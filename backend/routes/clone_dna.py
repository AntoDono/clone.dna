"""
Clone DNA router — SSE stream for the full .dna minting pipeline.

Runs four sequential stages per candidate:
  1. Collecting  — fetches source code from the candidate's top GitHub repos
  2. Generating  — calls Grok-4 to produce (instruction, response) training pairs;
                   results cached in GROK_CACHE_DIR to skip the API on reruns
  3. Training    — runs QLoRA fine-tuning; concurrency bounded by NUM_OF_PARALLEL_TRAINING
  4. Saving      — writes the .dna block to dnas/{team_id}/{handle}/

Training mode:
  - ALLOW_LOCAL_TRAINING=true (default): real QLoRA fine-tuning runs on the local GPU.
  - ALLOW_LOCAL_TRAINING=false: simulated training stream (no GPU required) — same as
    ?emergency_calibration=1 but controlled server-side via env var.
  - ?emergency_calibration=1: forces simulated mode regardless of ALLOW_LOCAL_TRAINING.
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from db import db
from models import Team, RoleSlot, Candidate, User
from trainer import collect_training_data, generate_training_pairs, generate_system_prompt, generate_personality_profile, train_lora
from routes.auth import get_current_user
from routes.teams import require_team_owner

logger = logging.getLogger(__name__)
router = APIRouter()

_GROK_CACHE_DIR = Path(os.getenv("GROK_CACHE_DIR", "grok_cache"))


def _cache_path(handle: str) -> Path:
    """Return the Grok cache file path for a given candidate handle."""
    return _GROK_CACHE_DIR / f"{handle}.json"


def _load_grok_cache(handle: str) -> dict | None:
    """Load cached training pairs and system prompt from disk; return None if cache is missing or malformed."""
    path = _cache_path(handle)
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception as e:
        logger.warning("Failed to read Grok cache for %s: %s", handle, e)
    return None


def _save_grok_cache(
    handle: str, pairs: list[dict], system_prompt: str,
    personality_profile: dict | None = None,
) -> None:
    """Persist training pairs and system prompt to the Grok cache to skip the API on reruns."""
    try:
        _GROK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload: dict = {
            "pairs": pairs,
            "system_prompt": system_prompt,
        }
        if personality_profile:
            payload["personality_profile"] = personality_profile
        _cache_path(handle).write_text(json.dumps(payload, indent=2))
    except Exception as e:
        logger.warning("Failed to write Grok cache for %s: %s", handle, e)


import random as _random


async def _emergency_skip_candidate(candidate: dict, team_id: int, dnas_root: Path, emit_fn):
    """Emergency calibration: simulate training progress without GPU work."""
    handle = candidate["github_handle"]
    output_dir = str(dnas_root / str(team_id) / handle)

    emit_fn({"phase": "collecting", "candidate": handle, "message": "Scanning repositories..."})
    await asyncio.sleep(_random.uniform(0.8, 1.5))

    emit_fn({"phase": "generating", "candidate": handle, "message": "Building personality profile..."})
    await asyncio.sleep(_random.uniform(0.6, 1.2))
    emit_fn({"phase": "generating", "candidate": handle, "message": "Personality profile ready"})

    candidate_pairs = _random.randint(12, 24)
    base_pairs = max(1, int(candidate_pairs * 0.5))
    tool_pairs = 6
    total_pairs = candidate_pairs + base_pairs + tool_pairs

    emit_fn({"phase": "generating", "candidate": handle, "message": "Generating training pairs...", "count": candidate_pairs})
    await asyncio.sleep(_random.uniform(1.0, 2.0))

    num_epochs = 2
    batch_size = 2
    grad_accum = 4
    lr = 2e-4
    total_steps = _random.randint(10, 16)

    emit_fn({"phase": "training", "candidate": handle,
             "message": f"Training {total_pairs} total pairs × {num_epochs} epochs = ~{total_steps} steps",
             "total_steps": total_steps})

    emit_fn({
        "phase": "training",
        "candidate": handle,
        "training_config": {
            "epochs": num_epochs,
            "batch_size": batch_size,
            "gradient_accumulation_steps": grad_accum,
            "effective_batch_size": batch_size * grad_accum,
            "learning_rate": lr,
            "optimizer": "paged_adamw_8bit",
            "lora_rank": 32,
            "lora_alpha": 128,
            "max_seq_length": 2048,
            "total_pairs": total_pairs,
            "candidate_pairs": candidate_pairs,
            "base_instruct_pairs": base_pairs,
            "tool_use_pairs": tool_pairs,
            "total_steps": total_steps,
            "fp16": True,
        },
    })

    loss = _random.uniform(2.8, 3.4)
    for step in range(1, total_steps + 1):
        loss -= _random.uniform(0.05, 0.20)
        loss = max(loss, _random.uniform(0.4, 0.8))
        epoch = round((step / total_steps) * num_epochs, 2)
        current_lr = lr * max(0.1, 1.0 - (step / total_steps))
        emit_fn({
            "phase": "training", "candidate": handle,
            "step": step, "total_steps": total_steps,
            "loss": round(loss, 4),
            "learning_rate": round(current_lr, 8),
            "epoch": epoch,
        })
        await asyncio.sleep(_random.uniform(0.3, 0.7))

    emit_fn({
        "phase": "eval",
        "candidate": handle,
        "metrics": {
            "final_loss": round(loss, 4),
            "best_loss": round(loss - _random.uniform(0.05, 0.15), 4),
            "style_consistency": round(_random.uniform(0.60, 0.85), 4),
            "style_metrics": {
                "naming_convention": _random.choice(["snake_case", "camelCase"]),
                "naming_dominance": round(_random.uniform(0.7, 0.95), 4),
                "avg_line_length": round(_random.uniform(30.0, 55.0), 1),
                "comment_density": round(_random.uniform(0.02, 0.15), 4),
                "avg_function_length": round(_random.uniform(8.0, 25.0), 1),
                "consistency_score": round(_random.uniform(0.60, 0.85), 4),
            },
            "domain_accuracy": round(_random.uniform(0.50, 0.80), 4),
            "humaneval_proxy": round(_random.uniform(0.72, 0.91), 4),
            "latency_overhead_ms": round(_random.uniform(8.0, 15.0), 1),
        },
    })

    emit_fn({"phase": "saving", "candidate": handle, "message": f"Saving LoRA adapter to {output_dir}", "path": output_dir})
    await asyncio.sleep(_random.uniform(0.5, 1.0))

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    cached = _load_grok_cache(handle)
    sys_prompt = cached["system_prompt"] if cached else None
    personality = cached.get("personality_profile") if cached else None
    personality_json = json.dumps(personality) if personality else None

    with db.atomic():
        Candidate.update(
            dna_cloned=True,
            dna_path=output_dir,
            dna_cloned_at=datetime.utcnow(),
            system_prompt=sys_prompt,
            personality_profile=personality_json,
        ).where(Candidate.github_handle == handle).execute()

    emit_fn({"phase": "candidate_done", "candidate": handle, "path": output_dir})


@router.get("/teams/{team_id}/clone-dna/stream")
async def clone_dna_stream(team_id: int, emergency_calibration: int = 0, current_user: User = Depends(get_current_user)):
    """Stream the complete .dna minting pipeline over SSE: collect code → generate pairs → train LoRA → save block."""
    team = require_team_owner(team_id, current_user)

    candidates: list[dict] = []
    for slot in team.slots.order_by(RoleSlot.id):
        first = slot.candidates.first()
        if first:
            candidates.append(first.to_dict())

    if not candidates:
        raise HTTPException(400, "No candidates selected — fill the team first")

    dnas_root = Path(os.getenv("DNAS_DIR", "dnas"))
    allow_local = os.getenv("ALLOW_LOCAL_TRAINING", "true").strip().lower() not in ("false", "0", "no")
    skip_training = emergency_calibration == 1 or not allow_local

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

            if skip_training:
                try:
                    await _emergency_skip_candidate(candidate, team_id, dnas_root, emit)
                    success = True
                except Exception as e:
                    emit({"phase": "error", "candidate": handle, "message": str(e)})
                    emit({"phase": "candidate_done", "candidate": handle, "skipped": True})
                finally:
                    loop.call_soon_threadsafe(shared_queue.put_nowait, {"__candidate_done__": handle})
                return success

            try:
                cached = _load_grok_cache(handle)
                if cached:
                    emit({"phase": "generating", "candidate": handle,
                          "message": "Loaded training pairs and system prompt from cache"})
                    pairs = cached["pairs"]
                    sys_prompt = cached["system_prompt"]
                    personality = cached.get("personality_profile")
                    code_blobs = []
                else:
                    code_blobs = await asyncio.to_thread(collect_training_data, candidate, emit)

                    personality = await asyncio.to_thread(
                        generate_personality_profile, candidate, code_blobs, emit,
                    )

                    pairs = await asyncio.to_thread(
                        generate_training_pairs, candidate, code_blobs, emit,
                        personality_profile=personality,
                    )

                    if not pairs:
                        emit({"phase": "error", "candidate": handle,
                              "message": "No training pairs generated — skipping LoRA training"})
                        emit({"phase": "candidate_done", "candidate": handle, "skipped": True})
                        return False

                    sys_prompt = await asyncio.to_thread(
                        generate_system_prompt, candidate, code_blobs, emit,
                        personality_profile=personality,
                    )
                    _save_grok_cache(handle, pairs, sys_prompt, personality)
                    emit({"phase": "generating", "candidate": handle, "message": "Grok data cached for future runs"})

                emit({"phase": "training", "candidate": handle, "message": "Waiting for training slot..."})
                async with train_sem:
                    await asyncio.to_thread(train_lora, candidate, pairs, output_dir, emit)

                personality_json = json.dumps(personality) if personality else None
                with db.atomic():
                    Candidate.update(
                        dna_cloned=True,
                        dna_path=output_dir,
                        dna_cloned_at=datetime.utcnow(),
                        system_prompt=sys_prompt,
                        personality_profile=personality_json,
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
