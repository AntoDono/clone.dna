"""
DNA Inference — loads the base model once and hot-swaps LoRA adapters per candidate.

stream_chat() is designed to be called via asyncio.to_thread().  The caller
passes a thread-safe emit callback; tokens are yielded synchronously here and
the caller forwards them to the asyncio SSE queue.

agent_chat() wraps stream_chat in an iterative tool-use loop: generate, detect
<tool_call> blocks, execute tools, feed results back, and regenerate.
"""

from __future__ import annotations

import gc
import json
import logging
import os
import re
import threading
from contextlib import contextmanager
from typing import Callable

from pathlib import Path

import torch

logger = logging.getLogger(__name__)

# ── Module-level model cache ──────────────────────────────────────────────────

_cache_lock = threading.Lock()
_base: dict = {}
_adapters_loaded: set[str] = set()
_training_count: int = 0  # number of training jobs currently holding the eviction lock


@contextmanager
def borrow_model_for_training():
    """Borrow the cached base model for training — no eviction, no reload.

    1. Ensures the base model is loaded.
    2. Detaches any inference LoRA adapter.
    3. Puts the model into training-ready state (train mode, use_cache=False).
    4. Yields (model, tokenizer) to the caller.
    5. On exit, restores inference state (eval mode, use_cache=True).
    """
    global _training_count

    model, tokenizer = ensure_base_model()

    with _cache_lock:
        _training_count += 1
        for old in list(_adapters_loaded):
            try:
                model.delete_adapter(old)
            except Exception:
                pass
        _adapters_loaded.clear()

    model.config.use_cache = False
    model.train()

    try:
        yield model, tokenizer
    finally:
        model.config.use_cache = True
        model.eval()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        with _cache_lock:
            _training_count -= 1


def _base_model_name() -> str:
    """Return the configured base model name from BASE_MODEL env var, or the default Qwen model."""
    return os.getenv("BASE_MODEL", "Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4")


_load_lock = threading.Lock()


def ensure_base_model() -> tuple:
    """Load base model + tokenizer into cache if not already done. Thread-safe.

    If a training job is currently active (_training_count > 0) the reload is
    skipped — the last training job to exit will call ensure_base_model() itself
    once _training_count drops to 0, so inference will still be restored.

    Uses a separate _load_lock so the heavy from_pretrained() call doesn't
    block callers that just need to read the already-loaded cache via _cache_lock.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer

    with _cache_lock:
        if _training_count > 0:
            logger.info(
                "Inference: skipping model reload — %d training job(s) still active",
                _training_count,
            )
            return _base.get("model"), _base.get("tokenizer")
        if "model" in _base:
            return _base["model"], _base["tokenizer"]

    with _load_lock:
        with _cache_lock:
            if "model" in _base:
                return _base["model"], _base["tokenizer"]

        name = _base_model_name()
        from .model_utils import resolve_model_path
        model_path = resolve_model_path(name, log=lambda msg: logger.info("Inference: %s", msg))
        logger.info("Inference: loading base model '%s'...", model_path)
        tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            model_path,
            torch_dtype="auto",
            device_map="auto",
            trust_remote_code=True,
        )
        model.eval()

        with _cache_lock:
            _base["model"] = model
            _base["tokenizer"] = tokenizer
        logger.info("Inference: base model ready.")
        return model, tokenizer


_NO_ADAPTER = "__raw__"


def load_adapter(lora_path: str, adapter_name: str) -> None:
    """
    Load a LoRA adapter, evicting any previously loaded adapter first.
    GPTQ-quantized models don't support multiple concurrent LoRA adapters
    (PEFT randomly initialises the first adapter's weights on layers created
    for the second), so we keep exactly one adapter resident at a time.

    If the adapter directory is missing or has no weights, falls back to the
    raw base model so inference still works without a trained LoRA.
    """
    adapter_dir = Path(lora_path)
    has_weights = adapter_dir.is_dir() and any(adapter_dir.glob("adapter_model*"))

    model, _ = ensure_base_model()
    with _cache_lock:
        target = adapter_name if has_weights else _NO_ADAPTER
        if target in _adapters_loaded:
            return
        for old in list(_adapters_loaded):
            if old == _NO_ADAPTER:
                continue
            logger.info("Inference: unloading adapter '%s' before swap", old)
            try:
                model.delete_adapter(old)
            except Exception:
                pass
        _adapters_loaded.clear()

        if not has_weights:
            logger.info("Inference: no adapter weights at '%s' — using raw base model", lora_path)
            _adapters_loaded.add(_NO_ADAPTER)
            return

        logger.info("Inference: loading adapter '%s' from %s", adapter_name, lora_path)
        model.load_adapter(lora_path, adapter_name=adapter_name)
        _adapters_loaded.add(adapter_name)


def load_blended_adapter(
    primary_path: str,
    primary_name: str,
    secondary_path: str,
    secondary_name: str,
    primary_weight: float = 0.7,
) -> str:
    """Create a transient LoRA adapter by linearly interpolating two adapters in weight space.

    Uses PEFT's add_weighted_adapter(combination_type="linear") to produce a merged
    adapter whose lora_A / lora_B matrices are weighted sums of the source matrices:

        delta_W_merged = primary_weight * (B_p @ A_p) + (1 - primary_weight) * (B_s @ A_s)

    The primary adapter (specialist) dominates; the secondary (PM) contributes its
    framing at (1 - primary_weight). The result is a single adapter — the PM's
    architectural vocabulary is encoded in the weights, not injected as tokens.

    Both source adapters are evicted after merging; only the blended adapter remains.
    Falls back to primary-only loading if either source has no weights or if PEFT
    rejects the merge (e.g. incompatible target modules between the two adapters).

    Returns the merged adapter name (or primary_name on fallback).
    """
    primary_dir = Path(primary_path)
    secondary_dir = Path(secondary_path)
    primary_has_weights = primary_dir.is_dir() and any(primary_dir.glob("adapter_model*"))
    secondary_has_weights = secondary_dir.is_dir() and any(secondary_dir.glob("adapter_model*"))

    if not primary_has_weights or not secondary_has_weights or primary_name == secondary_name:
        load_adapter(primary_path, primary_name)
        return primary_name

    model, _ = ensure_base_model()
    merged_name = f"blend_{primary_name}_x_{secondary_name}"

    with _cache_lock:
        # The merged adapter is a specialisation of (primary, secondary) — serve cached.
        if merged_name in _adapters_loaded:
            model.set_adapter(merged_name)
            return merged_name
        for old in list(_adapters_loaded):
            if old == _NO_ADAPTER:
                continue
            try:
                model.delete_adapter(old)
            except Exception:
                pass
        _adapters_loaded.clear()

    try:
        model.load_adapter(primary_path, adapter_name=primary_name)
        model.load_adapter(secondary_path, adapter_name=secondary_name)
        model.add_weighted_adapter(
            adapters=[primary_name, secondary_name],
            weights=[primary_weight, 1.0 - primary_weight],
            adapter_name=merged_name,
            combination_type="linear",
        )
        # Evict source adapters — keep only the merged one resident
        for src in [primary_name, secondary_name]:
            try:
                model.delete_adapter(src)
            except Exception:
                pass
        model.set_adapter(merged_name)
        with _cache_lock:
            _adapters_loaded.add(merged_name)
        logger.info(
            "Inference: blended adapter '%s' (%.0f%% primary, %.0f%% secondary)",
            merged_name, primary_weight * 100, (1 - primary_weight) * 100,
        )
        return merged_name
    except Exception as e:
        logger.warning("Inference: adapter blend failed (%s) — falling back to primary", e)
        # Clean up any partial state before falling back
        for name in [primary_name, secondary_name, merged_name]:
            try:
                model.delete_adapter(name)
            except Exception:
                pass
        with _cache_lock:
            _adapters_loaded.clear()
        load_adapter(primary_path, primary_name)
        return primary_name


def warmup_model() -> None:
    """Pre-load the base model into the inference cache at server startup."""
    base_model = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-Coder-14B-Instruct-GPTQ-Int4")
    logger.info("Warmup: loading model '%s' into inference cache...", base_model)
    try:
        from .model_utils import resolve_model_path
        resolved = resolve_model_path(base_model)
        logger.info("Warmup: resolved model path: '%s'", resolved)
        ensure_base_model()
        logger.info("Warmup: model ready.")
    except Exception as e:
        logger.warning("Warmup: failed to load model '%s': %s", base_model, e)
    print("Warmup: model loaded CAN CONTINUE.")


# ── System prompt fallback ────────────────────────────────────────────────────

def _list_workspace(workspace_dir: str | None) -> str:
    """Return a formatted directory listing of the agent workspace for use in system prompts."""
    if not workspace_dir:
        return ""
    ws = Path(workspace_dir)
    if not ws.is_dir():
        return ""
    entries = sorted(ws.iterdir(), key=lambda p: (not p.is_dir(), p.name))[:30]
    if not entries:
        return ""
    lines = [f"  {'d' if e.is_dir() else 'f'}  {e.name}" for e in entries]
    return "\n".join(lines)


def _build_system_prompt(
    handle: str,
    name: str,
    role: str,
    profile: dict,
    workspace_dir: str | None = None,
) -> str:
    """Construct a full system prompt for a candidate agent, combining their persona and current workspace state."""
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
        "",
        "You have access to tools. To call a tool, emit a <tool_call> block with the JSON inside. "
        "Do NOT output tool calls as markdown code blocks or numbered steps — they will not execute. "
        "ONLY the <tool_call> format below will be executed:",
        "",
        '<tool_call>',
        '{"name": "write_file", "arguments": {"path": "example.py", "content": "print(\'hello\')"}}',
        '</tool_call>',
        "",
        "When the user asks you to create, write, read, edit, or delete files, "
        "list directories, or run commands, you MUST use the <tool_call> format above. "
        "NEVER just show code in a text response when the user asks you to create or modify a file.",
    ]

    ws_listing = _list_workspace(workspace_dir)
    if ws_listing:
        lines += [
            "",
            "Your workspace currently contains:",
            ws_listing,
            "",
            "Use list_files and read_file to inspect existing files before creating new ones. "
            "Work within the existing project structure — do not start from scratch.",
        ]
    else:
        lines += [
            "",
            "Your workspace is empty. Use list_files to confirm before scaffolding a new project.",
        ]

    return "\n".join(l for l in lines if l or l == "")


# ── Message formatting ───────────────────────────────────────────────────────

def _history_to_openai(system_prompt: str, history: list[dict]) -> list[dict]:
    """Convert a list of ChatMessage-style dicts to OpenAI message format (role/content)."""
    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = "user" if msg.get("sender") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})
    return messages


def _format_prompt(tokenizer, messages: list[dict], tools: list[dict] | None = None) -> str:
    """Apply the tokenizer's chat template to a message list, with optional tool schema injection."""
    kwargs = {
        "conversation": messages,
        "tokenize": False,
        "add_generation_prompt": True,
    }
    if tools:
        kwargs["tools"] = tools
    try:
        return tokenizer.apply_chat_template(**kwargs)
    except Exception as e:
        if tools:
            logger.warning("apply_chat_template failed WITH tools (%s) — retrying without", e)
        kwargs.pop("tools", None)
        return tokenizer.apply_chat_template(**kwargs)


# ── Tool call parsing ────────────────────────────────────────────────────────

_TOOL_CALL_RE = re.compile(
    r"<tool_call>\s*(\{.*?\})\s*</tool_call>",
    re.DOTALL,
)

_KNOWN_TOOL_NAMES = {
    "run_command", "write_file", "read_file", "create_folder",
    "list_files", "edit_file", "search_registry",
}

_INLINE_JSON_RE = re.compile(
    r'```(?:json)?\s*\n?\s*(\{[\s\S]*?\})\s*\n?\s*```'
    r'|\{[\t ]*"name"[\t ]*:[\t ]*"[^"]+?"[\t ]*,[\t ]*"arguments"[\t ]*:[\t ]*\{[\s\S]*?\}\s*\}',
)


def _parse_tool_calls(text: str) -> list[dict]:
    """Extract and parse tool call JSON objects from <tool_call>...</tool_call> tags in generated text."""
    results = []
    for match in _TOOL_CALL_RE.finditer(text):
        try:
            data = json.loads(match.group(1))
            if "name" in data:
                results.append(data)
        except json.JSONDecodeError:
            pass
    return results


def _extract_inline_json_commands(text: str) -> list[dict]:
    """Fallback: extract tool commands from inline JSON in the visible text.

    Matches both bare JSON objects and JSON inside ```json``` fences, as long
    as they have a known "name" and an "arguments" dict.
    """
    results = []
    for match in _INLINE_JSON_RE.finditer(text):
        raw = match.group(1) if match.group(1) else match.group(0)
        try:
            data = json.loads(raw)
            if (isinstance(data, dict)
                    and data.get("name") in _KNOWN_TOOL_NAMES
                    and isinstance(data.get("arguments"), dict)):
                results.append(data)
        except (json.JSONDecodeError, TypeError):
            pass
    return results


# ── Core generation (single pass) ────────────────────────────────────────────

def _generate_once(
    model,
    tokenizer,
    adapter_name: str,
    prompt: str,
    emit: Callable[[dict], None],
    max_new_tokens: int = 512,
) -> tuple[str, str, list[dict]]:
    """
    Run a single generation pass. Returns (visible_text, raw_output, tool_calls).
    Streams visible tokens via emit({"token": ...}).
    Filters <think> and <tool_call> blocks from visible output.
    """
    from transformers import TextIteratorStreamer

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

    with _cache_lock:
        if _NO_ADAPTER not in _adapters_loaded:
            model.set_adapter(adapter_name)

    gen_thread = threading.Thread(
        target=lambda: model.generate(**generate_kwargs),
        daemon=True,
    )
    gen_thread.start()

    visible_text = ""
    raw_output = ""
    in_think = False
    in_tool_call = False
    in_suppressed = False
    tool_call_buf = ""
    captured_tool_calls: list[dict] = []
    buf = ""

    THINK_OPEN = "<think>"
    THINK_CLOSE = "</think>"
    TC_OPEN = "<tool_call>"
    TC_CLOSE = "</tool_call>"
    # Tags whose content should be silently dropped (model echoing template)
    SUPPRESS_PAIRS = [
        ("<tools>", "</tools>"),
        ("<tool_response>", "</tool_response>"),
    ]
    ALL_OPEN_TAGS = [THINK_OPEN, TC_OPEN] + [p[0] for p in SUPPRESS_PAIRS]
    MAX_TAG = max(len(t) for t in ALL_OPEN_TAGS + [THINK_CLOSE, TC_CLOSE] + [p[1] for p in SUPPRESS_PAIRS])
    suppress_close = ""

    for token_text in streamer:
        if not token_text:
            continue
        buf += token_text
        raw_output += token_text

        while True:
            if in_think:
                idx = buf.find(THINK_CLOSE)
                if idx >= 0:
                    buf = buf[idx + len(THINK_CLOSE):]
                    in_think = False
                    emit({"thinking": False})
                else:
                    if len(buf) > len(THINK_CLOSE):
                        buf = buf[-(len(THINK_CLOSE) - 1):]
                    break
            elif in_tool_call:
                idx = buf.find(TC_CLOSE)
                if idx >= 0:
                    tool_call_buf += buf[:idx]
                    buf = buf[idx + len(TC_CLOSE):]
                    in_tool_call = False
                    try:
                        data = json.loads(tool_call_buf.strip())
                        if "name" in data:
                            captured_tool_calls.append(data)
                            emit({"tool_call": data})
                    except json.JSONDecodeError:
                        pass
                    tool_call_buf = ""
                else:
                    tool_call_buf += buf
                    buf = ""
                    break
            elif in_suppressed:
                idx = buf.find(suppress_close)
                if idx >= 0:
                    buf = buf[idx + len(suppress_close):]
                    in_suppressed = False
                    suppress_close = ""
                else:
                    if len(buf) > len(suppress_close):
                        buf = buf[-(len(suppress_close) - 1):]
                    break
            else:
                first_tag_idx = -1
                first_tag = None
                for tag in ALL_OPEN_TAGS:
                    idx = buf.find(tag)
                    if idx >= 0 and (first_tag_idx == -1 or idx < first_tag_idx):
                        first_tag_idx = idx
                        first_tag = tag

                if first_tag is None:
                    safe = len(buf) - (MAX_TAG - 1)
                    if safe > 0:
                        to_emit = buf[:safe]
                        buf = buf[safe:]
                        visible_text += to_emit
                        emit({"token": to_emit})
                    break
                else:
                    if first_tag_idx > 0:
                        to_emit = buf[:first_tag_idx]
                        buf = buf[first_tag_idx:]
                        visible_text += to_emit
                        emit({"token": to_emit})
                    if first_tag == THINK_OPEN:
                        buf = buf[len(THINK_OPEN):]
                        in_think = True
                        emit({"thinking": True})
                    elif first_tag == TC_OPEN:
                        buf = buf[len(TC_OPEN):]
                        in_tool_call = True
                        tool_call_buf = ""
                    else:
                        for open_tag, close_tag in SUPPRESS_PAIRS:
                            if first_tag == open_tag:
                                buf = buf[len(open_tag):]
                                in_suppressed = True
                                suppress_close = close_tag
                                break

    if buf and not in_think and not in_tool_call and not in_suppressed:
        visible_text += buf
        emit({"token": buf})

    gen_thread.join()

    if not visible_text.strip() and not captured_tool_calls:
        logger.warning(
            "Generation produced no visible text and no tool calls. "
            "raw_output (%d chars): %s",
            len(raw_output),
            raw_output[:500] or "(completely empty)",
        )

    logger.info(
        "Generation done: %d visible chars, %d tool calls, %d raw chars",
        len(visible_text), len(captured_tool_calls), len(raw_output),
    )

    return visible_text, raw_output, captured_tool_calls


# ── stream_chat (backward compat, no tools) ──────────────────────────────────

def stream_chat(
    lora_path: str,
    adapter_name: str,
    role: str,
    profile: dict,
    history: list[dict],
    emit: Callable[[dict], None],
    max_new_tokens: int = 512,
    system_prompt: str | None = None,
) -> str:
    """
    Activate the candidate's LoRA adapter and generate a streaming response.
    No tool use — kept for backward compatibility.
    """
    model, tokenizer = ensure_base_model()
    load_adapter(lora_path, adapter_name)

    if not system_prompt:
        name = profile.get("name") or adapter_name
        system_prompt = _build_system_prompt(adapter_name, name, role, profile)

    messages = _history_to_openai(system_prompt, history)
    prompt = _format_prompt(tokenizer, messages)

    visible, _, _ = _generate_once(model, tokenizer, adapter_name, prompt, emit, max_new_tokens)
    return visible


# ── agent_chat (tool-use loop) ───────────────────────────────────────────────

MAX_TOOL_ITERATIONS = 10


def agent_chat(
    lora_path: str,
    adapter_name: str,
    role: str,
    profile: dict,
    history: list[dict],
    emit: Callable[[dict], None],
    workspace_dir: str,
    tools: list[dict] | None = None,
    max_new_tokens: int = 2048,
    system_prompt: str | None = None,
    blend_lora_path: str | None = None,
    blend_adapter_name: str | None = None,
    blend_weight: float = 0.7,
) -> str:
    """
    Agentic chat with tool use.  Generates a response, detects <tool_call>
    blocks, executes them in the sandboxed workspace, feeds results back,
    and regenerates — up to MAX_TOOL_ITERATIONS times.

    When blend_lora_path and blend_adapter_name are provided, the specialist's
    adapter is linearly interpolated with the secondary adapter (typically the PM's)
    before generation. The specialist dominates at blend_weight (default 0.7) and
    the secondary contributes at (1 - blend_weight). Merging happens in weight space
    via load_blended_adapter() — not via a system prompt injection.

    Returns the concatenated visible text across all iterations.
    """
    from .tools import execute_tool

    model, tokenizer = ensure_base_model()
    if blend_lora_path and blend_adapter_name and blend_adapter_name != adapter_name:
        active_adapter = load_blended_adapter(
            primary_path=lora_path,
            primary_name=adapter_name,
            secondary_path=blend_lora_path,
            secondary_name=blend_adapter_name,
            primary_weight=blend_weight,
        )
    else:
        load_adapter(lora_path, adapter_name)
        active_adapter = adapter_name

    if not system_prompt:
        name = profile.get("name") or adapter_name
        system_prompt = _build_system_prompt(adapter_name, name, role, profile, workspace_dir)

    messages = _history_to_openai(system_prompt, history)
    full_visible = ""

    for iteration in range(MAX_TOOL_ITERATIONS):
        prompt = _format_prompt(tokenizer, messages, tools=tools)
        visible, raw, tool_calls = _generate_once(
            model, tokenizer, active_adapter, prompt, emit, max_new_tokens,
        )
        full_visible += visible

        if not tool_calls:
            tool_calls = _extract_inline_json_commands(visible)
            if tool_calls:
                logger.info(
                    "agent_chat: no <tool_call> tags found, but extracted %d "
                    "inline JSON command(s) from visible text",
                    len(tool_calls),
                )
                for tc in tool_calls:
                    emit({"tool_call": tc})

        if not tool_calls:
            break

        assistant_content = raw
        messages.append({"role": "assistant", "content": assistant_content})

        for tc in tool_calls:
            tool_name = tc.get("name", "")
            arguments = tc.get("arguments", {})
            output, success = execute_tool(workspace_dir, tool_name, arguments)
            emit({"tool_result": {"name": tool_name, "output": output[:2000], "success": success}})

            messages.append({
                "role": "tool",
                "name": tool_name,
                "content": json.dumps({"result": output[:4000], "success": success}),
            })

        logger.info("agent_chat iteration %d: %d tool calls executed", iteration + 1, len(tool_calls))
    else:
        logger.warning("agent_chat hit max iterations (%d)", MAX_TOOL_ITERATIONS)

    return full_visible


# ── Side-by-side comparison (base vs. adapter) ──────────────────────────────

def compare_generation(
    lora_path: str,
    adapter_name: str,
    role: str,
    profile: dict,
    prompt_text: str,
    emit: Callable[[dict], None],
    max_new_tokens: int = 512,
    system_prompt: str | None = None,
) -> dict:
    """Generate the same prompt through the raw base model and the adapter-loaded
    model, returning both outputs for side-by-side comparison.

    Designed to be called via asyncio.to_thread().
    """
    model, tokenizer = ensure_base_model()

    name = profile.get("name") or adapter_name
    sys_prompt = system_prompt or _build_system_prompt(adapter_name, name, role, profile)
    messages = _history_to_openai(sys_prompt, [{"sender": "user", "content": prompt_text}])

    # 1) Generate with adapter loaded
    load_adapter(lora_path, adapter_name)
    prompt = _format_prompt(tokenizer, messages)
    emit({"phase": "adapter", "status": "generating"})
    adapter_visible, _, _ = _generate_once(
        model, tokenizer, adapter_name, prompt,
        lambda ev: emit({**ev, "source": "adapter"}),
        max_new_tokens,
    )

    # 2) Generate with raw base model (no adapter)
    with _cache_lock:
        for old in list(_adapters_loaded):
            if old == _NO_ADAPTER:
                continue
            try:
                model.delete_adapter(old)
            except Exception:
                pass
        _adapters_loaded.clear()
        _adapters_loaded.add(_NO_ADAPTER)

    emit({"phase": "base", "status": "generating"})
    base_visible, _, _ = _generate_once(
        model, tokenizer, _NO_ADAPTER, prompt,
        lambda ev: emit({**ev, "source": "base"}),
        max_new_tokens,
    )

    # Restore the adapter for subsequent requests
    with _cache_lock:
        _adapters_loaded.discard(_NO_ADAPTER)

    return {
        "prompt": prompt_text,
        "adapter_name": adapter_name,
        "base_response": base_visible,
        "adapter_response": adapter_visible,
    }
