"""Anthropic Claude API integration — Claude-powered chat for the build mode BoostX option."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable

import anthropic

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-haiku-4-5"
MAX_CLAUDE_TOOL_ITERATIONS = 10

_KNOWN_TOOL_NAMES = {
    "run_command", "write_file", "read_file", "create_folder",
    "list_files", "edit_file", "search_registry", "attach_file",
}

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_INLINE_JSON_RE = re.compile(
    r'```(?:json)?\s*\n?\s*(\{[\s\S]*?\})\s*\n?\s*```'
    r'|\{[\t ]*"name"[\t ]*:[\t ]*"[^"]+?"[\t ]*,[\t ]*"arguments"[\t ]*:[\t ]*\{[\s\S]*?\}\s*\}',
)


def _claude_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY", ""))


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


def claude_chat(
    candidate: dict,
    history: list[dict],
    emit: Callable[[dict], None],
    workspace_dir: str,
    tools: list[dict] | None = None,
) -> str:
    """Chat using Claude API with the candidate's personality profile and system
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
            "\n\nYou have access to tools. To call a tool, emit a <tool_call> block: "
            "<tool_call>{\"name\": \"tool_name\", \"arguments\": {...}}</tool_call>\n"
            f"Available tools: {', '.join(tool_names)}\n\n"
            "CRITICAL: Do NOT describe plans or say 'I will now...' or 'Executing step X'. "
            "Just call the tool immediately. One tool call, then respond with what you did. "
            "Never output a numbered plan — that is not helpful. Act first, explain after if needed. "
            "When asked to build, create, write, edit, attach, or modify anything, "
            "use the appropriate tool right now in this response.\n\n"
            "PDF GENERATION: To produce a PDF, write the content as an HTML file with embedded CSS "
            "first (use write_file), then compile it with: "
            "run_command: weasyprint input.html output.pdf"
        )

    messages = []
    for msg in history:
        role = "user" if msg.get("sender") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})

    client = _claude_client()
    full_visible = ""

    for iteration in range(MAX_CLAUDE_TOOL_ITERATIONS):
        emit({"thinking": True})
        try:
            visible = ""
            first_token = True
            _DELEGATE_TAG_RE = re.compile(r'\s*</?(?:no_)?delegate\s*/?>\s*', re.IGNORECASE)

            with client.messages.stream(
                model=CLAUDE_MODEL,
                system=sys_prompt,
                messages=messages,
                max_tokens=4096,
            ) as stream:
                for text_chunk in stream.text_stream:
                    if first_token:
                        emit({"thinking": False})
                        first_token = False
                    visible += text_chunk
                    full_visible += text_chunk
                    clean = _DELEGATE_TAG_RE.sub('', text_chunk)
                    if clean:
                        emit({"token": clean})

            if first_token:
                emit({"thinking": False})

        except Exception as e:
            emit({"thinking": False})
            emit({"error": f"Claude API error: {e}"})
            break

        tool_calls = _extract_tool_calls_from_text(visible)
        if not tool_calls:
            break

        messages.append({"role": "assistant", "content": visible})
        for tc in tool_calls:
            emit({"tool_call": tc})
            tool_name = tc.get("name", "")
            arguments = tc.get("arguments", {})
            output, success = execute_tool(workspace_dir, tool_name, arguments)
            emit({"tool_result": {"name": tool_name, "output": output[:2000], "success": success}})
            messages.append({
                "role": "user",
                "content": f"Tool result for {tool_name}: {json.dumps({'result': output[:4000], 'success': success})}",
            })

        logger.info("claude_chat iteration %d: %d tool calls executed", iteration + 1, len(tool_calls))

    return full_visible
