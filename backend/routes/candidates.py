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

# ── In-memory caches ─────────────────────────────────────────────────────────
_headhunt_cache: dict[int, list[dict]] = {}
_search_cache: dict[tuple[int, int], dict] = {}  # (team_id, slot_id) -> response


class SelectCandidateRequest(PydanticModel):
    github_handle: str

class ExtractWebsiteRequest(PydanticModel):
    url: str

class ExtractResumeRequest(PydanticModel):
    text: str


# ── Headhunt SSE ──────────────────────────────────────────────────────────────

@router.get("/teams/{team_id}/headhunt/stream")
async def headhunt_stream(team_id: int, force: bool = Query(False)):
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
def search_role(team_id: int, slot_id: int, force: bool = Query(False)):
    slot = get_slot(team_id, slot_id)
    key = (team_id, slot_id)
    if not force and key in _search_cache:
        return _search_cache[key]
    candidates = search_candidates(slot.role, limit=5)
    result = {"role": slot.role, "slot_id": slot_id, "candidates": candidates}
    _search_cache[key] = result
    return result


# ── Website / resume extraction ───────────────────────────────────────────────

@router.post("/teams/{team_id}/roles/{slot_id}/extract-website", status_code=201)
def extract_website(team_id: int, slot_id: int, body: ExtractWebsiteRequest):
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
    slot = get_slot(team_id, slot_id)
    profile = build_github_profile(body.github_handle, role=slot.role)
    if not profile:
        raise HTTPException(404, f"GitHub user '{body.github_handle}' not found")
    _search_cache.pop((team_id, slot_id), None)
    return save_candidate(slot, profile)


@router.delete("/teams/{team_id}/roles/{slot_id}/candidate", status_code=204)
def remove_candidate(team_id: int, slot_id: int):
    slot = get_slot(team_id, slot_id)
    with db.atomic():
        Candidate.delete().where(Candidate.role_slot == slot).execute()
        slot.filled = False
        slot.save()
    _search_cache.pop((team_id, slot_id), None)
