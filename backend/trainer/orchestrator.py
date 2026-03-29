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


def assign_tasks(
    pm_response: str,
    specialists: list,
    fallback_prompt: str,
    workspace_dir: str | None = None,
) -> list[dict]:
    """
    Call Grok-4 to derive one task assignment per specialist from the PM's plan.

    Args:
        pm_response: The full text response from the PM/lead agent.
        specialists:  List of Candidate ORM objects with .github_handle and .role_slot.role.
        fallback_prompt: The original user prompt used when Grok parsing fails.
        workspace_dir: Path to the team's sandboxed workspace (for context).

    Returns:
        List of {"handle": str, "task": str} dicts, one per specialist.
        Falls back to assigning `fallback_prompt` to every specialist on any error.
    """
    if not specialists or not pm_response:
        return [{"handle": s.github_handle, "task": fallback_prompt} for s in specialists]

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
                    f"PM said:\n{pm_response}\n\n"
                    f"Team specialists: {specialist_list}.\n"
                    f"{ws_context}"
                    "For each specialist, write ONE short task assignment sentence. "
                    "Return JSON: [{\"handle\": \"...\", \"task\": \"...\"}]. "
                    "Return ONLY valid JSON."
                ),
            }],
            temperature=0.3,
            max_tokens=512,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        assignments: list[dict] = json.loads(raw.strip())
        logger.info("assign_tasks: Grok assigned %d tasks", len(assignments))
        return assignments
    except Exception as exc:
        logger.warning("assign_tasks: Grok call failed (%s) — falling back to broadcast", exc)
        return [{"handle": s.github_handle, "task": fallback_prompt} for s in specialists]
