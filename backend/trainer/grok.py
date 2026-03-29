"""Grok API integration — generate training pairs and identity system prompts."""

from __future__ import annotations

import json
import logging
import os
from typing import Callable

from openai import OpenAI

logger = logging.getLogger(__name__)

GROK_MODEL = "grok-4.20-0309-reasoning"
PAIRS_PER_BLOB = 6

PAIR_SYSTEM_TEMPLATE = (
    "You are analyzing the code written by {name} (GitHub: @{handle}). "
    "Their primary skills: {skills}. Languages: {languages}. "
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


def generate_system_prompt(
    candidate: dict,
    code_blobs: list[dict],
    emit: Callable[[dict], None],
) -> str:
    """
    Call Grok with the candidate's full profile + a sample of their real code
    to produce a rich, first-person identity system prompt saved in the DB.
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

    emit({"phase": "generating", "candidate": handle, "message": "Generating identity system prompt..."})

    user_prompt = (
        f"You are crafting a system prompt that will make an LLM embody {name} (@{handle}), "
        f"a {role} on a software team.\n\n"
        f"Here is their profile:\n"
        f"- Bio: {bio or 'N/A'}\n"
        f"- Role fit summary: {description or 'N/A'}\n"
        f"- Technical skills: {skills or 'N/A'}\n"
        f"- Soft skills: {soft_skills or 'N/A'}\n"
        f"- Languages: {languages or 'N/A'}\n\n"
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
