"""
Candidates router — GitHub headhunting, candidate selection, and profile extraction.

Three candidate discovery paths:
  1. AI headhunt stream (SSE) — searches GitHub by role, streams structured profiles;
     results cached in-memory per team to avoid redundant API calls.
  2. Website extraction — scrapes a personal site or portfolio URL via Grok.
  3. Resume extraction — accepts raw resume text, extracts a structured profile via Grok.

All three paths normalize to the same profile shape and persist via save_candidate().
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticModel

from db import db
from models import Team, RoleSlot, Candidate
from extractor import (
    search_candidates,
    search_users_raw,
    build_github_profile,
    extract_from_website,
    extract_from_resume,
)
from routes.teams import get_slot, save_candidate

router = APIRouter()

# ── In-memory headhunt cache (keyed by team_id) ───────────────────────────────
_headhunt_cache: dict[int, list[dict]] = {}


class SelectCandidateRequest(PydanticModel):
    github_handle: str

class ExtractWebsiteRequest(PydanticModel):
    url: str

class ExtractResumeRequest(PydanticModel):
    text: str


# ── Headhunt SSE ──────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/headhunt/stream")
async def headhunt_stream(team_id: int, force: bool = Query(False)):
    """Stream GitHub headhunt results over SSE: searches by role, builds profiles, caches results per team. Accepts force=true to bypass cache."""
    try:
        Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")

    async def generator():
        if not force and team_id in _headhunt_cache:
            yield f"data: {json.dumps({'cached': True})}\n\n"
            for event in _headhunt_cache[team_id]:
                yield f"data: {json.dumps(event)}\n\n"
                await asyncio.sleep(0)
            total = len(_headhunt_cache[team_id])
            yield f"data: {json.dumps({'done': True, 'total': total, 'cached': True})}\n\n"
            return

        _headhunt_cache.pop(team_id, None)
        collected: list[dict] = []
        total_found = 0

        for role in ["pm", "swe", "designer"]:
            try:
                handles = await asyncio.to_thread(search_users_raw, role, 5)
            except Exception as e:
                yield f"data: {json.dumps({'error': f'GitHub search failed for {role}: {e}'})}\n\n"
                handles = []
            if not handles:
                yield f"data: {json.dumps({'error': f'No GitHub results for role: {role}. Check GITHUB_TOKEN in .env'})}\n\n"
            for handle in handles:
                try:
                    profile = await asyncio.to_thread(build_github_profile, handle, role)
                except Exception:
                    profile = None
                if profile:
                    total_found += 1
                    event = {"role": role, "candidate": profile}
                    collected.append(event)
                    yield f"data: {json.dumps(event)}\n\n"

        _headhunt_cache[team_id] = collected
        yield f"data: {json.dumps({'done': True, 'total': total_found})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/teams/{team_id}/headhunt/cache", status_code=204)
def clear_headhunt_cache(team_id: int):
    _headhunt_cache.pop(team_id, None)


# ── Role search ───────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/roles/{slot_id}/search")
def search_role(team_id: int, slot_id: int):
    """Return cached or freshly fetched candidates for a specific role slot."""
    slot = get_slot(team_id, slot_id)
    candidates = search_candidates(slot.role, limit=5)
    return {"role": slot.role, "slot_id": slot_id, "candidates": candidates}


# ── Website / resume extraction ───────────────────────────────────────────────

@router.post("/teams/{team_id}/roles/{slot_id}/extract-website", status_code=201)
def extract_website(team_id: int, slot_id: int, body: ExtractWebsiteRequest):
    """Scrape a URL, extract a candidate profile via Grok, and persist to the slot."""
    slot = get_slot(team_id, slot_id)
    try:
        profile = extract_from_website(body.url.strip(), role=slot.role)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")
    return save_candidate(slot, profile)


@router.post("/teams/{team_id}/roles/{slot_id}/extract-resume", status_code=201)
def extract_resume(team_id: int, slot_id: int, body: ExtractResumeRequest):
    """Extract a candidate profile from raw resume text via Grok and persist to the slot."""
    slot = get_slot(team_id, slot_id)
    try:
        profile = extract_from_resume(body.text.strip(), role=slot.role)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(500, f"Extraction failed: {e}")
    return save_candidate(slot, profile)


# ── Candidate select / remove ─────────────────────────────────────────────────

@router.post("/teams/{team_id}/roles/{slot_id}/select", status_code=201)
def select_candidate(team_id: int, slot_id: int, body: SelectCandidateRequest):
    """Fetch a GitHub user profile and assign them to the specified role slot."""
    slot = get_slot(team_id, slot_id)
    profile = build_github_profile(body.github_handle, role=slot.role)
    if not profile:
        raise HTTPException(404, f"GitHub user '{body.github_handle}' not found")
    return save_candidate(slot, profile)


@router.delete("/teams/{team_id}/roles/{slot_id}/candidate", status_code=204)
def remove_candidate(team_id: int, slot_id: int):
    """Remove the candidate from a role slot and mark the slot as unfilled."""
    slot = get_slot(team_id, slot_id)
    with db.atomic():
        Candidate.delete().where(Candidate.role_slot == slot).execute()
        slot.filled = False
        slot.save()
