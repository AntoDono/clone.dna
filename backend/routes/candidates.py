"""
Candidates router — GitHub headhunting, candidate selection, and profile extraction.

Three candidate discovery paths:
  1. AI headhunt stream (SSE) — searches GitHub by role, streams structured profiles;
     results cached in-memory per team (_headhunt_cache) to avoid redundant API calls.
  2. Website extraction — scrapes a personal site or portfolio URL via Grok.
  3. Resume extraction — accepts raw resume text, extracts a structured profile via Grok.

All three paths normalize to the same profile shape and persist via save_candidate().

Caching (two layers):
  - _headhunt_cache  (team_id → list[profile])  — in-memory, full headhunt results per team
  - _search_cache    ((team_id, slot_id) → SearchResult) — in-memory, per-slot search results
  - GithubProfileCache — SQLite-backed, 24-hour TTL per (handle, role)
  All layers are invalidated by DELETE /headhunt/cache or ?force=true on any endpoint.
"""

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel as PydanticModel

from db import db
from models import Team, RoleSlot, Candidate
from routes.utils import get_team_or_404
from extractor import (
    search_candidates,
    search_users_raw,
    build_github_profile,
    extract_from_website,
    extract_from_resume,
    score_candidates_against_jd,
)
from routes.teams import get_slot, save_candidate

router = APIRouter()

# ── In-memory caches ─────────────────────────────────────────────────────────
_headhunt_cache: dict[int, list[dict]] = {}
_search_cache: dict[tuple[int, int], dict] = {}  # (team_id, slot_id) -> response


class SelectCandidateRequest(PydanticModel):
    github_handle: str

class ExtractWebsiteRequest(PydanticModel):
    url: str

class ExtractResumeRequest(PydanticModel):
    text: str

class FitScoreRequest(PydanticModel):
    job_description: str
    role: str = "swe"


# ── Headhunt SSE ──────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/headhunt/stream")
async def headhunt_stream(team_id: int, force: bool = Query(False)):
    """Stream GitHub headhunt results over SSE: searches by role, builds profiles, caches results per team. Accepts force=true to bypass cache."""
    get_team_or_404(team_id)

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
                    profile = await asyncio.to_thread(build_github_profile, handle, role, force)
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
    try:
        from models import GithubProfileCache
        GithubProfileCache.delete().execute()
    except Exception:
        pass


@router.post("/teams/{team_id}/headhunt/score")
def score_headhunt_candidates(team_id: int, body: FitScoreRequest):
    """
    Score all cached headhunt candidates against a job description using Grok.

    Sends all candidate profiles to Grok in a single structured call — returns ranked
    scores per candidate across technical_fit, domain_fit, and seniority_match dimensions,
    plus per-candidate strengths, gaps, and reasoning.     Uses the team's in-memory headhunt
    cache; call the headhunt stream first to populate candidates.
    """
    get_team_or_404(team_id)

    cached = _headhunt_cache.get(team_id, [])
    candidates = [event["candidate"] for event in cached if "candidate" in event]

    if not candidates:
        raise HTTPException(422, "No headhunted candidates found for this team — run the headhunt stream first")

    if len(body.job_description.strip()) < 20:
        raise HTTPException(422, "job_description is too short — provide at least a sentence describing the role")

    result = score_candidates_against_jd(candidates, body.job_description, body.role)
    if not result:
        raise HTTPException(503, "Grok fit scoring unavailable — check XAI_API_KEY")

    # Merge scores back into candidate profiles for a single enriched response
    score_map = {s.handle: s for s in result.scores}
    ranked = sorted(result.scores, key=lambda s: s.overall_score, reverse=True)

    return {
        "job_description": body.job_description[:500],
        "role": body.role,
        "total_scored": len(result.scores),
        "ranked": [
            {
                **score_map[s.handle].model_dump(),
                "candidate": next(
                    (c for c in candidates if c.get("github_handle") == s.handle),
                    None,
                ),
            }
            for s in ranked
        ],
    }


# ── Role search ───────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/roles/{slot_id}/search")
def search_role(team_id: int, slot_id: int, force: bool = Query(False)):
    """Return cached or freshly fetched candidates for a role slot. Accepts ?force=true to bypass _search_cache."""
    slot = get_slot(team_id, slot_id)
    key = (team_id, slot_id)
    if not force and key in _search_cache:
        return _search_cache[key]
    candidates = search_candidates(slot.role, limit=5, force=force)
    result = {"role": slot.role, "slot_id": slot_id, "candidates": candidates}
    _search_cache[key] = result
    return result


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
    _search_cache.pop((team_id, slot_id), None)
    return save_candidate(slot, profile)


@router.delete("/teams/{team_id}/roles/{slot_id}/candidate", status_code=204)
def remove_candidate(team_id: int, slot_id: int):
    """Remove the candidate from a role slot and mark the slot as unfilled."""
    slot = get_slot(team_id, slot_id)
    with db.atomic():
        Candidate.delete().where(Candidate.role_slot == slot).execute()
        slot.filled = False
        slot.save()
    _search_cache.pop((team_id, slot_id), None)
