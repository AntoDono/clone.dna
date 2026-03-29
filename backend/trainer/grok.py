"""Grok API integration — generate training pairs, personality profiles, identity
system prompts, and Grok-powered chat for the build mode fallback."""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Callable

from openai import OpenAI

logger = logging.getLogger(__name__)

GROK_MODEL = "grok-4.20-0309-reasoning"
GROK_CHAT_MODEL = "grok-4.20-0309-reasoning"
PAIRS_PER_BLOB = 6

PAIR_SYSTEM_TEMPLATE = (
    "You are analyzing the code written by {name} (GitHub: @{handle}). "
    "Their primary skills: {skills}. Languages: {languages}. "
    "{personality_context}"
    "Your task: generate high-quality instruction→response training pairs that capture "
    "their coding style, architecture patterns, and domain expertise. "
    "Each pair should be a realistic programming task with a response in their style."
)

PAIR_USER_TEMPLATE = (
    "Here is real source code from their GitHub repo '{repo}':\n\n"
    "```\n{code}\n```\n\n"
    "Generate exactly {pairs_per_blob} instruction→response pairs as a JSON array. "
    "Each element must be: {{\"instruction\": \"<task>\", \"response\": \"<code/answer>\"}}. "
    "The instructions should be realistic engineering tasks. "
    "The responses should match this developer's actual style from the code above. "
    "Return ONLY valid JSON, no markdown fences."
)


def _grok_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("XAI_API_KEY", ""),
        base_url="https://api.x.ai/v1",
    )


def generate_training_pairs(
    candidate: dict,
    code_blobs: list[dict],
    emit: Callable[[dict], None],
    personality_profile: dict | None = None,
) -> list[dict]:
    """
    Send each code blob to Grok to generate instruction→response pairs
    that capture this developer's coding style and expertise.
    Returns list of {"instruction": str, "response": str} dicts.
    """
    handle = candidate.get("github_handle", "")
    name = candidate.get("name") or handle
    skills = ", ".join(candidate.get("skills", [])[:6])
    languages = ", ".join(list(candidate.get("languages", {}).keys())[:4])

    personality_context = ""
    if personality_profile:
        parts = []
        if personality_profile.get("coding_style"):
            parts.append(f"Coding style: {personality_profile['coding_style']}.")
        if personality_profile.get("work_style"):
            parts.append(f"Work style: {personality_profile['work_style']}.")
        if personality_profile.get("communication_style"):
            parts.append(f"Communication: {personality_profile['communication_style']}.")
        if personality_profile.get("architecture_preferences"):
            parts.append(f"Architecture: {personality_profile['architecture_preferences']}.")
        if parts:
            personality_context = " ".join(parts) + " "

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

        system_prompt = PAIR_SYSTEM_TEMPLATE.format(
            name=name, handle=handle, skills=skills, languages=languages,
            personality_context=personality_context,
        )

        user_prompt = PAIR_USER_TEMPLATE.format(
            repo=repo, code=code[:8000], pairs_per_blob=PAIRS_PER_BLOB,
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


def generate_personality_profile(
    candidate: dict,
    code_blobs: list[dict],
    emit: Callable[[dict], None],
) -> dict:
    """Analyze the candidate's code and profile to produce a structured personality
    profile covering coding style, work habits, skills depth, and communication."""
    handle = candidate.get("github_handle", "")
    name = candidate.get("name") or handle
    role_map = {"pm": "Product Manager", "swe": "Software Engineer", "designer": "Designer"}
    role = role_map.get(candidate.get("role", ""), candidate.get("role", "engineer"))
    skills = ", ".join((candidate.get("skills") or [])[:8])
    soft_skills = ", ".join((candidate.get("soft_skills") or [])[:5])
    languages = ", ".join(list((candidate.get("languages") or {}).keys())[:5])
    bio = (candidate.get("bio") or "").strip()
    description = (candidate.get("description") or "").strip()

    code_samples = ""
    for blob in code_blobs[:3]:
        code_samples += f"\n--- {blob.get('repo', 'unknown')} ---\n{blob['code'][:2500]}\n"

    emit({"phase": "generating", "candidate": handle, "message": "Building personality profile..."})

    user_prompt = (
        f"Analyze {name} (@{handle}), a {role}, and produce a structured personality profile.\n\n"
        f"Profile data:\n"
        f"- Bio: {bio or 'N/A'}\n"
        f"- Description: {description or 'N/A'}\n"
        f"- Technical skills: {skills or 'N/A'}\n"
        f"- Soft skills: {soft_skills or 'N/A'}\n"
        f"- Languages: {languages or 'N/A'}\n\n"
        + (f"Code samples from their repositories:\n```\n{code_samples}\n```\n\n" if code_samples.strip() else "")
        + "Return a JSON object with these keys:\n"
        '- "coding_style": string describing their coding patterns, naming conventions, '
        "comment density, function size preferences, paradigm (OOP/functional/etc.)\n"
        '- "architecture_preferences": string on their preferred architectures, patterns, '
        "and system design approach\n"
        '- "work_style": string on how they approach work (iterative/waterfall, test-first, etc.)\n'
        '- "communication_style": string on tone, verbosity, formality, emoji usage\n'
        '- "hard_skills": list of objects with "skill" and "depth" keys assessing their '
        "technical proficiency in specific areas\n"
        '- "soft_skills": list of objects with "trait" and "evidence" keys\n'
        '- "personality_traits": string summarizing their personality as a developer\n'
        '- "domain_expertise": list of objects with "domain" and "depth" (1-5 scale)\n'
    )

    try:
        client = _grok_client()
        resp = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.4,
            max_tokens=1200,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        profile = json.loads(raw)
        emit({"phase": "generating", "candidate": handle, "message": "Personality profile ready"})
        return profile
    except Exception as e:
        logger.warning("Personality profile generation failed for %s: %s", handle, e)
        emit({"phase": "generating", "candidate": handle, "message": f"Personality profile fallback: {e}"})
        return {
            "coding_style": "conventional, readable code",
            "architecture_preferences": "pragmatic, follows established patterns",
            "work_style": "iterative development",
            "communication_style": "concise and technical",
            "hard_skills": [{"skill": s, "depth": "proficient"} for s in (candidate.get("skills") or [])[:5]],
            "soft_skills": [{"trait": s, "evidence": "inferred from profile"} for s in (candidate.get("soft_skills") or [])[:3]],
            "personality_traits": "professional, focused",
            "domain_expertise": [],
        }


def generate_system_prompt(
    candidate: dict,
    code_blobs: list[dict],
    emit: Callable[[dict], None],
    personality_profile: dict | None = None,
) -> str:
    """
    Call Grok with the candidate's full profile + personality analysis + a sample
    of their real code to produce a rich, first-person identity system prompt.
    """
    handle = candidate.get("github_handle", "")
    name = candidate.get("name") or handle
    role_map = {"pm": "Product Manager", "swe": "Software Engineer", "designer": "Designer"}
    role = role_map.get(candidate.get("role", ""), candidate.get("role", "engineer"))
    skills = ", ".join((candidate.get("skills") or [])[:8])
    soft_skills = ", ".join((candidate.get("soft_skills") or [])[:5])
    languages = ", ".join(list((candidate.get("languages") or {}).keys())[:5])
    bio = (candidate.get("bio") or "").strip()
    description = (candidate.get("description") or "").strip()

    code_sample = ""
    if code_blobs:
        code_sample = code_blobs[0]["code"][:3000]

    personality_block = ""
    if personality_profile:
        personality_block = (
            f"\nPersonality analysis:\n"
            f"- Coding style: {personality_profile.get('coding_style', 'N/A')}\n"
            f"- Architecture: {personality_profile.get('architecture_preferences', 'N/A')}\n"
            f"- Work style: {personality_profile.get('work_style', 'N/A')}\n"
            f"- Communication: {personality_profile.get('communication_style', 'N/A')}\n"
            f"- Personality: {personality_profile.get('personality_traits', 'N/A')}\n"
        )

    emit({"phase": "generating", "candidate": handle, "message": "Generating identity system prompt..."})

    user_prompt = (
        f"You are crafting a system prompt that will make an LLM embody {name} (@{handle}), "
        f"a {role} on a software team.\n\n"
        f"Here is their profile:\n"
        f"- Bio: {bio or 'N/A'}\n"
        f"- Role fit summary: {description or 'N/A'}\n"
        f"- Technical skills: {skills or 'N/A'}\n"
        f"- Soft skills: {soft_skills or 'N/A'}\n"
        f"- Languages: {languages or 'N/A'}\n"
        + personality_block
        + "\n"
        + (f"Here is a sample of their real code:\n```\n{code_sample}\n```\n\n" if code_sample else "")
        + "Write a detailed first-person system prompt (200-350 words) that:\n"
        "1. States who they are and their role\n"
        "2. Describes their coding philosophy and architecture preferences drawn from the code sample\n"
        "3. Captures their communication style (terse/verbose, formal/casual, emoji usage, etc.)\n"
        "4. Lists their core technical strengths and the domains they think in\n"
        "5. Tells the LLM to stay in character, be opinionated, and respond as this specific person\n"
        "Return ONLY the system prompt text, no headings or meta-commentary."
    )

    try:
        client = _grok_client()
        resp = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[{"role": "user", "content": user_prompt}],
            temperature=0.6,
            max_tokens=600,
        )
        prompt_text = (resp.choices[0].message.content or "").strip()
        emit({"phase": "generating", "candidate": handle, "message": "Identity system prompt ready"})
        return prompt_text
    except Exception as e:
        logger.warning("System prompt generation failed for %s: %s", handle, e)
        emit({"phase": "generating", "candidate": handle, "message": f"System prompt fallback used: {e}"})
        return (
            f"You are {name} (@{handle}), a {role}. "
            f"Primary skills: {skills}. Languages: {languages}. "
            f"{bio} "
            "Respond as this specific person — be concise, technical, and in character."
        )


# ── Grok-powered chat (build mode fallback) ─────────────────────────────────

MAX_GROK_TOOL_ITERATIONS = 10

_KNOWN_TOOL_NAMES = {
    "run_command", "write_file", "read_file", "create_folder",
    "list_files", "edit_file", "search_registry", "attach_file",
}

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_INLINE_JSON_RE = re.compile(
    r'```(?:json)?\s*\n?\s*(\{[\s\S]*?\})\s*\n?\s*```'
    r'|\{[\t ]*"name"[\t ]*:[\t ]*"[^"]+?"[\t ]*,[\t ]*"arguments"[\t ]*:[\t ]*\{[\s\S]*?\}\s*\}',
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


def grok_chat(
    candidate: dict,
    history: list[dict],
    emit: Callable[[dict], None],
    workspace_dir: str,
    tools: list[dict] | None = None,
) -> str:
    """Chat using Grok API with the candidate's personality profile and system
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
            "use the appropriate tool right now in this response."
        )

    messages = [{"role": "system", "content": sys_prompt}]
    for msg in history:
        role = "user" if msg.get("sender") == "user" else "assistant"
        messages.append({"role": role, "content": msg.get("content", "")})

    client = _grok_client()
    full_visible = ""

    for iteration in range(MAX_GROK_TOOL_ITERATIONS):
        emit({"thinking": True})
        try:
            stream = client.chat.completions.create(
                model=GROK_CHAT_MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
                stream=True,
            )
        except Exception as e:
            emit({"thinking": False})
            emit({"error": f"Grok API error: {e}"})
            break

        visible = ""
        first_token = True
        _DELEGATE_TAG_RE = re.compile(r'\s*</?(?:no_)?delegate\s*/?>\s*', re.IGNORECASE)
        for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta:
                # Reasoning model emits thinking tokens in reasoning_content before visible content.
                # Keep the thinking indicator alive during that phase.
                if not delta.content and getattr(delta, "reasoning_content", None):
                    emit({"thinking": True})
                if delta.content:
                    if first_token:
                        emit({"thinking": False})
                        first_token = False
                    token = delta.content
                    visible += token
                    full_visible += token
                    clean = _DELEGATE_TAG_RE.sub('', token)
                    if clean:
                        emit({"token": clean})

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

        logger.info("grok_chat iteration %d: %d tool calls executed", iteration + 1, len(tool_calls))

    return full_visible
