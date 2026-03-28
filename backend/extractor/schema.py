"""
Shared Grok client + structured output schema used by website and resume extractors.
"""
import json
import os
from typing import Optional

from openai import OpenAI
from pydantic import BaseModel, Field


# ── Pydantic model for structured candidate extraction ────────────────────────

class CandidateExtract(BaseModel):
    name: str = Field(description="Full name of the candidate")
    bio: str = Field(description="1-2 sentence professional summary")
    location: str = Field(description="City/country, or empty string if unknown")
    skills: list[str] = Field(description="Technical or domain-specific skills, max 8")
    soft_skills: list[str] = Field(description="Interpersonal and leadership skills, max 8")
    description: str = Field(description="One sentence role-fit assessment for the given role")
    languages: dict[str, float] = Field(
        default_factory=dict,
        description="Programming language proficiency percentages (0-100), empty for non-engineers",
    )


# ── Grok client ───────────────────────────────────────────────────────────────

def get_grok_client() -> OpenAI:
    api_key = os.getenv("XAI_API_KEY")
    if not api_key:
        raise RuntimeError("XAI_API_KEY environment variable is not set")
    return OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")


GROK_MODEL = "grok-4.20-0309-non-reasoning"

# ── Role-aware system prompts ─────────────────────────────────────────────────

ROLE_CONTEXT: dict[str, str] = {
    "pm": (
        "You are evaluating this person as a potential Product Manager. "
        "Focus on: strategic thinking, roadmapping, user research, stakeholder management, "
        "cross-functional collaboration, and data-driven decision making. "
        "Soft skills matter more than technical skills for this role."
    ),
    "swe": (
        "You are evaluating this person as a Software Engineer. "
        "Focus on: technical depth, languages/frameworks, system design, architecture, "
        "open-source contributions, and engineering practices."
    ),
    "designer": (
        "You are evaluating this person as a UX/UI Designer. "
        "Focus on: design tools (Figma, Sketch), UX research, design systems, "
        "interaction design, visual design, accessibility, and portfolio work."
    ),
}

SYSTEM_PROMPT = """You are a talent-intelligence AI for Clone.dna, a platform that profiles candidates for hiring.

Your task: extract a structured candidate profile from the provided content.

Rules:
- Be specific and factual — only extract what is actually present in the content.
- If information is missing, use an empty string or empty list — do not hallucinate.
- skills: technical/domain skills (languages, frameworks, tools, methodologies).
- soft_skills: interpersonal/leadership (communication, leadership, strategy, etc.).
- description: exactly one sentence assessing this person's fit for the target role.
- languages: only for engineers; a dict mapping language names to estimated % proficiency.

Respond with a valid JSON object matching this schema exactly:
{
  "name": string,
  "bio": string (1-2 sentences),
  "location": string,
  "skills": [string, ...],       // max 8
  "soft_skills": [string, ...],  // max 8
  "description": string,
  "languages": { "Language": percentage_float, ... }
}"""


def call_grok(content: str, role: Optional[str] = None) -> Optional[CandidateExtract]:
    """
    Send content to Grok with structured output extraction.
    Uses json_object mode for broad compatibility, then validates with Pydantic.
    """
    client = get_grok_client()

    role_context = ROLE_CONTEXT.get(role or "", "")
    user_message = f"{role_context}\n\n---CONTENT---\n{content[:12000]}" if role_context else content[:12000]

    try:
        response = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return CandidateExtract(**data)
    except Exception as e:
        print(f"[grok] extraction failed: {e}")
        return None


def generate_github_description(profile: dict, role: str) -> Optional[str]:
    """
    Generate a single personalized role-fit sentence for a GitHub profile using Grok.
    Returns None if Grok is unavailable or the call fails.
    """
    try:
        client = get_grok_client()
    except RuntimeError:
        return None

    role_context = ROLE_CONTEXT.get(role, "")
    top_repos = profile.get("top_repos", [])
    repo_names = ", ".join(r["name"] for r in top_repos[:3]) if top_repos else "none"
    languages = ", ".join(
        f"{lang} ({pct}%)" for lang, pct in list(profile.get("languages", {}).items())[:4]
    ) or "unknown"
    skills = ", ".join(profile.get("skills", [])[:6]) or "none listed"

    user_message = (
        f"{role_context}\n\n"
        f"Name: {profile.get('name', 'Unknown')}\n"
        f"Bio: {profile.get('bio', '') or 'No bio'}\n"
        f"Location: {profile.get('location', '') or 'Unknown'}\n"
        f"Followers: {profile.get('followers', 0)} | Public repos: {profile.get('public_repos', 0)}\n"
        f"Top repos: {repo_names}\n"
        f"Primary languages: {languages}\n"
        f"Skills: {skills}\n\n"
        "Write exactly one sentence (under 25 words) assessing this person's fit for the role. "
        "Be specific to their actual background. Do not start with their name."
    )

    try:
        response = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": "You are a concise talent-intelligence AI. Respond with a single sentence only — no quotes, no explanation."},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.4,
            max_tokens=60,
        )
        sentence = response.choices[0].message.content.strip().strip('"').strip("'")
        return sentence if sentence else None
    except Exception as e:
        print(f"[grok] description generation failed: {e}")
        return None


def candidate_extract_to_profile(extract: CandidateExtract, source_url: str = "") -> dict:
    """Convert a CandidateExtract into the same dict shape that github.py returns."""
    return {
        "github_handle":  extract.name.lower().replace(" ", "-"),
        "name":           extract.name,
        "avatar_url":     None,
        "bio":            extract.bio,
        "location":       extract.location,
        "followers":      0,
        "public_repos":   0,
        "top_repos":      [],
        "languages":      extract.languages,
        "skills":         extract.skills,
        "soft_skills":    extract.soft_skills,
        "description":    extract.description,
        "profile_url":    source_url,
    }
