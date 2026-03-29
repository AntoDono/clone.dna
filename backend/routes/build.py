"""
Build router — post-clone chat and PM orchestration over SSE.

Endpoints:
  POST /chat        — DM a single cloned candidate; hot-swaps their LoRA adapter
                      and runs the tool-use agent loop (up to 10 iterations).
  POST /compare     — side-by-side: same prompt through base model vs adapter.
  POST /orchestrate — PM generates a plan → Grok assigns tasks → each specialist
                      responds sequentially with shared workspace tool access.
  GET  /messages    — full message history for the team's build workspace.
"""

import asyncio
import datetime as dt
import json
import os
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel as PydanticModel

from db import db
from models import Team, RoleSlot, Candidate, ChatMessage
from trainer import agent_chat, compare_generation, grok_chat
from trainer.orchestrator import assign_tasks, build_pm_prompt
from trainer.tools import TOOL_SCHEMAS

router = APIRouter()

_WORKSPACE_ROOT = Path(os.getenv("AGENT_WORKSPACE_DIR", "agent-workspace"))
_META_DIR_NAME = ".clone_dna"
_RUNS_DIR_NAME = "orchestrations"


def _workspace_for_team(team_id: int) -> str:
    """Return the sandboxed workspace directory path for a team, creating it if necessary."""
    ws = _WORKSPACE_ROOT / str(team_id)
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


def _workspace_meta_dir(team_id: int) -> Path:
    """Return the metadata directory used for workspace-local audit artifacts."""
    meta = Path(_workspace_for_team(team_id)) / _META_DIR_NAME
    meta.mkdir(parents=True, exist_ok=True)
    return meta


def _persist_workspace_artifact(team_id: int, name: str, payload: dict) -> Path:
    """Write a JSON artifact into the team's hidden workspace metadata directory."""
    path = _workspace_meta_dir(team_id) / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _persist_orchestration_run(team_id: int, payload: dict) -> Path:
    """Persist a full orchestration run and update the latest-run pointer."""
    runs_dir = _workspace_meta_dir(team_id) / _RUNS_DIR_NAME
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_id = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    run_path = runs_dir / f"{run_id}.json"
    run_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _persist_workspace_artifact(team_id, "latest_orchestration.json", payload)
    return run_path


class BuildChatRequest(PydanticModel):
    handle: str
    message: str
    use_grok: bool = False


class BuildOrchestrateRequest(PydanticModel):
    prompt: str
    use_grok: bool = False


class BuildCompareRequest(PydanticModel):
    handle: str
    prompt: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_candidate_for_team(team_id: int, handle: str) -> Candidate:
    """Fetch a Candidate by GitHub handle, verifying they belong to the given team. Raises 404 if not found."""
    result = (
        Candidate
        .select(Candidate, RoleSlot)
        .join(RoleSlot)
        .join(Team)
        .where(Team.id == team_id, Candidate.github_handle == handle)
        .first()
    )
    if not result:
        raise HTTPException(404, f"Candidate '{handle}' not found in team {team_id}")
    return result


def _sse(data: dict) -> str:
    """Format a dict as an SSE data line for StreamingResponse."""
    return f"data: {json.dumps(data)}\n\n"


_ATTACHMENT_PREFIX = "__ATTACHMENT__:"


def _extract_attachment(ev: dict, team_id: int) -> dict | None:
    """If ev contains an attach_file tool result, parse it and return an attachment dict.

    Also mutates ev['tool_result']['output'] to a friendly summary so the raw
    marker is never shown in the chat bubble or stored in the DB.
    """
    tr = ev.get("tool_result")
    if not tr:
        return None
    output = tr.get("output", "")
    if not isinstance(output, str) or not output.startswith(_ATTACHMENT_PREFIX):
        return None
    try:
        att = json.loads(output[len(_ATTACHMENT_PREFIX):])
        att["url"] = f"/teams/{team_id}/build/files/{att['path']}"
        size_kb = round(att.get("size", 0) / 1024, 1)
        tr["output"] = f"Attached: {att['name']} ({size_kb} KB)"
        return att
    except Exception:
        return None


# ── File download ─────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/build/files/{path:path}")
async def build_get_file(team_id: int, path: str):
    """Serve a file from the team's agent workspace for download."""
    workspace = Path(_workspace_for_team(team_id)).resolve()
    target = (workspace / path).resolve()
    if not str(target).startswith(str(workspace)):
        raise HTTPException(403, "Access denied")
    if not target.exists() or not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(
        str(target),
        filename=target.name,
        headers={"Content-Disposition": f'attachment; filename="{target.name}"'},
    )


# ── Get message history ───────────────────────────────────────────────────────

@router.get("/teams/{team_id}/build/messages")
def get_build_messages(team_id: int, thread: str):
    """Return full message history for a team's build workspace, optionally filtered by thread."""
    try:
        Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")
    msgs = (
        ChatMessage
        .select()
        .where(ChatMessage.team == team_id, ChatMessage.thread == thread)
        .order_by(ChatMessage.created_at)
    )
    return [m.to_dict() for m in msgs]


@router.get("/teams/{team_id}/build/artifacts")
def get_build_artifacts(team_id: int):
    """Return the latest orchestration artifact and recent tool audit entries for a team workspace."""
    try:
        Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")

    meta_dir = _workspace_meta_dir(team_id)
    latest_orchestration_path = meta_dir / "latest_orchestration.json"
    audit_path = meta_dir / "tool_audit.jsonl"

    latest_orchestration = None
    if latest_orchestration_path.exists():
        latest_orchestration = json.loads(latest_orchestration_path.read_text(encoding="utf-8"))

    audit_events: list[dict] = []
    if audit_path.exists():
        for line in audit_path.read_text(encoding="utf-8").splitlines()[-50:]:
            if not line.strip():
                continue
            try:
                audit_events.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    return {
        "workspace": _workspace_for_team(team_id),
        "latest_orchestration": latest_orchestration,
        "tool_audit_events": audit_events,
    }


# ── Direct message (SSE stream) ───────────────────────────────────────────────

@router.post("/teams/{team_id}/build/chat")
async def build_chat(team_id: int, body: BuildChatRequest):
    """Stream a direct message to a cloned candidate using their LoRA adapter and the tool-use agent loop."""
    try:
        Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")

    candidate = _get_candidate_for_team(team_id, body.handle)
    if not candidate.dna_cloned:
        raise HTTPException(400, f"DNA not yet cloned for '{body.handle}'")

    workspace = _workspace_for_team(team_id)

    with db.atomic():
        ChatMessage.create(
            team=team_id,
            thread=body.handle,
            sender="user",
            content=body.message,
        )

    history = [
        m.to_dict()
        for m in ChatMessage
        .select()
        .where(ChatMessage.team == team_id, ChatMessage.thread == body.handle)
        .order_by(ChatMessage.created_at)
    ]

    profile = candidate.to_dict()
    role = candidate.role_slot.role
    loop = asyncio.get_running_loop()
    token_queue: asyncio.Queue = asyncio.Queue()
    full_response: list[str] = []

    def emit(event: dict):
        loop.call_soon_threadsafe(token_queue.put_nowait, event)

    def run_inference():
        try:
            if body.use_grok:
                text = grok_chat(
                    candidate=profile,
                    history=history,
                    emit=emit,
                    workspace_dir=workspace,
                    tools=TOOL_SCHEMAS,
                )
            else:
                text = agent_chat(
                    lora_path=candidate.dna_path,
                    adapter_name=body.handle,
                    role=role,
                    profile=profile,
                    history=history,
                    emit=emit,
                    workspace_dir=workspace,
                    tools=TOOL_SCHEMAS,
                    system_prompt=candidate.system_prompt or None,
                )
            full_response.append(text)
        except Exception as e:
            emit({"error": str(e)})
        finally:
            loop.call_soon_threadsafe(token_queue.put_nowait, {"__done__": True})

    async def generator():
        threading.Thread(target=run_inference, daemon=True).start()
        while True:
            ev = await token_queue.get()
            if ev.get("__done__"):
                break
            att = _extract_attachment(ev, team_id)
            yield _sse(ev)
            if att:
                yield _sse({"attachment": att})

        if full_response:
            with db.atomic():
                msg = ChatMessage.create(
                    team=team_id,
                    thread=body.handle,
                    sender=body.handle,
                    content=full_response[0],
                )
            yield _sse({"done": True, "message_id": msg.id})
        else:
            yield _sse({"done": True})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Side-by-side comparison (SSE stream) ──────────────────────────────────────

@router.post("/teams/{team_id}/build/compare")
async def build_compare(team_id: int, body: BuildCompareRequest):
    """Generate the same prompt through raw base model and adapter-loaded model.

    Streams SSE events with {"source": "adapter"|"base", "token": "..."} so the
    frontend can display both responses side-by-side.
    """
    try:
        Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")

    candidate = _get_candidate_for_team(team_id, body.handle)
    if not candidate.dna_cloned:
        raise HTTPException(400, f"DNA not yet cloned for '{body.handle}'")

    loop = asyncio.get_running_loop()
    token_queue: asyncio.Queue = asyncio.Queue()
    result_holder: list[dict] = []

    def emit(event: dict):
        loop.call_soon_threadsafe(token_queue.put_nowait, event)

    def run_compare():
        try:
            result = compare_generation(
                lora_path=candidate.dna_path,
                adapter_name=body.handle,
                role=candidate.role_slot.role,
                profile=candidate.to_dict(),
                prompt_text=body.prompt,
                emit=emit,
                system_prompt=candidate.system_prompt or None,
            )
            result_holder.append(result)
        except Exception as e:
            emit({"error": str(e)})
        finally:
            loop.call_soon_threadsafe(token_queue.put_nowait, {"__done__": True})

    async def generator():
        threading.Thread(target=run_compare, daemon=True).start()
        while True:
            ev = await token_queue.get()
            if ev.get("__done__"):
                break
            yield _sse(ev)

        if result_holder:
            yield _sse({
                "done": True,
                "base_response": result_holder[0]["base_response"],
                "adapter_response": result_holder[0]["adapter_response"],
            })
        else:
            yield _sse({"done": True})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── PM orchestration (SSE stream) ─────────────────────────────────────────────

@router.post("/teams/{team_id}/build/orchestrate")
async def build_orchestrate(team_id: int, body: BuildOrchestrateRequest):
    """Stream PM orchestration: PM generates a plan, Grok assigns tasks to specialists, each specialist responds sequentially."""
    try:
        team = Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")

    cloned: list[Candidate] = []
    pm_candidate: Candidate | None = None
    for slot in team.slots.order_by(RoleSlot.id):
        first = slot.candidates.first()
        if first and first.dna_cloned:
            cloned.append(first)
            if slot.role == "pm" and pm_candidate is None:
                pm_candidate = first

    if not cloned:
        raise HTTPException(400, "No cloned candidates found — clone DNA first")

    workspace = _workspace_for_team(team_id)

    with db.atomic():
        ChatMessage.create(
            team=team_id, thread="orchestrate", sender="user", content=body.prompt
        )

    loop = asyncio.get_running_loop()
    shared_queue: asyncio.Queue = asyncio.Queue()

    def make_emit(speaker: str):
        def emit(event: dict):
            loop.call_soon_threadsafe(shared_queue.put_nowait, {**event, "speaker": speaker})
        return emit

    async def generator():
        yield _sse({"phase": "start", "prompt": body.prompt})
        run_record = {
            "team_id": team_id,
            "prompt": body.prompt,
            "workspace": workspace,
            "started_at": dt.datetime.utcnow().isoformat() + "Z",
            "lead": None,
            "pm_response": "",
            "assignments": [],
            "specialist_outputs": [],
        }

        orch_history = [
            m.to_dict()
            for m in ChatMessage
            .select()
            .where(ChatMessage.team == team_id, ChatMessage.thread == "orchestrate")
            .order_by(ChatMessage.created_at)
        ]

        # ── Step 1: PM plans ──────────────────────────────────────────────────
        lead = pm_candidate or cloned[0]
        lead_handle = lead.github_handle
        run_record["lead"] = {"handle": lead_handle, "role": lead.role_slot.role}
        pm_tokens: list[str] = []

        pm_history = list(orch_history)
        if pm_history and pm_history[-1].get("sender") == "user":
            enriched = build_pm_prompt(pm_history[-1]["content"], cloned, workspace)
            pm_history[-1] = {**pm_history[-1], "content": enriched}

        def run_pm():
            try:
                if body.use_grok:
                    text = grok_chat(
                        candidate=lead.to_dict(),
                        history=pm_history,
                        emit=make_emit(lead_handle),
                        workspace_dir=workspace,
                        tools=TOOL_SCHEMAS,
                    )
                else:
                    text = agent_chat(
                        lora_path=lead.dna_path,
                        adapter_name=lead_handle,
                        role=lead.role_slot.role,
                        profile=lead.to_dict(),
                        history=pm_history,
                        emit=make_emit(lead_handle),
                        workspace_dir=workspace,
                        tools=TOOL_SCHEMAS,
                        system_prompt=lead.system_prompt or None,
                    )
                pm_tokens.append(text)
            except Exception as e:
                loop.call_soon_threadsafe(shared_queue.put_nowait,
                    {"speaker": lead_handle, "error": str(e)})
            finally:
                loop.call_soon_threadsafe(shared_queue.put_nowait,
                    {"__speaker_done__": lead_handle})

        threading.Thread(target=run_pm, daemon=True).start()

        while True:
            ev = await shared_queue.get()
            if ev.get("__speaker_done__") == lead_handle:
                break
            att = _extract_attachment(ev, team_id)
            yield _sse(ev)
            if att:
                yield _sse({"speaker": ev.get("speaker"), "attachment": att})

        pm_response = pm_tokens[0] if pm_tokens else ""
        run_record["pm_response"] = pm_response
        if pm_response:
            with db.atomic():
                ChatMessage.create(
                    team=team_id, thread="orchestrate",
                    sender=lead_handle, content=pm_response,
                )

        # ── Step 2: Grok assigns tasks to specialists ─────────────────────────
        specialists = [c for c in cloned if c.github_handle != lead_handle]
        assignments = await asyncio.to_thread(
            assign_tasks, pm_response, specialists, body.prompt, workspace
        )
        run_record["assignments"] = assignments

        # ── Step 3: Each specialist responds ─────────────────────────────────
        handle_map = {c.github_handle: c for c in specialists}
        for assignment in assignments:
            spec_handle = assignment.get("handle", "")
            task = assignment.get("task", body.prompt)
            spec = handle_map.get(spec_handle)
            if not spec:
                continue

            spec_tokens: list[str] = []
            yield _sse({"phase": "specialist", "speaker": spec_handle, "task": task})

            def run_spec(s=spec, sh=spec_handle, sr=spec.role_slot.role,
                         hist=[{"sender": "user", "content": task}], toks=spec_tokens,
                         pm=lead):
                try:
                    if body.use_grok:
                        text = grok_chat(
                            candidate=s.to_dict(),
                            history=hist,
                            emit=make_emit(sh),
                            workspace_dir=workspace,
                            tools=TOOL_SCHEMAS,
                        )
                    else:
                        # Blend the specialist adapter (0.7) with the PM adapter (0.3)
                        # in weight space so the PM's framing is encoded in the weights,
                        # not injected as a system prompt. Falls back to specialist-only
                        # if either adapter is missing or the merge fails.
                        text = agent_chat(
                            lora_path=s.dna_path,
                            adapter_name=sh,
                            role=sr,
                            profile=s.to_dict(),
                            history=hist,
                            emit=make_emit(sh),
                            workspace_dir=workspace,
                            tools=TOOL_SCHEMAS,
                            system_prompt=s.system_prompt or None,
                            blend_lora_path=pm.dna_path,
                            blend_adapter_name=pm.github_handle,
                            blend_weight=0.7,
                        )
                    toks.append(text)
                except Exception as e:
                    loop.call_soon_threadsafe(shared_queue.put_nowait,
                        {"speaker": sh, "error": str(e)})
                finally:
                    loop.call_soon_threadsafe(shared_queue.put_nowait, {"__speaker_done__": sh})

            threading.Thread(target=run_spec, daemon=True).start()

            while True:
                ev = await shared_queue.get()
                if ev.get("__speaker_done__") == spec_handle:
                    break
                att = _extract_attachment(ev, team_id)
                yield _sse(ev)
                if att:
                    yield _sse({"speaker": ev.get("speaker"), "attachment": att})

            if spec_tokens:
                run_record["specialist_outputs"].append({
                    "handle": spec_handle,
                    "role": spec.role_slot.role,
                    "task": task,
                    "response": spec_tokens[0],
                })
                with db.atomic():
                    ChatMessage.create(
                        team=team_id, thread="orchestrate",
                        sender=spec_handle, content=spec_tokens[0],
                    )

        run_record["completed_at"] = dt.datetime.utcnow().isoformat() + "Z"
        artifact_path = _persist_orchestration_run(team_id, run_record)
        yield _sse({"phase": "artifact", "path": str(artifact_path)})
        yield _sse({"done": True})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
