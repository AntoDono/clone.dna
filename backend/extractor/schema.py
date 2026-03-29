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
    """Create an OpenAI-compatible client pointed at the xAI Grok API endpoint."""
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
    """Send content to Grok with role-aware system prompt and return a validated CandidateExtract, or None on failure."""
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


class SemanticAnalysis(BaseModel):
    """Structured result of Grok's semantic analysis of a developer's actual source code."""
    tech_skills: list[str] = Field(description="Technical skills inferred from code, max 8")
    soft_skills: list[str] = Field(description="Soft skills inferred from code style and patterns, max 6")
    architectural_patterns: list[str] = Field(description="Architectural patterns observed, max 5")
    code_quality_signals: list[str] = Field(description="Code quality indicators observed, max 5")
    domain_expertise: list[str] = Field(description="Problem domains inferred from code, max 5")
    description: str = Field(description="1-2 sentence role-fit assessment based on code analysis")


SEMANTIC_ANALYSIS_SYSTEM = """You are a senior software architect and talent evaluator for Clone.dna.

Perform deep semantic analysis of a developer's actual source code to produce a structured candidate profile.

Analyze:
1. **Architectural patterns** — MVC, event-driven, microservices, functional, reactive, CQRS, hexagonal, etc.
2. **Code quality signals** — naming conventions, modularity, error handling, test coverage, documentation quality
3. **Technical skills** — specific languages, frameworks, libraries evident in the code (not just file extensions)
4. **Domain expertise** — the problem domains this developer works in (payments, ML pipelines, compilers, etc.)
5. **Soft skills inferred** — clean code = attention to detail; good tests = quality mindset; clear docs = communication

Be specific and factual — base your analysis only on what you observe in the provided code.

Respond with a valid JSON object:
{
  "tech_skills": ["string", ...],            // max 8, specific (e.g. "Redis pub/sub", not "databases")
  "soft_skills": ["string", ...],            // max 6, inferred from code style
  "architectural_patterns": ["string", ...], // max 5
  "code_quality_signals": ["string", ...],   // max 5
  "domain_expertise": ["string", ...],       // max 5
  "description": "string"                    // 1-2 sentences on role fit
}"""


def semantic_analyze_code(
    code_samples: list[dict],
    candidate_meta: dict,
    role: str,
) -> Optional["SemanticAnalysis"]:
    """
    Run Grok semantic analysis on a candidate's actual source code samples.

    Extracts architectural patterns, code quality signals, domain expertise,
    and richer skill inference from real code — not bio keywords or language names.
    Returns None if Grok is unavailable, call fails, or no code samples provided.
    """
    if not code_samples:
        return None
    try:
        client = get_grok_client()
    except RuntimeError:
        return None

    # Build code block capped at ~9K chars across up to 3 repos
    code_block = ""
    for sample in code_samples[:3]:
        repo = sample.get("repo", "unknown")
        code = sample.get("code", "")[:3000]
        code_block += f"\n\n=== REPO: {repo} ===\n{code}"
    code_block = code_block[:9000]

    role_context = ROLE_CONTEXT.get(role, "")
    name = candidate_meta.get("name") or candidate_meta.get("github_handle", "")
    bio = (candidate_meta.get("bio") or "")[:200]

    user_message = (
        f"Developer: {name} (GitHub: {candidate_meta.get('github_handle', '')})\n"
        f"Role being evaluated for: {role.upper()}\n"
        f"Bio: {bio or 'Not provided'}\n"
        f"{role_context}\n\n"
        f"--- SOURCE CODE SAMPLES ---\n{code_block}"
    )

    try:
        response = client.chat.completions.create(
            model=GROK_MODEL,
            messages=[
                {"role": "system", "content": SEMANTIC_ANALYSIS_SYSTEM},
                {"role": "user",   "content": user_message},
            ],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        raw = response.choices[0].message.content
        data = json.loads(raw)
        return SemanticAnalysis(**data)
    except Exception as e:
        print(f"[grok] semantic analysis failed: {e}")
        return None


def candidate_extract_to_profile(extract: CandidateExtract, source_url: str = "") -> dict:
    """Convert a CandidateExtract Pydantic model to the flat profile dict shape used throughout the app."""
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
