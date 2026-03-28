"""
DNA Trainer — collects candidate code, generates training pairs via Grok,
then trains a LoRA adapter on the base model specified in BASE_MODEL env var.

train_lora() is designed to be called via asyncio.to_thread() — it blocks its
worker thread and calls emit() directly from TrainerCallback.on_log().  The
emit callback is responsible for thread-safe delivery (e.g. loop.call_soon_threadsafe).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
GROK_MODEL = "grok-4.20-0309-non-reasoning"

# Files extensions worth fetching as training source
CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".cpp", ".c", ".h", ".rb", ".swift", ".kt", ".md", ".txt",
}

# Max bytes of code to send to Grok per repo to stay within context
MAX_CODE_BYTES = 12_000

# Number of training pairs to request per code blob
PAIRS_PER_BLOB = 6


# ── GitHub helpers ────────────────────────────────────────────────────────────

def _gh_headers() -> dict:
    token = os.getenv("GITHUB_TOKEN", "").strip()
    h = {"Accept": "application/vnd.github.v3+json"}
    if token and token.startswith("ghp_"):
        h["Authorization"] = f"token {token}"
    return h


def _gh_get(url: str, params: dict | None = None) -> dict | list | None:
    try:
        r = requests.get(url, headers=_gh_headers(), params=params, timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.warning("GitHub fetch failed: %s", e)
        return None


def _fetch_repo_code(owner: str, repo: str) -> str:
    """Fetch a meaningful slice of source code from a repo's root tree."""
    tree = _gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD", {"recursive": "1"})
    if not tree or not isinstance(tree, dict):
        return ""

    blobs: list[dict] = []
    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        path: str = item.get("path", "")
        ext = Path(path).suffix.lower()
        if ext not in CODE_EXTENSIONS:
            continue
        # Prefer root-level and src/ files, skip test/vendor dirs
        if any(skip in path for skip in ("test", "vendor", "node_modules", ".github", "dist", "__pycache__")):
            continue
        blobs.append(item)

    # Sort: prefer shorter paths (more likely to be core logic), take top 4
    blobs = sorted(blobs, key=lambda b: len(b.get("path", "")))[:4]

    code_parts: list[str] = []
    total = 0
    for blob in blobs:
        if total >= MAX_CODE_BYTES:
            break
        sha = blob.get("sha")
        path = blob.get("path", "")
        raw = _gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/git/blobs/{sha}")
        if not raw or not isinstance(raw, dict):
            continue
        encoding = raw.get("encoding")
        content_b64 = raw.get("content", "")
        if encoding == "base64":
            import base64
            try:
                content = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8", errors="replace")
            except Exception:
                continue
        else:
            content = content_b64
        snippet = content[:MAX_CODE_BYTES - total]
        code_parts.append(f"// ── {path} ──\n{snippet}")
        total += len(snippet)

    return "\n\n".join(code_parts)


# ── Grok client ───────────────────────────────────────────────────────────────

def _grok_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("XAI_API_KEY", ""),
        base_url="https://api.x.ai/v1",
    )


# ── Phase 1: collect training data ────────────────────────────────────────────

def collect_training_data(
    candidate: dict,
    emit: Callable[[dict], None],
) -> list[dict]:
    """
    For each of the candidate's top repos, fetch real source code from GitHub.
    Returns list of {"repo": str, "code": str} dicts.
    """
    handle = candidate.get("github_handle", "")
    top_repos: list[dict] = candidate.get("top_repos", [])

    if not top_repos:
        emit({"phase": "collecting", "candidate": handle, "message": "No public repos found — skipping collection"})
        return []

    results: list[dict] = []
    for repo_meta in top_repos[:3]:  # cap at 3 repos per candidate
        repo_name = repo_meta.get("name", "")
        if not repo_name:
            continue
        emit({
            "phase": "collecting",
            "candidate": handle,
            "message": f"Fetching source: {handle}/{repo_name}",
        })
        code = _fetch_repo_code(handle, repo_name)
        if code:
            emit({
                "phase": "collecting",
                "candidate": handle,
                "message": f"Got {len(code):,} bytes from {repo_name}",
            })
            results.append({"repo": repo_name, "code": code})
        else:
            emit({
                "phase": "collecting",
                "candidate": handle,
                "message": f"No code extracted from {repo_name}",
            })

    return results


# ── Phase 2: generate training pairs via Grok ─────────────────────────────────

def generate_training_pairs(
    candidate: dict,
    code_blobs: list[dict],
    emit: Callable[[dict], None],
) -> list[dict]:
    """
    Send each code blob to Grok, ask it to generate instruction→response pairs
    that capture this developer's coding style and expertise.
    Returns list of {"instruction": str, "response": str} dicts.
    """
    handle = candidate.get("github_handle", "")
    name = candidate.get("name") or handle
    skills = ", ".join(candidate.get("skills", [])[:6])
    languages = ", ".join(list(candidate.get("languages", {}).keys())[:4])

    client = _grok_client()
    all_pairs: list[dict] = []

    for blob in code_blobs:
        repo = blob["repo"]
        code = blob["code"]

        emit({
            "phase": "generating",
            "candidate": handle,
            "message": f"Generating training pairs from {repo}...",
        })

        system_prompt = (
            f"You are analyzing the code written by {name} (GitHub: @{handle}). "
            f"Their primary skills: {skills}. Languages: {languages}. "
            "Your task: generate high-quality instruction→response training pairs that capture "
            "their coding style, architecture patterns, and domain expertise. "
            "Each pair should be a realistic programming task with a response in their style."
        )

        user_prompt = (
            f"Here is real source code from their GitHub repo '{repo}':\n\n"
            f"```\n{code[:8000]}\n```\n\n"
            f"Generate exactly {PAIRS_PER_BLOB} instruction→response pairs as a JSON array. "
            "Each element must be: {\"instruction\": \"<task>\", \"response\": \"<code/answer>\"}. "
            "The instructions should be realistic engineering tasks. "
            "The responses should match this developer's actual style from the code above. "
            "Return ONLY valid JSON, no markdown fences."
        )

        try:
            resp = client.chat.completions.create(
                model=GROK_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.7,
                max_tokens=4096,
            )
            raw = resp.choices[0].message.content or ""
            # Strip markdown fences if present
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            pairs = json.loads(raw.strip())
            if isinstance(pairs, list):
                for p in pairs:
                    if isinstance(p, dict) and "instruction" in p and "response" in p:
                        all_pairs.append(p)
        except Exception as e:
            logger.warning("Grok pair generation failed for %s/%s: %s", handle, repo, e)
            emit({
                "phase": "generating",
                "candidate": handle,
                "message": f"Pair generation failed for {repo}: {e}",
            })

    emit({
        "phase": "generating",
        "candidate": handle,
        "count": len(all_pairs),
        "message": f"Generated {len(all_pairs)} training pairs",
    })
    return all_pairs


# ── Model warmup (called at server startup) ───────────────────────────────────

def warmup_model() -> None:
    """
    Download and cache the base model + tokenizer at startup so the first
    clone-dna request doesn't block waiting for a multi-GB download.
    Runs in a background thread — server stays responsive while this completes.
    """
    base_model = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    logger.info("Warmup: downloading model '%s' to HF cache...", base_model)
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        AutoModelForCausalLM.from_pretrained(base_model, trust_remote_code=True)
        logger.info("Warmup: model '%s' ready.", base_model)
    except Exception as e:
        logger.warning("Warmup: failed to pre-download model '%s': %s", base_model, e)


# ── Phase 3: LoRA training ────────────────────────────────────────────────────


def train_lora(
    candidate: dict,
    pairs: list[dict],
    output_dir: str,
    emit: Callable[[dict], None],
) -> dict:
    """
    Train a LoRA adapter on the base model using the generated pairs.
    Streams training metrics via `emit`. Saves adapter + manifest to output_dir.
    Returns a summary dict.
    """
    handle = candidate.get("github_handle", "")

    # Import here so the rest of the app works even if torch isn't installed
    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, TaskType, get_peft_model
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            DataCollatorForSeq2Seq,
            Trainer,
            TrainerCallback,
            TrainingArguments,
        )
    except ImportError as e:
        emit({"phase": "error", "candidate": handle, "message": f"Missing dependency: {e}. Install transformers, peft, torch."})
        raise

    base_model = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    emit({"phase": "training", "candidate": handle, "message": f"Loading base model: {base_model}"})

    tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=64,
        lora_alpha=128,
        lora_dropout=0.05,
        bias="none",
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, lora_config)
    trainable, total = model.get_nb_trainable_parameters()
    emit({
        "phase": "training",
        "candidate": handle,
        "message": f"LoRA ready — {trainable:,} trainable / {total:,} total params",
    })

    # Build dataset from pairs
    def _format(pair: dict) -> str:
        return (
            f"### Instruction:\n{pair['instruction']}\n\n"
            f"### Response:\n{pair['response']}\n"
        )

    MAX_LEN = 512

    def _tokenize(example: dict):
        text = _format(example)
        enc = tokenizer(
            text,
            truncation=True,
            max_length=MAX_LEN,
            padding="max_length",
        )
        enc["labels"] = enc["input_ids"].copy()
        return enc

    raw_ds = Dataset.from_list(pairs)
    tokenized_ds = raw_ds.map(_tokenize, remove_columns=raw_ds.column_names)

    num_epochs = 3
    total_steps = max(1, (len(tokenized_ds) // max(1, len(tokenized_ds))) * num_epochs)
    # More accurate: steps = ceil(len / batch) * epochs
    batch_size = 1
    steps_per_epoch = max(1, len(tokenized_ds) // batch_size)
    total_steps = steps_per_epoch * num_epochs

    emit({
        "phase": "training",
        "candidate": handle,
        "message": f"Training {len(pairs)} pairs × {num_epochs} epochs = ~{total_steps} steps",
        "total_steps": total_steps,
    })

    # Emit training metrics directly from the callback — no internal threading needed
    # because train_lora() is always called via asyncio.to_thread() and emit() is
    # thread-safe (caller uses loop.call_soon_threadsafe under the hood).
    class DirectEmitCallback(TrainerCallback):
        def on_log(self, args, state, control, logs=None, **kwargs):
            if not logs:
                return
            loss = logs.get("loss") or logs.get("train_loss")
            if loss is not None:
                emit({
                    "phase": "training",
                    "candidate": handle,
                    "step": state.global_step,
                    "total_steps": total_steps,
                    "loss": round(float(loss), 4),
                })

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=num_epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=4,
        learning_rate=2e-4,
        fp16=torch.cuda.is_available(),
        logging_steps=1,
        save_strategy="no",
        report_to="none",
        dataloader_num_workers=0,
        remove_unused_columns=False,
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_ds,
        data_collator=DataCollatorForSeq2Seq(tokenizer, model=model, padding=True),
        callbacks=[DirectEmitCallback()],
    )

    # Blocks this thread-pool worker; asyncio event loop stays free for other candidates
    trainer.train()

    # Save adapter weights
    emit({"phase": "saving", "candidate": handle, "message": f"Saving LoRA adapter to {output_dir}"})
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)

    # Write manifest
    manifest = {
        "name": f"{handle}-dna",
        "version": "1.0.0",
        "type": "candidate_dna_block",
        "candidate": {
            "handle": handle,
            "name": candidate.get("name") or handle,
            "sources": [r.get("url", "") for r in candidate.get("top_repos", [])[:3]],
            "expertise_domains": candidate.get("skills", [])[:5],
        },
        "base_model": base_model,
        "rank": 64,
        "alpha": 128,
        "training_pairs": len(pairs),
        "num_epochs": num_epochs,
        "vllm_compatible": True,
        "created": datetime.now(timezone.utc).isoformat(),
    }
    with open(Path(output_dir) / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    emit({
        "phase": "saving",
        "candidate": handle,
        "path": output_dir,
        "message": f"Saved to {output_dir}",
    })

    return manifest
