"""OpenRouter API integration — OpenAI-compatible client for multi-model chat."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENROUTER_MODEL = "qwen/qwen3.5-35b-a3b"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_OPENROUTER_TOOL_ITERATIONS = 10

_KNOWN_TOOL_NAMES = {
    "run_command", "write_file", "read_file", "create_folder",
    "list_files", "edit_file", "search_registry", "attach_file",
}

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_INLINE_JSON_RE = re.compile(
    r'```(?:json)?\s*\n?\s*(\{[\s\S]*?\})\s*\n?\s*```'
    r'|\{[\t ]*"name"[\t ]*:[\t ]*"[^"]+?"[\t ]*,[\t ]*"arguments"[\t ]*:[\t ]*\{[\s\S]*?\}\s*\}',
)


def _openrouter_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url=OPENROUTER_BASE_URL,
    )


def _extract_tool_calls_from_text(text: str) -> list[dict]:
    """Extract tool calls from <tool_call> tags or inline JSON."""
    results = []
    for match in _TOOL_CALL_RE.finditer(text):
        try:
            data = json.loads(match.group(1))
            if "name" in data:
                results.append(data)
        except json.JSONDecodeError:
            pass
    if results:
        return results
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


def openrouter_chat(
    candidate: dict,
    history: list[dict],
    emit: Callable[[dict], None],
    workspace_dir: str,
    tools: list[dict] | None = None,
) -> str:
    """Chat using OpenRouter API with the candidate's personality profile and system
    prompt. Supports tool use with the same execute_tool from trainer.tools."""
    from .tools import execute_tool

    handle = candidate.get("github_handle", "")
    name = candidate.get("name") or handle
    sys_prompt = candidate.get("system_prompt") or ""

    profile = candidate.get("personality_profile")
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except (json.JSONDecodeError, TypeError):
            profile = None

    if profile:
        profile_context = (
            f"\n\nPersonality profile:\n"
            f"- Coding style: {profile.get('coding_style', '')}\n"
            f"- Architecture: {profile.get('architecture_preferences', '')}\n"
            f"- Work style: {profile.get('work_style', '')}\n"
            f"- Communication: {profile.get('communication_style', '')}\n"
            f"- Personality: {profile.get('personality_traits', '')}\n"
        )
        sys_prompt += profile_context

    if not sys_prompt:
        sys_prompt = (
            f"You are {name} (@{handle}). Respond as this developer — "
            "be concise, technical, and in character."
        )

    if tools:
        tool_names = [t["function"]["name"] for t in tools if "function" in t]
        sys_prompt += (
            "\n\nYou have access to LIVE, EXECUTABLE tools. When you emit a <tool_call> block it "
            "runs immediately and you receive the result. Tools are not hypothetical.\n\n"
            "To call a tool emit EXACTLY this format (one per call):\n"
            "<tool_call>{\"name\": \"TOOL_NAME\", \"arguments\": {\"KEY\": \"VALUE\"}}</tool_call>\n\n"
            f"Available tools: {', '.join(tool_names)}\n\n"
            "EXACT parameter names (never invent others):\n"
            "  write_file    → {\"path\": \"report.txt\", \"content\": \"...\"}\n"
            "  read_file     → {\"path\": \"report.txt\"}\n"
            "  edit_file     → {\"path\": \"f.txt\", \"old_string\": \"...\", \"new_string\": \"...\"}\n"
            "  run_command   → {\"command\": \"python3 script.py\"}\n"
            "  attach_file   → {\"path\": \"report.txt\"}\n"
            "  create_folder → {\"path\": \"dirname\"}\n"
            "  list_files    → {\"path\": \".\"}\n\n"
            "ALWAYS deliver output as a file. Workflow for ANY deliverable:\n"
            "  STEP 1 — write the file:\n"
            "  <tool_call>{\"name\": \"write_file\", \"arguments\": {\"path\": \"output.txt\", \"content\": \"...\"}}</tool_call>\n"
            "  STEP 2 — attach it so it appears as a download in the channel:\n"
            "  <tool_call>{\"name\": \"attach_file\", \"arguments\": {\"path\": \"output.txt\"}}</tool_call>\n\n"
            "NEVER say 'the attachment mechanism isn't available', 'I can't attach', or 'share it manually'. "
            "attach_file is live. If you skip it the user sees nothing. Always call it.\n\n"
            "CRITICAL: Do NOT narrate plans. Do NOT say 'I will now...'. Call the tool, then briefly state what you did.\n\n"
            "PYTHON: Always use `python3` (global). Never use `python`, venv paths, or `./venv/`."
        )

    messages = [{"role": "system", "content": sys_prompt}]
    for msg in history:
        role = "user" if msg.get("sender") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})

    client = _openrouter_client()
    full_visible = ""
    _DELEGATE_TAG_RE = re.compile(r'\s*</?(?:no_)?delegate\s*/?>\s*', re.IGNORECASE)

    for iteration in range(MAX_OPENROUTER_TOOL_ITERATIONS):
        emit({"thinking": True})

        api_kwargs: dict = {
            "model": OPENROUTER_MODEL,
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 4096,
            "stream": True,
        }
        if tools:
            api_kwargs["tools"] = tools
            api_kwargs["tool_choice"] = "auto"

        try:
            stream = client.chat.completions.create(**api_kwargs)
        except Exception as e:
            emit({"thinking": False})
            emit({"error": f"OpenRouter API error: {e}"})
            break

        visible = ""
        first_token = True
        # Accumulate native tool-call deltas keyed by index
        tc_acc: dict[int, dict] = {}

        for chunk in stream:
            choice = chunk.choices[0] if chunk.choices else None
            if not choice:
                continue
            delta = choice.delta

            if delta and delta.content:
                if first_token:
                    emit({"thinking": False})
                    first_token = False
                token = delta.content
                visible += token
                full_visible += token
                clean = _DELEGATE_TAG_RE.sub("", token)
                if clean:
                    emit({"token": clean})

            if delta and delta.tool_calls:
                if first_token:
                    emit({"thinking": False})
                    first_token = False
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_acc:
                        tc_acc[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tc_acc[idx]["id"] += tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc_acc[idx]["name"] += tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc_acc[idx]["arguments"] += tc_delta.function.arguments

        if first_token:
            emit({"thinking": False})

        # Build native tool calls from accumulated deltas
        native_calls: list[dict] = []
        for idx in sorted(tc_acc.keys()):
            acc = tc_acc[idx]
            try:
                native_calls.append({
                    "id": acc["id"],
                    "name": acc["name"],
                    "arguments": json.loads(acc["arguments"]),
                })
            except json.JSONDecodeError:
                logger.warning("openrouter_chat: bad tool-call JSON for %s: %s", acc["name"], acc["arguments"])

        # Fall back to text-based extraction if the model didn't use native calls
        text_calls = _extract_tool_calls_from_text(visible) if not native_calls else []
        all_calls = native_calls or text_calls

        if not all_calls:
            break

        if native_calls:
            # Add assistant turn with native tool_calls array
            messages.append({
                "role": "assistant",
                "content": visible or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        },
                    }
                    for tc in native_calls
                ],
            })
            for tc in native_calls:
                emit({"tool_call": {"name": tc["name"], "arguments": tc["arguments"]}})
                output, success = execute_tool(workspace_dir, tc["name"], tc["arguments"])
                emit({"tool_result": {"name": tc["name"], "output": output[:2000], "success": success}})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": json.dumps({"result": output[:4000], "success": success}),
                })
        else:
            # Text-based fallback
            messages.append({"role": "assistant", "content": visible})
            for tc in text_calls:
                emit({"tool_call": tc})
                output, success = execute_tool(workspace_dir, tc.get("name", ""), tc.get("arguments", {}))
                emit({"tool_result": {"name": tc.get("name"), "output": output[:2000], "success": success}})
                messages.append({
                    "role": "user",
                    "content": f"Tool result for {tc.get('name')}: {json.dumps({'result': output[:4000], 'success': success})}",
                })

        logger.info("openrouter_chat iteration %d: %d tool calls (%s)",
                    iteration + 1, len(all_calls), "native" if native_calls else "text")

    return full_visible
