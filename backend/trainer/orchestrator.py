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
    """Return a compact listing of the workspace for inclusion in prompts."""
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
        "You are the PM leading this team. Your job is to:\n"
        "1. Analyze the request and break it into concrete implementation steps\n"
        "2. Create a clear plan specifying WHAT needs to be done and WHO should do it\n"
        "3. You can also do work yourself using tools (write files, run commands, etc.)\n\n"
        f"Your team:\n{roster}\n"
        f"{ws_context}\n"
        "In your response, lay out the plan with numbered steps. "
        "For each step, note which team member is best suited. "
        "If something is simple enough that you can just do it yourself with tools, do it. "
        "Only delegate to specialists when their expertise is needed.\n\n"
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
        logger.warning("assign_tasks: Grok call failed (%s) — falling back to broadcast", exc)
        return [{"handle": s.github_handle, "task": fallback_prompt} for s in specialists]
