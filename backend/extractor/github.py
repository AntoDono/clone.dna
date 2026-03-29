"""GitHub API integration for candidate search, profile extraction, and skill inference from bios and repo metadata."""

import json
import logging
import os
import random
from datetime import datetime, timedelta
from typing import Optional
import requests

from .schema import generate_github_description, semantic_analyze_code
from trainer.github import fetch_repo_code, fetch_recent_commits, compute_commit_velocity

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
_CACHE_TTL = timedelta(hours=24)

# ── Search queries per role ───────────────────────────────────────────────────

ROLE_QUERIES: dict[str, str] = {
    "pm":       "product manager in:bio followers:>80",
    "swe":      "software engineer developer in:bio repos:>10 followers:>20",
    "designer": "designer UI UX in:bio followers:>40",
}

# ── Technical skills inferred from primary repo language ─────────────────────

LANG_SKILL_MAP: dict[str, str] = {
    "Python":           "Python",
    "JavaScript":       "JavaScript",
    "TypeScript":       "TypeScript",
    "Rust":             "Rust",
    "Go":               "Go",
    "Java":             "Java",
    "C++":              "C++",
    "C":                "C / Systems",
    "CSS":              "CSS",
    "SCSS":             "CSS / SCSS",
    "HTML":             "HTML",
    "Vue":              "Vue.js",
    "Swift":            "iOS / Swift",
    "Kotlin":           "Android / Kotlin",
    "Jupyter Notebook": "Data Science",
    "R":                "R / Statistics",
    "Dart":             "Flutter / Dart",
    "Ruby":             "Ruby",
    "PHP":              "PHP",
    "Shell":            "Shell Scripting",
    "Dockerfile":       "Docker",
}

# ── Bio keyword → soft or domain skill ───────────────────────────────────────
# Each entry: (list of trigger substrings, skill label)
# Matched case-insensitively against the user's bio + company + blog fields.

BIO_SKILL_PATTERNS: list[tuple[list[str], str]] = [
    # Product / PM
    (["product manager", "pm @", "product lead", "head of product"], "Product Management"),
    (["roadmap", "road map"],                                          "Roadmapping"),
    (["strategy", "strategic"],                                        "Product Strategy"),
    (["agile", "scrum", "sprint"],                                     "Agile / Scrum"),
    (["user research", "user testing", "ux research", "user interview"],"User Research"),
    (["data-driven", "metrics", "kpi", "okr", "analytics"],            "Data-Driven Thinking"),
    (["stakeholder", "cross-functional", "cross functional"],           "Stakeholder Management"),
    (["growth", "growth hacking", "acquisition", "retention"],         "Growth"),
    (["launch", "gtm", "go-to-market"],                                "Go-to-Market"),
    (["prioriti"],                                                      "Prioritization"),
    # Leadership
    (["leadership", "director", "head of", "vp ", "vice president"],   "Leadership"),
    (["mentor", "mentoring", "teach", "coaching"],                      "Mentorship"),
    (["founder", "co-founder", "cto", "ceo", "startup"],               "Startup / Founding"),
    # Design
    (["figma", "sketch", "adobe xd", "framer"],                        "Figma / Design Tools"),
    (["ux", "user experience"],                                         "UX Design"),
    (["ui", "user interface", "interface design"],                      "UI Design"),
    (["accessibility", "a11y", "wcag"],                                 "Accessibility"),
    (["branding", "brand design", "visual identity"],                   "Brand Design"),
    (["motion", "animation", "micro-interaction"],                      "Motion Design"),
    (["design system", "component library", "storybook"],              "Design Systems"),
    (["typography", "typographic"],                                     "Typography"),
    (["illustration", "illustrat"],                                     "Illustration"),
    # Engineering
    (["open source", "open-source"],                                    "Open Source"),
    (["machine learning", "deep learning", "ml ", "nlp"],              "ML / AI"),
    (["cloud", "aws", "gcp", "azure", "serverless"],                   "Cloud / Infra"),
    (["devops", "ci/cd", "infrastructure", "k8s", "kubernetes"],       "DevOps"),
    (["security", "infosec", "cybersec", "pen test"],                  "Security"),
    (["mobile", "react native", "expo"],                               "Mobile"),
    (["backend", "back-end", "server-side", "api"],                    "Backend"),
    (["frontend", "front-end", "client-side"],                         "Frontend"),
    (["fullstack", "full stack", "full-stack"],                        "Full Stack"),
    (["distributed system", "microservice", "event-driven"],           "Distributed Systems"),
    (["blockchain", "web3", "solidity", "ethereum", "defi"],           "Web3"),
    (["research", "researcher", "phd", "postdoc", "academia"],        "Research"),
    (["writer", "writing", "technical writer", "blog"],               "Technical Writing"),
    (["community", "developer advocate", "devrel"],                    "Developer Relations"),
]

# ── Role-fit description templates (picked randomly, varied per run) ──────────

ROLE_DESCRIPTIONS: dict[str, list[str]] = {
    "pm": [
        "Strategic product thinker who bridges user needs with business outcomes.",
        "User-obsessed PM with a bias toward data-informed decisions and clear roadmaps.",
        "Cross-functional leader experienced in shipping 0→1 and scaling products.",
        "Product leader who combines qualitative user research with quantitative analytics.",
        "Outcome-oriented PM with a track record of aligning engineering and design teams.",
    ],
    "swe": [
        "Systems engineer who ships clean, maintainable code at scale.",
        "Full-stack engineer with a strong open-source contribution history.",
        "Backend specialist focused on distributed systems and API design.",
        "Infrastructure-minded engineer who builds reliable platforms from the ground up.",
        "Pragmatic engineer who values simplicity, testing, and iterative delivery.",
    ],
    "designer": [
        "Visual systems designer with a sharp eye for interaction and detail.",
        "UX-led designer who transforms complex flows into intuitive experiences.",
        "Interface and brand designer specializing in cohesive design systems.",
        "Motion and interaction designer focused on delightful, accessible interfaces.",
        "Research-grounded designer who validates assumptions before pushing pixels.",
    ],
}

# ── Fallback soft skills when bio is sparse ───────────────────────────────────

ROLE_SOFT_SKILL_FALLBACKS: dict[str, list[str]] = {
    "pm": [
        "Product Strategy", "User Research", "Roadmapping",
        "Agile / Scrum", "Stakeholder Management", "Data-Driven Thinking",
    ],
    "swe": [
        "System Design", "Code Review", "Testing", "DevOps", "Open Source",
    ],
    "designer": [
        "UX Design", "UI Design", "Figma / Design Tools",
        "Design Systems", "User Research", "Prototyping",
    ],
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _headers() -> dict:
    """Build GitHub API request headers, including Bearer token if GITHUB_TOKEN is set."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    h = {"Accept": "application/vnd.github.v3+json"}
    # Only attach token if it looks like a real GitHub token (not the placeholder)
    if token and token != "ghp_your_token_here" and token.startswith("ghp_"):
        h["Authorization"] = f"token {token}"
        logger.debug("GitHub API: using authenticated requests")
    else:
        logger.debug("GitHub API: using unauthenticated requests (rate limit: 60 req/hr)")
    return h


def _get(url: str, params: Optional[dict] = None) -> Optional[dict | list]:
    """Make an authenticated GET request to the GitHub API, returning parsed JSON or None on error."""
    try:
        resp = requests.get(url, headers=_headers(), params=params, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        logger.warning("GitHub API %s returned %d: %s", url, resp.status_code, resp.text[:200])
        return None
    except requests.RequestException as e:
        logger.warning("GitHub API request failed: %s", e)
        return None


# ── Core functions ────────────────────────────────────────────────────────────

def search_users_raw(role: str, limit: int = 10) -> list[str]:
    """Return a list of GitHub login handles for a given role without building full profiles."""
    query = ROLE_QUERIES.get(role, f"{role} developer in:bio")
    data = _get(
        f"{GITHUB_API}/search/users",
        params={"q": query, "per_page": limit, "sort": "followers"},
    )
    if not data or not isinstance(data, dict):
        return []
    return [user["login"] for user in data.get("items", [])[:limit]]


def search_candidates(role: str, limit: int = 10, force: bool = False) -> list[dict]:
    """Search GitHub for candidates by role and build full profiles for each handle. Expensive — fetches repos and languages per candidate."""
    query = ROLE_QUERIES.get(role, f"{role} developer in:bio")
    data = _get(
        f"{GITHUB_API}/search/users",
        params={"q": query, "per_page": limit, "sort": "followers"},
    )
    if not data or not isinstance(data, dict):
        return []

    profiles = []
    for user in data.get("items", [])[:limit]:
        profile = build_profile(user["login"], role=role, force=force)
        if profile:
            profiles.append(profile)
    return profiles


def build_profile(handle: str, role: Optional[str] = None, force: bool = False) -> Optional[dict]:
    """
    Build a structured candidate profile by combining GitHub metadata with
    Grok-powered semantic analysis of the candidate's actual source code.

    Results are cached in SQLite for 24 hours. Pass force=True to bypass the
    cache and re-fetch from GitHub (used when the user clicks Refresh).

    Two-pass approach:
      1. Keyword baseline — language names, bio patterns, and repo topics produce
         an initial skill set that always succeeds even if Grok is unavailable.
      2. Semantic enrichment — fetches real source code from the candidate's top
         3 repos, then calls Grok to extract architectural patterns, code quality
         signals, domain expertise, and semantically-grounded skills. Semantic
         results take priority over keyword-derived ones when available.
    """
    cache_role = role or "swe"

    # ── SQLite cache read ─────────────────────────────────────────────────────
    if not force:
        try:
            from models import GithubProfileCache
            cutoff = datetime.utcnow() - _CACHE_TTL
            row = (
                GithubProfileCache
                .select()
                .where(
                    GithubProfileCache.github_handle == handle,
                    GithubProfileCache.role == cache_role,
                    GithubProfileCache.cached_at >= cutoff,
                )
                .first()
            )
            if row:
                logger.debug("GitHub profile cache hit: %s (%s)", handle, cache_role)
                return json.loads(row.profile_json)
        except Exception as exc:
            logger.debug("GitHub profile cache read error: %s", exc)

    user = _get(f"{GITHUB_API}/users/{handle}")
    if not user or not isinstance(user, dict):
        return None

    repos_data = _get(
        f"{GITHUB_API}/users/{handle}/repos",
        params={"sort": "stars", "per_page": 8, "type": "owner"},
    ) or []

    # ── Repos + language counting ─────────────────────────────────────────────
    top_repos: list[dict] = []
    lang_counts: dict[str, int] = {}

    _PERMISSIVE_LICENSES = {"mit", "apache-2.0", "bsd-2-clause", "bsd-3-clause", "isc", "unlicense"}

    for repo in (repos_data if isinstance(repos_data, list) else []):
        if repo.get("fork"):
            continue
        lang = repo.get("language")
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        license_obj = repo.get("license") or {}
        license_id  = (license_obj.get("spdx_id") or "").lower()
        top_repos.append({
            "name":        repo["name"],
            "description": (repo.get("description") or "")[:120],
            "stars":       repo.get("stargazers_count", 0),
            "language":    lang or "",
            "url":         repo.get("html_url", ""),
            "topics":      repo.get("topics", [])[:4],
            "license":     license_obj.get("spdx_id") or "",
            "permissive":  license_id in _PERMISSIVE_LICENSES,
        })

    top_repos = sorted(top_repos, key=lambda r: r["stars"], reverse=True)[:5]

    total = sum(lang_counts.values()) or 1
    lang_pct = {
        lang: round(count / total * 100, 1)
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])
    }

    # ── Pass 1: Keyword baseline (languages + bio patterns) ───────────────────
    baseline_tech: list[str] = []
    for lang in list(lang_pct.keys())[:4]:
        mapped = LANG_SKILL_MAP.get(lang)
        if mapped and mapped not in baseline_tech:
            baseline_tech.append(mapped)
    for repo in top_repos:
        for topic in repo.get("topics", [])[:2]:
            label = topic.replace("-", " ").title()
            if label not in baseline_tech and len(baseline_tech) < 6:
                baseline_tech.append(label)

    bio_text = " ".join(filter(None, [
        user.get("bio") or "",
        user.get("company") or "",
        user.get("blog") or "",
    ])).lower()
    baseline_soft: list[str] = []
    for triggers, label in BIO_SKILL_PATTERNS:
        if any(t in bio_text for t in triggers) and label not in baseline_soft:
            baseline_soft.append(label)
    if role and len(baseline_soft) < 3:
        for fallback in ROLE_SOFT_SKILL_FALLBACKS.get(role, []):
            if fallback not in baseline_soft and len(baseline_soft) < 6:
                baseline_soft.append(fallback)

    # ── Pass 2: Semantic enrichment via Grok code + commit analysis ──────────
    code_samples: list[dict] = []
    commit_history: list[dict] = []
    all_commits: list[dict] = []  # flat list for velocity computation

    for repo in top_repos[:3]:
        repo_name = repo["name"]
        try:
            code = fetch_repo_code(handle, repo_name)
            if code:
                code_samples.append({"repo": repo_name, "code": code})
        except Exception:
            pass
        try:
            commits = fetch_recent_commits(handle, repo_name, limit=25)
            if commits:
                commit_history.append({
                    "repo": repo_name,
                    "messages": [c["message"] for c in commits],
                })
                all_commits.extend(commits)
        except Exception:
            pass

    commit_velocity = compute_commit_velocity(all_commits)

    semantic = None
    if code_samples:
        candidate_meta = {
            "github_handle": handle,
            "name": user.get("name") or handle,
            "bio": user.get("bio") or "",
        }
        semantic = semantic_analyze_code(
            code_samples,
            candidate_meta,
            role or "swe",
            commit_history=commit_history or None,
        )

    if semantic:
        # Semantic results take priority; baseline fills gaps
        tech_skills = list(dict.fromkeys(semantic.tech_skills + baseline_tech))[:8]
        soft_skills = list(dict.fromkeys(semantic.soft_skills + baseline_soft))[:8]
        description            = semantic.description
        architectural_patterns = semantic.architectural_patterns
        code_quality_signals   = semantic.code_quality_signals
        domain_expertise       = semantic.domain_expertise
        commit_themes          = semantic.commit_themes
    else:
        tech_skills = baseline_tech
        soft_skills = baseline_soft
        profile_so_far = {
            "name": user.get("name") or handle,
            "bio": (user.get("bio") or "")[:200],
            "location": user.get("location") or "",
            "followers": user.get("followers", 0),
            "public_repos": user.get("public_repos", 0),
            "top_repos": top_repos,
            "languages": lang_pct,
            "skills": baseline_tech,
        }
        description = generate_github_description(profile_so_far, role or "swe")
        if not description:
            description = random.choice(ROLE_DESCRIPTIONS.get(role or "swe", ROLE_DESCRIPTIONS["swe"]))
        architectural_patterns = []
        code_quality_signals   = []
        domain_expertise       = []
        commit_themes          = []

    # ── Combined skills list (soft first for non-technical roles) ─────────────
    if role in ("pm", "designer"):
        skills = soft_skills + [s for s in tech_skills if s not in soft_skills]
    else:
        skills = tech_skills + [s for s in soft_skills if s not in tech_skills]
    skills = skills[:10]

    profile = {
        "github_handle":        handle,
        "name":                 user.get("name") or handle,
        "avatar_url":           user.get("avatar_url"),
        "bio":                  (user.get("bio") or "")[:200],
        "location":             user.get("location") or "",
        "followers":            user.get("followers", 0),
        "public_repos":         user.get("public_repos", 0),
        "top_repos":            top_repos,
        "languages":            lang_pct,
        "skills":               skills,
        "soft_skills":          soft_skills,
        "description":          description,
        "profile_url":          user.get("html_url", f"https://github.com/{handle}"),
        # Semantic signals — present when code analysis succeeded, empty otherwise
        "architectural_patterns": architectural_patterns,
        "code_quality_signals":   code_quality_signals,
        "domain_expertise":       domain_expertise,
        # Commit-derived signals — intent layer from commit history
        "commit_themes":          commit_themes,
        "commit_velocity":        commit_velocity,
    }

    # ── SQLite cache write ────────────────────────────────────────────────────
    try:
        from models import GithubProfileCache
        GithubProfileCache.insert(
            github_handle=handle,
            role=cache_role,
            profile_json=json.dumps(profile),
            cached_at=datetime.utcnow(),
        ).on_conflict_replace().execute()
        logger.debug("GitHub profile cached: %s (%s)", handle, cache_role)
    except Exception as exc:
        logger.debug("GitHub profile cache write error: %s", exc)

    return profile
