"""
DNA Inference — loads the base model once and hot-swaps LoRA adapters per candidate.

stream_chat() is designed to be called via asyncio.to_thread().  The caller
passes a thread-safe emit callback; tokens are yielded synchronously here and
the caller forwards them to the asyncio SSE queue.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Generator

logger = logging.getLogger(__name__)

# ── Module-level model cache ──────────────────────────────────────────────────
# Shared across all inference calls in this process.  Protected by a lock so
# concurrent requests don't double-load the base model.

_cache_lock = threading.Lock()
_base: dict = {}               # {"model": ..., "tokenizer": ...}
_adapters_loaded: set[str] = set()   # set of adapter names already registered


def _base_model_name() -> str:
    return os.getenv("BASE_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")


def ensure_base_model() -> tuple:
    """Load base model + tokenizer into cache if not already done. Thread-safe."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    with _cache_lock:
        if "model" not in _base:
            name = _base_model_name()
            logger.info("Inference: loading base model '%s'...", name)
            tokenizer = AutoTokenizer.from_pretrained(name, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token
            model = AutoModelForCausalLM.from_pretrained(
                name,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                device_map="auto",
                trust_remote_code=True,
            )
            model.eval()
            _base["model"] = model
            _base["tokenizer"] = tokenizer
            logger.info("Inference: base model ready.")
        return _base["model"], _base["tokenizer"]


def load_adapter(lora_path: str, adapter_name: str) -> None:
    """Register a LoRA adapter on the cached model if not already loaded."""
    model, _ = ensure_base_model()
    with _cache_lock:
        if adapter_name not in _adapters_loaded:
            logger.info("Inference: loading adapter '%s' from %s", adapter_name, lora_path)
            model.load_adapter(lora_path, adapter_name=adapter_name)
            _adapters_loaded.add(adapter_name)


# ── System prompt builder ─────────────────────────────────────────────────────

def _build_system_prompt(handle: str, name: str, role: str, profile: dict) -> str:
    skills = ", ".join((profile.get("skills") or [])[:6])
    bio = (profile.get("bio") or "").strip()
    languages = ", ".join(list((profile.get("languages") or {}).keys())[:4])
    role_label = {"pm": "Product Manager", "swe": "Software Engineer", "designer": "Designer"}.get(role, role)

    lines = [
        f"You are {name} (@{handle}), a {role_label}.",
        f"Primary skills: {skills}." if skills else "",
        f"Languages: {languages}." if languages else "",
        f'Bio: "{bio}"' if bio else "",
        "",
        "You are part of a software team. Respond as this specific person — "
        "use their coding style, domain expertise, and communication patterns. "
        "Be concise, technical, and in character.",
    ]
    return "\n".join(l for l in lines if l or l == "")


# ── Chat history formatter ────────────────────────────────────────────────────

def _format_messages(system_prompt: str, history: list[dict]) -> str:
    """Format history into a simple prompt string compatible with most causal LMs."""
    parts = [f"<|system|>\n{system_prompt}\n"]
    for msg in history:
        role = msg.get("sender", "user")
        content = msg.get("content", "")
        if role == "user":
            parts.append(f"<|user|>\n{content}\n")
        else:
            parts.append(f"<|assistant|>\n{content}\n")
    parts.append("<|assistant|>\n")
    return "".join(parts)


# ── Main streaming function ───────────────────────────────────────────────────

def stream_chat(
    lora_path: str,
    adapter_name: str,
    role: str,
    profile: dict,
    history: list[dict],
    emit: Callable[[dict], None],
    max_new_tokens: int = 512,
) -> str:
    """
    Activate the candidate's LoRA adapter and generate a streaming response.

    `history` is a list of {"sender": "user"|handle, "content": "..."} dicts
    in chronological order.  The last entry must be the user's latest message.

    Calls emit({"token": "..."}) for each generated token.
    Returns the full response string.
    """
    import torch
    from transformers import TextIteratorStreamer

    model, tokenizer = ensure_base_model()
    load_adapter(lora_path, adapter_name)

    name = profile.get("name") or adapter_name
    system_prompt = _build_system_prompt(adapter_name, name, role, profile)
    prompt = _format_messages(system_prompt, history)

    inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

    streamer = TextIteratorStreamer(
        tokenizer,
        skip_prompt=True,
        skip_special_tokens=True,
    )

    generate_kwargs = {
        **inputs,
        "streamer": streamer,
        "max_new_tokens": max_new_tokens,
        "do_sample": True,
        "temperature": 0.7,
        "top_p": 0.9,
        "pad_token_id": tokenizer.eos_token_id,
    }

    # Activate the correct LoRA adapter
    with _cache_lock:
        model.set_adapter(adapter_name)

    # Run generation in a thread (TextIteratorStreamer bridges the gap)
    gen_thread = threading.Thread(
        target=lambda: model.generate(**generate_kwargs),
        daemon=True,
    )
    gen_thread.start()

    full_response = ""
    for token_text in streamer:
        if token_text:
            full_response += token_text
            emit({"token": token_text})

    gen_thread.join()
    return full_response
