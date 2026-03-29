"""
Shared route utilities — eliminates repeated boilerplate across all routers.

Provides:
  get_team_or_404(team_id)           — fetch Team or raise 404
  get_block_dir(team_id, handle)     — resolve .dna block Path or raise 404/410
  sse(data)                          — format a dict as an SSE line
  require_json_file(path)            — read a JSON file or raise 500
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import HTTPException

from models import Team

_DNAS_ROOT = Path(os.getenv("DNAS_DIR", "dnas"))


# ── Team lookup ───────────────────────────────────────────────────────────────

def get_team_or_404(team_id: int) -> Team:
    """Return the Team row or raise HTTP 404."""
    try:
        return Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(status_code=404, detail="Team not found")


# ── DNA block lookup ──────────────────────────────────────────────────────────

def get_block_dir(team_id: str | int, handle: str) -> Path:
    """
    Resolve the DNA block directory for (team_id, handle).

    Raises:
      404  — block directory or manifest.json missing
      410  — block has been revoked (revoked.json present)
    """
    block_dir = _DNAS_ROOT / str(team_id) / handle
    if not block_dir.exists() or not (block_dir / "manifest.json").exists():
        raise HTTPException(
            status_code=404,
            detail=f"DNA block '{handle}' not found for team {team_id}",
        )
    if (block_dir / "revoked.json").exists():
        raise HTTPException(
            status_code=410,
            detail=f"DNA block '{handle}' has been revoked",
        )
    return block_dir


# ── SSE helpers ───────────────────────────────────────────────────────────────

def sse(data: dict) -> str:
    """Format a dict as a Server-Sent Events data line."""
    return f"data: {json.dumps(data)}\n\n"


def sse_done() -> str:
    """Emit a [DONE] SSE sentinel so clients can cleanly close the stream."""
    return "data: [DONE]\n\n"


# ── JSON file helpers ─────────────────────────────────────────────────────────

def read_json_file(path: Path, default: dict | None = None) -> dict:
    """Read a JSON file, returning default (empty dict) on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def require_json_file(path: Path, label: str = "file") -> dict:
    """Read a JSON file or raise HTTP 500 with a descriptive message."""
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"{label} not found at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"{label} is not valid JSON: {e}")
