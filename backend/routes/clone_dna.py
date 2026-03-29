import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import db
from models import Team, RoleSlot, Candidate
from trainer import collect_training_data, generate_training_pairs, generate_system_prompt, train_lora

logger = logging.getLogger(__name__)
router = APIRouter()

_GROK_CACHE_DIR = Path(os.getenv("GROK_CACHE_DIR", "grok_cache"))


def _cache_path(handle: str) -> Path:
    return _GROK_CACHE_DIR / f"{handle}.json"


def _load_grok_cache(handle: str) -> dict | None:
    path = _cache_path(handle)
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.warning("Failed to read Grok cache for %s: %s", handle, e)
    return None


def _save_grok_cache(handle: str, pairs: list[dict], system_prompt: str) -> None:
    try:
        _GROK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _cache_path(handle).write_text(json.dumps({
            "pairs": pairs,
            "system_prompt": system_prompt,
        }, indent=2))
    except Exception as e:
        logger.warning("Failed to write Grok cache for %s: %s", handle, e)


@router.get("/teams/{team_id}/clone-dna/stream")
async def clone_dna_stream(team_id: int):
    try:
        team = Team.get_by_id(team_id)
    except Team.DoesNotExist:
        raise HTTPException(404, "Team not found")

    candidates: list[dict] = []
    for slot in team.slots.order_by(RoleSlot.id):
        first = slot.candidates.first()
        if first:
            candidates.append(first.to_dict())

    if not candidates:
        raise HTTPException(400, "No candidates selected — fill the team first")

    dnas_root = Path(os.getenv("DNAS_DIR", "dnas"))

    async def generator():
        yield f"data: {json.dumps({'phase': 'start', 'candidates': [c['github_handle'] for c in candidates]})}\n\n"

        loop = asyncio.get_running_loop()
        shared_queue: asyncio.Queue = asyncio.Queue()

        def make_emit(handle: str):
            def emit(event: dict):
                loop.call_soon_threadsafe(shared_queue.put_nowait, event)
            return emit

        async def process_candidate(candidate: dict) -> bool:
            handle = candidate["github_handle"]
            output_dir = str(dnas_root / str(team_id) / handle)
            emit = make_emit(handle)
            success = False
            try:
                cached = _load_grok_cache(handle)
                if cached:
                    emit({"phase": "generating", "candidate": handle,
                          "message": "Loaded training pairs and system prompt from cache"})
                    pairs = cached["pairs"]
                    sys_prompt = cached["system_prompt"]
                    code_blobs = []
                else:
                    code_blobs = await asyncio.to_thread(collect_training_data, candidate, emit)
                    pairs = await asyncio.to_thread(generate_training_pairs, candidate, code_blobs, emit)

                    if not pairs:
                        emit({"phase": "error", "candidate": handle,
                              "message": "No training pairs generated — skipping LoRA training"})
                        emit({"phase": "candidate_done", "candidate": handle, "skipped": True})
                        return False

                    sys_prompt = await asyncio.to_thread(generate_system_prompt, candidate, code_blobs, emit)
                    _save_grok_cache(handle, pairs, sys_prompt)
                    emit({"phase": "generating", "candidate": handle, "message": "Grok data cached for future runs"})

                emit({"phase": "training", "candidate": handle, "message": "Waiting for training slot..."})
                async with train_sem:
                    await asyncio.to_thread(train_lora, candidate, pairs, output_dir, emit)

                with db.atomic():
                    Candidate.update(
                        dna_cloned=True,
                        dna_path=output_dir,
                        dna_cloned_at=datetime.utcnow(),
                        system_prompt=sys_prompt,
                    ).where(Candidate.github_handle == handle).execute()

                emit({"phase": "candidate_done", "candidate": handle, "path": output_dir})
                success = True
            except Exception as e:
                emit({"phase": "error", "candidate": handle, "message": str(e)})
                emit({"phase": "candidate_done", "candidate": handle, "skipped": True})
            finally:
                loop.call_soon_threadsafe(shared_queue.put_nowait, {"__candidate_done__": handle})
            return success

        parallel_training = int(os.getenv("NUM_OF_PARALLEL_TRAINING", "1"))
        train_sem = asyncio.Semaphore(parallel_training)
        logger.info("Starting clone-DNA for %d candidate(s) with parallelism=%d", len(candidates), parallel_training)
        tasks = [asyncio.create_task(process_candidate(c)) for c in candidates]

        remaining = len(candidates)
        while remaining > 0:
            try:
                ev = await asyncio.wait_for(shared_queue.get(), timeout=90.0)
            except asyncio.TimeoutError:
                yield f"data: {json.dumps({'phase': 'heartbeat', 'remaining': remaining})}\n\n"
                continue

            if "__candidate_done__" in ev:
                remaining -= 1
            else:
                yield f"data: {json.dumps(ev)}\n\n"

        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_done = sum(1 for r in results if r is True)
        yield f"data: {json.dumps({'phase': 'done', 'total': total_done})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
