"""
PM orchestration helpers — Grok-powered task assignment for multi-agent build sessions.

assign_tasks() extracts the raw Grok API call from the route layer so that
build.py stays as a thin SSE coordinator with no inline LLM logic.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _workspace_listing(workspace_dir: str | None, limit: int = 30) -> str:
    """Return a compact comma-separated listing of workspace entries for inclusion in orchestration prompts."""
    if not workspace_dir:
        return ""
    ws = Path(workspace_dir)
    if not ws.is_dir():
        return ""
    entries = sorted(ws.iterdir(), key=lambda p: (not p.is_dir(), p.name))[:limit]
    if not entries:
        return ""
    names = [f"{e.name}/" if e.is_dir() else e.name for e in entries]
    return ", ".join(names)


def build_pm_prompt(user_text: str, team_members: list, workspace_dir: str | None = None) -> str:
    """Wrap the user's request with PM orchestration instructions."""
    roster = "\n".join(
        f"  - @{m.github_handle} ({m.role_slot.role})" for m in team_members
    )
    ws_context = ""
    listing = _workspace_listing(workspace_dir)
    if listing:
        ws_context = f"\nWorkspace contains: {listing}\n"

    return (
        "You are the PM leading this team.\n\n"
        "RULE: Do NOT write plans. Do NOT number steps. Do NOT say 'I will now' or 'Executing step X'. "
        "If the task is simple (a question, file lookup, quick action), just do it immediately with tools "
        "or answer directly in one response. Save structured delegation only for genuinely complex, "
        "multi-person work (e.g. building a full feature from scratch).\n\n"
        f"Your team:\n{roster}\n"
        f"{ws_context}\n"
        "Use your tools yourself for anything straightforward. "
        "Only assign work to specialists when their specific expertise is truly required.\n\n"
        "IMPORTANT: At the very end of your response, append exactly one of these XML tags on its own line:\n"
        "  <no_delegate/> — if you handled this yourself and no specialist needs to act\n"
        "  <delegate/> — if specialists genuinely have work to do\n\n"
        f"User request: {user_text}"
    )


def assign_tasks(
    pm_response: str,
    specialists: list,
    fallback_prompt: str,
    workspace_dir: str | None = None,
) -> list[dict]:
    """
    Call Grok-4 to derive task assignments from the PM's plan.

    Only assigns to specialists who actually have work to do — not everyone.
    Returns an empty list if the PM handled everything.
    """
    if not specialists or not pm_response:
        return []

    specialist_list = ", ".join(
        f"{s.github_handle} ({s.role_slot.role})" for s in specialists
    )

    ws_context = ""
    listing = _workspace_listing(workspace_dir)
    if listing:
        ws_context = f"\nWorkspace already contains: {listing}\nTasks should build on existing files, not start from scratch.\n"

    try:
        from openai import OpenAI as _OpenAI
        grok = _OpenAI(api_key=os.getenv("XAI_API_KEY", ""), base_url="https://api.x.ai/v1")
        resp = grok.chat.completions.create(
            model="grok-4.20-0309-reasoning",
            messages=[{
                "role": "user",
                "content": (
                    f"PM's plan:\n{pm_response}\n\n"
                    f"Available specialists: {specialist_list}.\n"
                    f"{ws_context}\n"
                    "Based on the PM's plan, assign tasks ONLY to specialists who have "
                    "specific work to do. If the PM already handled everything or a specialist "
                    "has no relevant task, do NOT include them.\n"
                    "Each task should be a clear, actionable instruction.\n"
                    "Return JSON: [{\"handle\": \"...\", \"task\": \"...\"}]\n"
                    "Return an empty array [] if no specialist work is needed.\n"
                    "Return ONLY valid JSON."
                ),
            }],
            temperature=0.3,
            max_tokens=512,
        )
        raw = (resp.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        assignments: list[dict] = json.loads(raw.strip())
        logger.info("assign_tasks: Grok assigned %d tasks (of %d specialists)", len(assignments), len(specialists))
        return assignments
    except Exception as exc:
        logger.error("assign_tasks: Grok call failed — specialist delegation aborted", exc_info=True)
        raise RuntimeError(f"Specialist delegation failed: {exc}") from exc
