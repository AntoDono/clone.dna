import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db import db
from models import Team, RoleSlot, Candidate
from trainer import collect_training_data, generate_training_pairs, train_lora

router = APIRouter()


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
                code_blobs = await asyncio.to_thread(collect_training_data, candidate, emit)
                pairs = await asyncio.to_thread(generate_training_pairs, candidate, code_blobs, emit)

                if not pairs:
                    emit({"phase": "error", "candidate": handle,
                          "message": "No training pairs generated — skipping LoRA training"})
                    emit({"phase": "candidate_done", "candidate": handle, "skipped": True})
                    return False

                emit({"phase": "training", "candidate": handle, "message": "Waiting for GPU slot..."})
                async with train_sem:
                    await asyncio.to_thread(train_lora, candidate, pairs, output_dir, emit)

                with db.atomic():
                    Candidate.update(
                        dna_cloned=True,
                        dna_path=output_dir,
                        dna_cloned_at=datetime.utcnow(),
                    ).where(Candidate.github_handle == handle).execute()

                emit({"phase": "candidate_done", "candidate": handle, "path": output_dir})
                success = True
            except Exception as e:
                emit({"phase": "error", "candidate": handle, "message": str(e)})
                emit({"phase": "candidate_done", "candidate": handle, "skipped": True})
            finally:
                loop.call_soon_threadsafe(shared_queue.put_nowait, {"__candidate_done__": handle})
            return success

        # One GPU slot at a time for training; collect+generate run in parallel
        train_sem = asyncio.Semaphore(1)
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
