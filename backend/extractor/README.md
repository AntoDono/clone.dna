# Clone.dna — Extractor Module

The `extractor/` package builds structured candidate profiles from three sources: GitHub profiles, personal websites, and resume text. All three paths normalize to the same profile shape and feed into the Grok-powered schema extraction layer.

---

## Module Map

| File | Responsibility |
|---|---|
| `github.py` | Search GitHub for candidates by role, fetch repo/language/bio data, build structured profiles |
| `website.py` | Scrape a personal site or portfolio URL, extract meaningful text, pass to Grok |
| `resume.py` | Accept raw resume text, validate length, pass to Grok for structured extraction |
| `schema.py` | Grok client, `CandidateExtract` and `SemanticAnalysis` Pydantic models, role-aware system prompts, semantic code analysis |

---

## Shared Output Shape

All three extractors return a profile dict with the following fields:

```python
{
    "github_handle": str,        # derived from name for non-GitHub sources
    "name": str,
    "avatar_url": str | None,
    "bio": str | None,
    "location": str | None,
    "followers": int,
    "public_repos": int,
    "skills": list[str],         # merged technical + soft skills, ordered by relevance
    "soft_skills": list[str],    # communication, leadership, domain skills
    "languages": dict[str, float],  # language → % of repos using it
    "top_repos": list[dict],     # [{name, url, stars, description, language, topics}]
    "description": str,          # role-fit summary (Grok-generated)
    # GitHub-only — present when semantic code analysis succeeded, empty lists otherwise:
    "architectural_patterns": list[str],  # e.g. ["event-driven", "layered architecture"]
    "code_quality_signals": list[str],    # e.g. ["consistent error handling", "typed interfaces"]
    "domain_expertise": list[str],        # e.g. ["distributed systems", "payments"]
}
```

---

## GitHub Extractor (`github.py`)

### Candidate search

`search_users_raw(role)` queries the GitHub Users Search API using role-specific queries:

| Role | Query strategy |
|---|---|
| `pm` | Bio keywords: "product manager", "program manager", follower thresholds |
| `swe` | High follower/repo counts, language-agnostic |
| `designer` | Bio keywords: "designer", "UX", "UI", "Figma" |

Returns up to 5 GitHub handles per role.

`search_candidates(role, handles)` builds full profiles for a list of handles by calling `build_profile` on each.

### Profile building (`build_profile`)

`build_profile(handle, role)` uses a **two-pass approach** to build the richest possible candidate profile:

**Pass 1 — Keyword baseline** (always runs, no Grok required):
1. **User metadata** — name, avatar, bio, location, followers, public_repos via `GET /users/{handle}`
2. **Top 8 repos by star count** — via `GET /users/{handle}/repos?sort=stars&per_page=8`
3. **Language percentages** — normalized from repo primary language counts
4. **Technical skills** — derived from `LANG_SKILL_MAP` (language → skill label) and repo topics
5. **Soft skills** — derived from `BIO_SKILL_PATTERNS` (50+ patterns matching bio, company, and blog fields); padded with `ROLE_SOFT_SKILL_FALLBACKS` when bio is sparse

**Pass 2 — Semantic enrichment** (runs when Grok is available):
1. Fetches actual source code from the top 3 repos using `trainer.github.fetch_repo_code()` (up to 12KB per repo)
2. Passes code samples to `semantic_analyze_code()` (see below) for deep analysis
3. Semantic results **take priority** over keyword-derived skills; baseline fills any gaps

When semantic analysis succeeds, the profile includes `architectural_patterns`, `code_quality_signals`, and `domain_expertise` fields from the code. The description is also Grok-generated from code context rather than from bio metadata alone.

**Fallback chain for description**: semantic analysis → `generate_github_description()` (bio-based Grok call) → random template from `ROLE_DESCRIPTIONS`.

---

## Website Extractor (`website.py`)

`extract_from_website(url)` scrapes a personal site or portfolio and runs Grok extraction.

### Scraping strategy (`_fetch_text`)

1. Fetches the URL with a browser User-Agent string via `httpx`
2. Parses HTML with `BeautifulSoup` + `lxml`
3. Removes `<script>`, `<style>`, `<nav>`, `<footer>` tags
4. Prefers content from semantic elements in order: `<main>`, `<article>`, `[role="main"]`, `.content`, `#content`
5. Falls back to full `<body>` text
6. Collapses excessive whitespace

Requires at least **100 characters** of extracted text to proceed. Raises `ValueError` on insufficient content.

Passes the cleaned text to `call_grok()` for structured profile extraction.

---

## Resume Extractor (`resume.py`)

`extract_from_resume(text)` accepts raw resume text (pre-extracted by the frontend or caller).

- Validates minimum length of **80 characters**
- Passes text directly to `call_grok()` for structured extraction
- Returns the normalized profile dict or raises `ValueError`

---

## Grok Extraction Layer (`schema.py`)

### `CandidateExtract` (Pydantic model)

```python
class CandidateExtract(BaseModel):
    name: str
    bio: str | None
    location: str | None
    skills: list[str]           # technical skills extracted from content
    soft_skills: list[str]      # soft skills and domain expertise
    description: str            # one-sentence role-fit summary
    languages: dict[str, float] # inferred programming languages with confidence
```

### `SemanticAnalysis` (Pydantic model)

Returned by `semantic_analyze_code()` — represents deep code-level analysis:

```python
class SemanticAnalysis(BaseModel):
    tech_skills: list[str]           # specific skills found in code (e.g. "Redis pub/sub")
    soft_skills: list[str]           # inferred from code style (e.g. "attention to detail")
    architectural_patterns: list[str] # observed patterns (e.g. "event-driven", "CQRS")
    code_quality_signals: list[str]  # quality indicators (e.g. "consistent error handling")
    domain_expertise: list[str]      # problem domains (e.g. "distributed systems")
    description: str                 # 1-2 sentence role-fit assessment from code
```

### `semantic_analyze_code(code_samples, candidate_meta, role)`

Calls Grok (`grok-4.20-0309-non-reasoning`) with up to 3 code samples (capped at ~9K chars total) and a role-aware analysis prompt. The model is instructed to analyze:

- **Architectural patterns** — identifies design patterns used (MVC, event-driven, microservices, CQRS, hexagonal, functional, etc.)
- **Code quality signals** — naming conventions, modularity, error handling patterns, test coverage presence, documentation density
- **Technical skills** — specific libraries, frameworks, and tools used in code (not just file extensions)
- **Domain expertise** — the problem domains the developer operates in, inferred from function names, data structures, and API designs
- **Soft skills** — inferred from code style: clean code → attention to detail; good tests → quality mindset; clear docstrings → communication

Returns `None` if Grok is unavailable or no code samples are provided.

### `call_grok(content, role)`

Makes a single Grok API call (`grok-4.20-0309-non-reasoning`) with:
- A role-aware system prompt that frames extraction differently for `pm`, `swe`, and `designer` roles
- `response_format={"type": "json_object"}` for structured output
- Returns a validated `CandidateExtract` instance or `None` on failure

### Role-aware system prompts

Each role has a different extraction context:
- **PM**: emphasizes product leadership, stakeholder communication, roadmap ownership
- **SWE**: emphasizes technical depth, language/framework expertise, system design
- **Designer**: emphasizes visual tools (Figma, Sketch), UX process, accessibility

### `candidate_extract_to_profile(extract, handle)`

Converts a `CandidateExtract` to the shared profile dict shape. The `github_handle` is derived from `name.lower().replace(" ", "")` for non-GitHub sources.
