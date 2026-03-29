"""LoRA adapter training — trains a candidate DNA block from instruction-response pairs."""

from __future__ import annotations

import gc
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .tool_examples import TOOL_USE_EXAMPLES

logger = logging.getLogger(__name__)

BASE_INSTRUCT_RATIO = 0.5


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

    Designed to be called via asyncio.to_thread() — blocks its worker thread
    and calls emit() directly from TrainerCallback.on_log().
    """
    handle = candidate.get("github_handle", "")

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

    from .inference import model_evicted
    from .model_utils import resolve_model_path

    base_model = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")
    base_model = resolve_model_path(
        base_model,
        log=lambda msg: emit({"phase": "training", "candidate": handle, "message": msg}),
    )
    emit({"phase": "training", "candidate": handle, "message": f"Loading base model: {base_model}"})

    os.environ.setdefault("GPTQMODEL_BACKEND", "torch")

    emit({"phase": "training", "candidate": handle, "message": "Evicting inference model from VRAM for training..."})
    with model_evicted():
        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
        )
        model.config.use_cache = False

        is_quantized = getattr(model.config, "quantization_config", None) is not None
        if is_quantized:
            from peft import prepare_model_for_kbit_training
            model = prepare_model_for_kbit_training(
                model, use_gradient_checkpointing=True,
                gradient_checkpointing_kwargs={"use_reentrant": False},
            )
            emit({"phase": "training", "candidate": handle, "message": "Quantized model prepared for QLoRA"})

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=32,
            lora_alpha=128,
            lora_dropout=0.05,
            bias="none",
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        )
        model = get_peft_model(model, lora_config)
        trainable, total = model.get_nb_trainable_parameters()
        emit({
            "phase": "training",
            "candidate": handle,
            "message": f"LoRA ready — {trainable:,} trainable / {total:,} total params",
        })

        def _format(pair: dict) -> str:
            messages = [
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
        steps_per_epoch = max(1, math.ceil(len(tokenized_ds) / batch_size / gradient_accumulation_steps))
        total_steps = steps_per_epoch * num_epochs

        emit({
            "phase": "training",
            "candidate": handle,
            "message": f"Training {len(all_pairs)} total pairs × {num_epochs} epochs = ~{total_steps} steps",
            "total_steps": total_steps,
        })

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
            gradient_accumulation_steps=gradient_accumulation_steps,
            learning_rate=2e-4,
            fp16=torch.cuda.is_available(),
            logging_steps=1,
            save_strategy="no",
            report_to="none",
            dataloader_num_workers=0,
            remove_unused_columns=False,
            gradient_checkpointing=is_quantized,
            gradient_checkpointing_kwargs={"use_reentrant": False} if is_quantized else {},
            optim="paged_adamw_8bit" if is_quantized else "adamw_torch",
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
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

        del trainer
        del model
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        emit({"phase": "saving", "candidate": handle, "message": "Training VRAM freed — reloading inference model"})

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
        "rank": 32,
        "alpha": 64,
        "training_pairs": len(all_pairs),
        "candidate_pairs": len(pairs),
        "base_instruct_pairs": len(base_pairs),
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
