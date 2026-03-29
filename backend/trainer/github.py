"""GitHub API helpers — fetch candidate source code for training data collection."""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Callable

import requests

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"

CODE_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".cpp", ".c", ".h", ".rb", ".swift", ".kt", ".md", ".txt",
}

MAX_CODE_BYTES = 12_000

SKIP_DIRS = ("test", "vendor", "node_modules", ".github", "dist", "__pycache__")


def _gh_headers() -> dict:
    """Build GitHub API request headers, including Bearer token if GITHUB_TOKEN is set."""
    token = os.getenv("GITHUB_TOKEN", "").strip()
    h = {"Accept": "application/vnd.github.v3+json"}
    if token and token.startswith("ghp_"):
        h["Authorization"] = f"token {token}"
    return h


def _gh_get(url: str, params: dict | None = None) -> dict | list | None:
    """Make an authenticated GET request to the GitHub API, returning parsed JSON or None on error."""
    try:
        r = requests.get(url, headers=_gh_headers(), params=params, timeout=15)
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.warning("GitHub fetch failed: %s", e)
        return None


def fetch_repo_code(owner: str, repo: str) -> str:
    """Fetch up to 4 source code blobs from a repo's HEAD tree, capped at 12KB each, annotated with file paths."""
    tree = _gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/HEAD", {"recursive": "1"})
    if not tree or not isinstance(tree, dict):
        return ""

    blobs: list[dict] = []
    for item in tree.get("tree", []):
        if item.get("type") != "blob":
            continue
        path: str = item.get("path", "")
        ext = Path(path).suffix.lower()
        if ext not in CODE_EXTENSIONS:
            continue
        if any(skip in path for skip in SKIP_DIRS):
            continue
        blobs.append(item)

    blobs = sorted(blobs, key=lambda b: len(b.get("path", "")))[:4]

    code_parts: list[str] = []
    total = 0
    for blob in blobs:
        if total >= MAX_CODE_BYTES:
            break
        sha = blob.get("sha")
        path = blob.get("path", "")
        raw = _gh_get(f"{GITHUB_API}/repos/{owner}/{repo}/git/blobs/{sha}")
        if not raw or not isinstance(raw, dict):
            continue
        encoding = raw.get("encoding")
        content_b64 = raw.get("content", "")
        if encoding == "base64":
            try:
                content = base64.b64decode(content_b64.replace("\n", "")).decode("utf-8", errors="replace")
            except Exception:
                continue
        else:
            content = content_b64
        snippet = content[:MAX_CODE_BYTES - total]
        code_parts.append(f"// ── {path} ──\n{snippet}")
        total += len(snippet)

    return "\n\n".join(code_parts)


def collect_training_data(
    candidate: dict,
    emit: Callable[[dict], None],
) -> list[dict]:
    """
    For each of the candidate's top repos, fetch real source code from GitHub.
    Returns list of {"repo": str, "code": str} dicts.
    """
    handle = candidate.get("github_handle", "")
    top_repos: list[dict] = candidate.get("top_repos", [])

    if not top_repos:
        emit({"phase": "collecting", "candidate": handle, "message": "No public repos found — skipping collection"})
        return []

    results: list[dict] = []
    for repo_meta in top_repos[:3]:
        repo_name = repo_meta.get("name", "")
        if not repo_name:
            continue

        # Only train on permissively-licensed repos (MIT, Apache-2.0, BSD, ISC, Unlicense).
        # If license metadata is missing from the profile (older cache), allow it through.
        if repo_meta.get("permissive") is False:
            license_id = repo_meta.get("license") or "unknown"
            emit({
                "phase": "collecting",
                "candidate": handle,
                "message": f"Skipping {repo_name} — license '{license_id}' is not permissive (MIT/Apache-2.0 only)",
            })
            continue

        emit({
            "phase": "collecting",
            "candidate": handle,
            "message": f"Fetching source: {handle}/{repo_name}",
        })
        code = fetch_repo_code(handle, repo_name)
        if code:
            emit({
                "phase": "collecting",
                "candidate": handle,
                "message": f"Got {len(code):,} bytes from {repo_name}",
            })
            results.append({"repo": repo_name, "code": code})
        else:
            emit({
                "phase": "collecting",
                "candidate": handle,
                "message": f"No code extracted from {repo_name}",
            })

    return results
    