import asyncio
import json
import os
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticModel

from db import db
from models import Team, RoleSlot, Candidate, ChatMessage
from trainer import agent_chat
from trainer.orchestrator import assign_tasks
from trainer.tools import TOOL_SCHEMAS

router = APIRouter()

_WORKSPACE_ROOT = Path(os.getenv("AGENT_WORKSPACE_DIR", "agent-workspace"))


def _workspace_for_team(team_id: int) -> str:
    ws = _WORKSPACE_ROOT / str(team_id)
    ws.mkdir(parents=True, exist_ok=True)
    return str(ws)


class BuildChatRequest(PydanticModel):
    handle: str
    message: str


class BuildOrchestrateRequest(PydanticModel):
    prompt: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_candidate_for_team(team_id: int, handle: str) -> Candidate:
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
    return f"data: {json.dumps(data)}\n\n"


# ── Get message history ───────────────────────────────────────────────────────

@router.get("/teams/{team_id}/build/messages")
def get_build_messages(team_id: int, thread: str):
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


# ── Direct message (SSE stream) ───────────────────────────────────────────────

@router.post("/teams/{team_id}/build/chat")
async def build_chat(team_id: int, body: BuildChatRequest):
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
            yield _sse(ev)

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


# ── PM orchestration (SSE stream) ─────────────────────────────────────────────

@router.post("/teams/{team_id}/build/orchestrate")
async def build_orchestrate(team_id: int, body: BuildOrchestrateRequest):
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
        pm_tokens: list[str] = []

        def run_pm():
            try:
                text = agent_chat(
                    lora_path=lead.dna_path,
                    adapter_name=lead_handle,
                    role=lead.role_slot.role,
                    profile=lead.to_dict(),
                    history=orch_history,
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
            yield _sse(ev)

        pm_response = pm_tokens[0] if pm_tokens else ""
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
                         hist=[{"sender": "user", "content": task}], toks=spec_tokens):
                try:
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
                yield _sse(ev)

            if spec_tokens:
                with db.atomic():
                    ChatMessage.create(
                        team=team_id, thread="orchestrate",
                        sender=spec_handle, content=spec_tokens[0],
                    )

        yield _sse({"done": True})

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
