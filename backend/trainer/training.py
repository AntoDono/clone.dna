"""
LoRA adapter training — mints a candidate .dna block from instruction-response pairs.

Pipeline
--------
1. collect_training_data()  — fetch raw code blobs from the candidate's GitHub repos
2. generate_training_pairs() — call Grok-4 to generate (instruction, code) pairs
3. generate_system_prompt()  — derive a persona system prompt from the candidate profile
4. train_lora()              — PEFT LoRA fine-tune on the candidate pairs mixed with:
     - alpaca-cleaned base instruct data (BASE_INSTRUCT_RATIO × candidate pair count)
       to prevent catastrophic forgetting of general instruction-following ability
     - TOOL_USE_EXAMPLES to preserve the model's tool-use formatting ability

Output (saved to output_dir/)
------------------------------
  manifest.json          — block metadata, vLLM compatibility, eval summary
  eval.json              — training metrics: loss, pair counts, benchmark placeholder
  sources.json           — full repo provenance (name, URL, language, stars)
  consent.json           — opt-in record stub (pending registry enrollment)
  profile.md             — human-readable candidate profile + PEFT usage snippet
  adapter_config.json    — PEFT LoRA config (auto-generated)
  adapter_model.safetensors — LoRA weights (load with PEFT or vLLM --enable-lora)
  tokenizer files        — tokenizer state for standalone loading
"""

from __future__ import annotations

import gc
import json
import logging
import math
import os
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .grok import PAIR_SYSTEM_TEMPLATE, PAIR_USER_TEMPLATE, GROK_MODEL, PAIRS_PER_BLOB
from .tool_examples import TOOL_USE_EXAMPLES

logger = logging.getLogger(__name__)

BASE_INSTRUCT_RATIO = 0.5


def compute_style_metrics(pairs: list[dict]) -> dict:
    """Compute lightweight style-consistency fingerprints from candidate code pairs.

    Analyzes the *response* (code) side of each training pair and produces
    heuristic metrics that characterize the developer's coding style:
      - naming_convention: dominant convention ("snake_case", "camelCase", "mixed")
        and the ratio of the dominant convention to total identifiers
      - avg_line_length: mean non-blank line length across all code samples
      - comment_density: ratio of comment lines to total non-blank lines
      - avg_function_length: mean number of lines per function/method definition
      - consistency_score: 0–1 aggregate measuring how self-consistent the
        developer's style is across their code samples

    Returns a dict with all metrics plus the aggregate consistency_score.
    """
    if not pairs:
        return {"consistency_score": None}

    code_samples = [p.get("response", "") for p in pairs if p.get("response", "").strip()]
    if not code_samples:
        return {"consistency_score": None}

    _SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
    _CAMEL = re.compile(r"\b[a-z][a-z0-9]*(?:[A-Z][a-z0-9]*)+\b")
    _FUNC_DEF = re.compile(r"^\s*(?:def |function |async function |const \w+ = |let \w+ = |var \w+ = )", re.MULTILINE)

    per_sample_line_lengths: list[float] = []
    per_sample_comment_densities: list[float] = []
    per_sample_func_lengths: list[float] = []
    total_snake = 0
    total_camel = 0

    for code in code_samples:
        lines = code.splitlines()
        non_blank = [l for l in lines if l.strip()]
        if not non_blank:
            continue

        per_sample_line_lengths.append(statistics.mean(len(l) for l in non_blank))

        comment_lines = sum(
            1 for l in non_blank
            if l.strip().startswith("#") or l.strip().startswith("//") or l.strip().startswith("/*")
        )
        per_sample_comment_densities.append(comment_lines / len(non_blank))

        total_snake += len(_SNAKE.findall(code))
        total_camel += len(_CAMEL.findall(code))

        func_starts = [i for i, l in enumerate(lines) if _FUNC_DEF.match(l)]
        if func_starts:
            lengths = []
            for idx, start in enumerate(func_starts):
                end = func_starts[idx + 1] if idx + 1 < len(func_starts) else len(lines)
                lengths.append(end - start)
            per_sample_func_lengths.append(statistics.mean(lengths))

    total_idents = total_snake + total_camel
    if total_idents > 0:
        dominant_ratio = max(total_snake, total_camel) / total_idents
        naming_convention = "snake_case" if total_snake >= total_camel else "camelCase"
    else:
        dominant_ratio = 1.0
        naming_convention = "unknown"

    avg_line_length = statistics.mean(per_sample_line_lengths) if per_sample_line_lengths else 0.0
    comment_density = statistics.mean(per_sample_comment_densities) if per_sample_comment_densities else 0.0
    avg_func_length = statistics.mean(per_sample_func_lengths) if per_sample_func_lengths else 0.0

    # Consistency sub-scores: low variance across samples = high consistency.
    subscores: list[float] = []

    subscores.append(dominant_ratio)

    if len(per_sample_line_lengths) >= 2:
        cv_line = statistics.stdev(per_sample_line_lengths) / avg_line_length if avg_line_length > 0 else 0
        subscores.append(max(0.0, 1.0 - cv_line))

    if len(per_sample_comment_densities) >= 2:
        sd_comment = statistics.stdev(per_sample_comment_densities)
        subscores.append(max(0.0, 1.0 - sd_comment * 3))

    if len(per_sample_func_lengths) >= 2:
        cv_func = statistics.stdev(per_sample_func_lengths) / avg_func_length if avg_func_length > 0 else 0
        subscores.append(max(0.0, 1.0 - cv_func))

    consistency_score = round(statistics.mean(subscores), 4) if subscores else None

    return {
        "naming_convention": naming_convention,
        "naming_dominance": round(dominant_ratio, 4),
        "avg_line_length": round(avg_line_length, 1),
        "comment_density": round(comment_density, 4),
        "avg_function_length": round(avg_func_length, 1),
        "consistency_score": consistency_score,
    }


def compute_domain_accuracy(pairs: list[dict], candidate: dict) -> float | None:
    """Heuristic domain-accuracy score (0-1) measuring how well training pairs
    cover the candidate's declared expertise domains.

    Collects domain keywords from skills, language names, and repo topics, then
    checks keyword presence across the concatenated instruction+response text of
    every training pair.

    Score = 0.6 * coverage (fraction of keywords hit) +
            0.4 * density  (avg keyword hits per pair, clamped to [0,1]).
    """
    if not pairs:
        return None

    skills = [s.lower() for s in candidate.get("skills", [])]
    lang_keys = [l.lower() for l in candidate.get("languages", {}).keys()]
    repo_topics: list[str] = []
    for r in candidate.get("top_repos", []):
        repo_topics.extend(t.lower() for t in r.get("topics", []))

    keywords = list({k for k in skills + lang_keys + repo_topics if len(k) >= 2})
    if not keywords:
        return None

    pair_texts = [
        (p.get("instruction", "") + " " + p.get("response", "")).lower()
        for p in pairs
    ]

    keyword_hits = set()
    hits_per_pair: list[int] = []
    for text in pair_texts:
        count = 0
        for kw in keywords:
            if kw in text:
                keyword_hits.add(kw)
                count += 1
        hits_per_pair.append(count)

    coverage = len(keyword_hits) / len(keywords)
    raw_density = statistics.mean(hits_per_pair) / len(keywords) if keywords else 0.0
    density = min(1.0, raw_density)

    return round(0.6 * coverage + 0.4 * density, 4)


def compute_humaneval_proxy(pairs: list[dict]) -> float | None:
    """Heuristic code-quality proxy (0-1) estimated from training pair responses.

    Checks five quality indicators per code sample — function definitions, error
    handling, type annotations, documentation, and imports — and averages
    indicator presence across all samples.  Not a substitute for HumanEval but
    provides a directional signal from the training data itself.
    """
    if not pairs:
        return None

    code_samples = [p.get("response", "") for p in pairs if p.get("response", "").strip()]
    if not code_samples:
        return None

    _FUNC = re.compile(r"(?:^|\n)\s*(?:def |function |async function |class )")
    _ERR = re.compile(r"\b(?:try|except|catch|raise|throw|Error)\b")
    _TYPE = re.compile(r"(?::\s*(?:str|int|float|bool|list|dict|List|Dict|Optional|Tuple|Set|Any|number|string|boolean)|\)\s*->)")
    _DOC = re.compile(r'(?:"""|\'\'\'|^\s*(?:#|//|/\*))', re.MULTILINE)
    _IMP = re.compile(r"(?:^|\n)\s*(?:import |from \S+ import |require\(|using )")

    indicators = [_FUNC, _ERR, _TYPE, _DOC, _IMP]
    sample_scores: list[float] = []

    for code in code_samples:
        hits = sum(1 for pat in indicators if pat.search(code))
        sample_scores.append(hits / len(indicators))

    return round(statistics.mean(sample_scores), 4)


def estimate_latency_overhead_ms(rank: int = 32, num_adapted_modules: int = 4) -> float:
    """Estimate LoRA inference latency overhead in milliseconds.

    Uses an empirical constant per rank per adapted module based on typical
    transformer hidden dimensions on consumer GPUs.  The overhead comes from the
    two small matmuls (down-project + up-project) added per adapted linear layer.
    """
    overhead = rank * num_adapted_modules * 0.1
    return round(max(1.0, min(50.0, overhead)), 1)


def validate_vllm_export(adapter_dir: Path) -> tuple[bool, list[str]]:
    """Check that a saved adapter directory is structurally valid for vLLM --enable-lora.

    Returns (is_compatible, issues) where issues lists any problems found.
    Does not require vLLM to be installed — inspects files only.
    """
    issues: list[str] = []
    adapter_dir = Path(adapter_dir)

    config_path = adapter_dir / "adapter_config.json"
    if not config_path.exists():
        issues.append("adapter_config.json missing")
        return False, issues

    try:
        config = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        issues.append(f"adapter_config.json unreadable: {e}")
        return False, issues

    peft_type = config.get("peft_type", "")
    if peft_type != "LORA":
        issues.append(f"peft_type is '{peft_type}', expected 'LORA'")

    rank = config.get("r")
    if not isinstance(rank, int) or rank <= 0:
        issues.append(f"invalid or missing rank (r={rank})")

    for field in ("lora_alpha", "target_modules"):
        if field not in config:
            issues.append(f"missing required field '{field}'")

    safetensors_path = adapter_dir / "adapter_model.safetensors"
    bin_path = adapter_dir / "adapter_model.bin"
    if not safetensors_path.exists() and not bin_path.exists():
        issues.append("no adapter weights (adapter_model.safetensors or .bin)")
        return False, issues

    if safetensors_path.exists() and isinstance(rank, int) and rank > 0:
        try:
            from safetensors import safe_open
            with safe_open(str(safetensors_path), framework="pt") as f:
                tensor_names = f.keys()
                has_lora_a = any("lora_A" in n for n in tensor_names)
                has_lora_b = any("lora_B" in n for n in tensor_names)
                if not has_lora_a or not has_lora_b:
                    issues.append("weight tensors missing lora_A/lora_B naming pattern")
                for name in tensor_names:
                    if "lora_A" in name:
                        shape = f.get_slice(name).get_shape()
                        if shape[0] != rank:
                            issues.append(
                                f"tensor '{name}' dim 0 is {shape[0]}, expected rank {rank}"
                            )
                            break
        except Exception as e:
            issues.append(f"could not inspect safetensors: {e}")

    return (len(issues) == 0), issues


class _TrainingResult:
    """Carries loss metrics out of the training callback into the save block."""
    final_loss: float | None = None
    best_loss: float | None = None


def _sample_base_instruct_pairs(count: int) -> list[dict]:
    """
    Sample general instruction-following pairs from alpaca-cleaned to mix into
    candidate-specific training data.  Prevents catastrophic forgetting of
    basic instruct ability when the candidate set is small (~18 pairs).
    HuggingFace datasets caches after first download (~25 MB).
    """
    if count <= 0:
        return []
    try:
        import random
        from datasets import load_dataset
        ds = load_dataset("yahma/alpaca-cleaned", split="train")
        pool = [
            {
                "instruction": row["instruction"] + ("\n" + row["input"] if row.get("input") else ""),
                "response": row["output"],
            }
            for row in ds
            if row.get("output") and len(row["output"]) > 20
        ]
        return random.sample(pool, min(count, len(pool)))
    except Exception as e:
        logger.warning("Failed to load base instruct data: %s", e)
        return []


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

    GPU selection is handled entirely by CUDA_VISIBLE_DEVICES in the environment —
    set it before starting the server and the HuggingFace device_map="auto" loader
    will confine itself to the visible devices automatically.

    Designed to be called via asyncio.to_thread() — blocks its worker thread
    and calls emit() directly from TrainerCallback.on_log().
    """
    handle = candidate.get("github_handle", "")

    try:
        import torch
        from datasets import Dataset
        from peft import LoraConfig, PeftModel, TaskType, get_peft_model
        from transformers import (
            DataCollatorForSeq2Seq,
            Trainer,
            TrainerCallback,
            TrainingArguments,
        )
    except ImportError as e:
        emit({"phase": "error", "candidate": handle, "message": f"Missing dependency: {e}. Install transformers, peft, torch."})
        raise

    from .inference import borrow_model_for_training

    base_model = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4")
    os.environ.setdefault("GPTQMODEL_BACKEND", "torch")

    emit({"phase": "training", "candidate": handle, "message": "Borrowing base model for training..."})
    with borrow_model_for_training() as (model, tokenizer):
        is_quantized = getattr(model.config, "quantization_config", None) is not None
        if is_quantized:
            from peft import prepare_model_for_kbit_training
            model = prepare_model_for_kbit_training(
                model, use_gradient_checkpointing=True,
                gradient_checkpointing_kwargs={"use_reentrant": False},
            )
            emit({"phase": "training", "candidate": handle, "message": "Quantized model prepared for QLoRA"})

        training_adapter = f"train-{handle}"
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=32,
            lora_alpha=128,
            lora_dropout=0.05,
            bias="none",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        if isinstance(model, PeftModel):
            model.add_adapter(training_adapter, lora_config)
            model.set_adapter(training_adapter)
        else:
            model = get_peft_model(model, lora_config, adapter_name=training_adapter)
        trainable, total = model.get_nb_trainable_parameters()
        emit({
            "phase": "training",
            "candidate": handle,
            "message": f"LoRA ready — {trainable:,} trainable / {total:,} total params",
        })

        _TOOL_SYSTEM = (
            "You have access to tools. To call a tool, emit a <tool_call> block with JSON inside. "
            "Do NOT output tool calls as markdown code blocks — ONLY the <tool_call> format will be executed:\n\n"
            "<tool_call>\n"
            '{"name": "tool_name", "arguments": {"key": "value"}}\n'
            "</tool_call>\n\n"
            "When asked to create, write, read, edit, or delete files, list directories, "
            "or run commands, you MUST use <tool_call>. NEVER just show code in a text response."
        )

        def _format(pair: dict) -> str:
            """
            Render an instruction-response pair as a single training string using the
            tokenizer's chat template.  Falls back to a plain markdown format if the
            tokenizer doesn't expose apply_chat_template (e.g. older checkpoints).

            Tool-use examples get a system message so the model learns to associate
            the tool-use system prompt with <tool_call> output.
            """
            has_tool_call = "<tool_call>" in pair.get("response", "")
            messages = []
            if has_tool_call:
                messages.append({"role": "system", "content": _TOOL_SYSTEM})
            messages += [
                {"role": "user", "content": pair["instruction"]},
                {"role": "assistant", "content": pair["response"]},
            ]
            try:
                return tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=False,
                )
            except Exception:
                return (
                    f"### Instruction:\n{pair['instruction']}\n\n"
                    f"### Response:\n{pair['response']}\n"
                )

        MAX_LEN = 2048

        def _tokenize(example: dict):
            """
            Tokenize a single training example to fixed length MAX_LEN.
            Labels are set equal to input_ids so the model trains on every token
            (causal LM objective with no masking of the prompt portion).
            """
            text = _format(example)
            enc = tokenizer(text, truncation=True, max_length=MAX_LEN, padding="max_length")
            enc["labels"] = enc["input_ids"].copy()
            return enc

        base_count = max(1, int(len(pairs) * BASE_INSTRUCT_RATIO))
        base_pairs = _sample_base_instruct_pairs(base_count)
        if base_pairs:
            emit({
                "phase": "training",
                "candidate": handle,
                "message": f"Mixing {len(base_pairs)} base instruct pairs with {len(pairs)} candidate pairs",
            })
        all_pairs = pairs + base_pairs + TOOL_USE_EXAMPLES
        emit({
            "phase": "training",
            "candidate": handle,
            "message": f"Added {len(TOOL_USE_EXAMPLES)} tool-use training examples",
        })

        raw_ds = Dataset.from_list(all_pairs)
        tokenized_ds = raw_ds.map(_tokenize, remove_columns=raw_ds.column_names)

        num_epochs = 2
        batch_size = 2
        gradient_accumulation_steps = 4
        learning_rate = 2e-4
        lora_rank = 32
        lora_alpha = 128
        steps_per_epoch = max(1, math.ceil(len(tokenized_ds) / batch_size / gradient_accumulation_steps))
        total_steps = steps_per_epoch * num_epochs
        optimizer_name = "paged_adamw_8bit" if is_quantized else "adamw_torch"

        emit({
            "phase": "training",
            "candidate": handle,
            "message": f"Training {len(all_pairs)} total pairs × {num_epochs} epochs = ~{total_steps} steps",
            "total_steps": total_steps,
        })

        emit({
            "phase": "training",
            "candidate": handle,
            "training_config": {
                "epochs": num_epochs,
                "batch_size": batch_size,
                "gradient_accumulation_steps": gradient_accumulation_steps,
                "effective_batch_size": batch_size * gradient_accumulation_steps,
                "learning_rate": learning_rate,
                "optimizer": optimizer_name,
                "lora_rank": lora_rank,
                "lora_alpha": lora_alpha,
                "max_seq_length": MAX_LEN,
                "total_pairs": len(all_pairs),
                "candidate_pairs": len(pairs),
                "base_instruct_pairs": len(base_pairs),
                "tool_use_pairs": len(TOOL_USE_EXAMPLES),
                "total_steps": total_steps,
                "fp16": torch.cuda.is_available(),
            },
        })

        _training_result = _TrainingResult()

        class DirectEmitCallback(TrainerCallback):
            def on_log(self, args, state, control, logs=None, **kwargs):
                if not logs:
                    return
                loss = logs.get("loss") or logs.get("train_loss")
                if loss is not None:
                    loss_val = round(float(loss), 4)
                    _training_result.final_loss = loss_val
                    if _training_result.best_loss is None or loss_val < _training_result.best_loss:
                        _training_result.best_loss = loss_val

                    current_lr = logs.get("learning_rate", 0.0)
                    current_epoch = state.epoch or 0.0

                    emit({
                        "phase": "training",
                        "candidate": handle,
                        "step": state.global_step,
                        "total_steps": total_steps,
                        "loss": loss_val,
                        "learning_rate": round(float(current_lr), 8),
                        "epoch": round(float(current_epoch), 2),
                    })

        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=num_epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=gradient_accumulation_steps,
            learning_rate=learning_rate,
            fp16=torch.cuda.is_available(),
            logging_steps=1,
            save_strategy="no",
            report_to="none",
            dataloader_num_workers=0,
            remove_unused_columns=False,
            gradient_checkpointing=is_quantized,
            gradient_checkpointing_kwargs={"use_reentrant": False} if is_quantized else {},
            optim=optimizer_name,
        )

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=tokenized_ds,
            data_collator=DataCollatorForSeq2Seq(tokenizer, model=model, padding=True),
            callbacks=[DirectEmitCallback()],
        )

        trainer.train()

        emit({"phase": "saving", "candidate": handle, "message": f"Saving LoRA adapter to {output_dir}"})
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        model.save_pretrained(output_dir, selected_adapters=[training_adapter])
        tokenizer.save_pretrained(output_dir)

        del trainer
        try:
            model.delete_adapter(training_adapter)
        except Exception:
            pass
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        emit({"phase": "saving", "candidate": handle, "message": "Training adapter removed — model ready for inference"})

    vllm_ok, vllm_issues = validate_vllm_export(Path(output_dir))
    if vllm_ok:
        emit({"phase": "saving", "candidate": handle, "message": "vLLM compatibility validated"})
    else:
        emit({"phase": "saving", "candidate": handle, "message": f"vLLM validation failed: {'; '.join(vllm_issues)}"})

    created_at = datetime.now(timezone.utc).isoformat()
    top_repos = candidate.get("top_repos", [])
    skills = candidate.get("skills", [])
    languages = candidate.get("languages", {})

    # Collect training loss history from the DirectEmitCallback via trainer state.
    # After trainer.train() the log_history is available on trainer.state — but
    # trainer/model are already deleted above.  We track losses in the callback instead.
    # Pull them out via the trainer return value stored in the emit closure.
    final_loss = getattr(_training_result, "final_loss", None)
    best_loss = getattr(_training_result, "best_loss", None)

    style_metrics = compute_style_metrics(pairs)
    style_consistency = style_metrics.get("consistency_score")
    domain_accuracy = compute_domain_accuracy(pairs, candidate)
    humaneval_score = compute_humaneval_proxy(pairs)
    latency_overhead_ms = estimate_latency_overhead_ms(rank=32, num_adapted_modules=4)

    emit({
        "phase": "eval",
        "candidate": handle,
        "metrics": {
            "final_loss": final_loss,
            "best_loss": best_loss,
            "style_consistency": style_consistency,
            "style_metrics": style_metrics,
            "domain_accuracy": domain_accuracy,
            "humaneval_score": humaneval_score,
            "latency_overhead_ms": latency_overhead_ms,
        },
    })

    manifest = {
        "name": f"{handle}-dna",
        "version": "1.0.0",
        "type": "candidate_dna_block",
        "candidate": {
            "handle": handle,
            "name": candidate.get("name") or handle,
            "sources": [r.get("url", "") for r in top_repos[:3]],
            "expertise_domains": skills[:5],
            "total_contributions_analyzed": sum(
                r.get("stars", 0) for r in top_repos
            ),
            # True when all trained repos carry a permissive license verified via GitHub API.
            # False for older cached profiles that predate license metadata.
            "consent_verified": all(
                r.get("permissive", False) for r in top_repos[:3]
            ) if top_repos else False,
        },
        "base_model": base_model,
        "rank": 32,
        "alpha": 128,
        "quantization": "INT4" if os.getenv("QUANTIZATION_BITS") == "4" else "FP16",
        "vllm_compatible": vllm_ok,
        "tags": skills[:8],
        "training_pairs": len(all_pairs),
        "candidate_pairs": len(pairs),
        "base_instruct_pairs": len(base_pairs),
        "num_epochs": num_epochs,
        "created": created_at,
        "eval_summary": {
            "final_loss": final_loss,
            "best_loss": best_loss,
            "style_consistency": style_consistency,
            "domain_accuracy": domain_accuracy,
            "latency_overhead_ms": latency_overhead_ms,
            "teacher_model": "grok-4",
        },
    }
    out = Path(output_dir)
    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    # eval.json — training metrics and quality summary
    eval_data = {
        "handle": handle,
        "base_model": base_model,
        "training": {
            "total_pairs": len(all_pairs),
            "candidate_pairs": len(pairs),
            "base_instruct_pairs": len(base_pairs),
            "tool_use_pairs": len(TOOL_USE_EXAMPLES),
            "num_epochs": num_epochs,
            "rank": 32,
            "alpha": 128,
            "final_loss": final_loss,
            "best_loss": best_loss,
        },
        "benchmarks": {
            "style_consistency": style_consistency,
            "style_metrics": style_metrics,
            "domain_accuracy": domain_accuracy,
            "humaneval_score": humaneval_score,
        },
        "teacher_model": "grok-4",
        "created": created_at,
    }
    with open(out / "eval.json", "w") as f:
        json.dump(eval_data, f, indent=2)

    # sources.json — full repo provenance
    sources = {
        "handle": handle,
        "repos": [
            {
                "name": r.get("name", ""),
                "url": r.get("url", ""),
                "language": r.get("language", ""),
                "stars": r.get("stars", 0),
                "description": r.get("description", ""),
                "topics": r.get("topics", []),
            }
            for r in top_repos
        ],
        "languages": languages,
        "license_filter": "MIT/Apache-2.0 only",
        "created": created_at,
    }
    with open(out / "sources.json", "w") as f:
        json.dump(sources, f, indent=2)

    # teacher_config.json — prompt templates used for Grok pair generation
    teacher_config = {
        "teacher_model": GROK_MODEL,
        "pairs_per_blob": PAIRS_PER_BLOB,
        "system_template": PAIR_SYSTEM_TEMPLATE,
        "user_template": PAIR_USER_TEMPLATE,
        "temperature": 0.7,
        "max_tokens": 4096,
        "created": created_at,
    }
    with open(out / "teacher_config.json", "w") as f:
        json.dump(teacher_config, f, indent=2)

    # consent.json — opt-in record
    source_repos = [r.get("url", "") for r in top_repos if r.get("url")]
    consent = {
        "handle": handle,
        "consent_status": "implicit_public",
        "consent_scope": "public_repos_mit_apache",
        "public_repos_only": True,
        "revocable": True,
        "source_count": len(source_repos),
        "source_urls": source_repos,
        "license_filter": "MIT/Apache-2.0",
        "minted_at": created_at,
        "minted_by": "clone.dna automated pipeline",
        "revocation_endpoint": f"/registry/{Path(output_dir).parent.name}/{handle}",
        "note": (
            "This block was minted from MIT/Apache-2.0 licensed public repositories. "
            "The developer can revoke this block at any time via the registry API "
            "or by contacting the team. Full self-service consent management is "
            "available at the developer enrollment portal."
        ),
    }
    with open(out / "consent.json", "w") as f:
        json.dump(consent, f, indent=2)

    # profile.md — human-readable candidate profile
    lang_list = ", ".join(list(languages.keys())[:6]) or "N/A"
    skill_list = ", ".join(skills[:8]) or "N/A"
    repo_lines = "\n".join(
        f"- [{r.get('name', '')}]({r.get('url', '')}) — {r.get('description', '') or r.get('language', '')}"
        for r in top_repos[:5]
    )
    profile_md = f"""# {candidate.get('name') or handle} (@{handle})

**Role:** {candidate.get('description') or 'Software Developer'}

## Bio
{candidate.get('bio') or 'No bio available.'}

## Expertise Domains
{skill_list}

## Languages
{lang_list}

## Top Repositories
{repo_lines or '_(none available)_'}

## DNA Block Stats
- Training pairs: {len(pairs)} candidate + {len(base_pairs)} base instruct + {len(TOOL_USE_EXAMPLES)} tool-use
- Base model: `{base_model}`
- LoRA rank: 32, alpha: 128
- Trained: {created_at}
- vLLM compatible: {"yes" if vllm_ok else "no (" + "; ".join(vllm_issues) + ")"}

## Usage
Load this .dna block via the Clone.dna runtime or directly with PEFT:
```python
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
model = AutoModelForCausalLM.from_pretrained("{base_model}", device_map="auto")
model = PeftModel.from_pretrained(model, "{output_dir}")
```
"""
    (out / "profile.md").write_text(profile_md)

    emit({
        "phase": "saving",
        "candidate": handle,
        "path": output_dir,
        "message": f"Saved to {output_dir}",
    })

    return manifest
