"""
Website extractor — fetches a URL, strips HTML, sends clean text to Grok for
structured candidate profile extraction.
"""
import re
from typing import Optional
import requests
from bs4 import BeautifulSoup

from .schema import call_grok, candidate_extract_to_profile


_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Tags whose content we fully discard
_SKIP_TAGS = {"script", "style", "noscript", "svg", "img", "video", "audio", "nav", "footer"}


def _fetch_text(url: str, timeout: int = 12) -> Optional[str]:
    """Fetch a URL and return the cleaned visible text content."""
    try:
        resp = requests.get(url, headers=_REQUEST_HEADERS, timeout=timeout, allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as e:
        raise ValueError(f"Could not fetch '{url}': {e}") from e

    soup = BeautifulSoup(resp.text, "lxml")

    # Remove noise tags
    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    # Prefer main content areas
    for selector in ("main", "article", '[role="main"]', ".content", "#content"):
        node = soup.select_one(selector)
        if node:
            text = node.get_text(separator="\n", strip=True)
            if len(text) > 200:
                return text

    # Fall back to body text
    body = soup.body
    text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)

    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_from_website(url: str, role: Optional[str] = None) -> Optional[dict]:
    """
    Scrape `url` and extract a candidate profile via Grok.

    Returns a profile dict in the same shape as github.build_profile(),
    or raises ValueError with a user-friendly message on failure.
    """
    text = _fetch_text(url)
    if not text or len(text) < 100:
        raise ValueError("Page content is too short or empty to extract a profile from.")

    extract = call_grok(text, role=role)
    if not extract:
        raise ValueError("Grok could not extract a structured profile from this page.")

    profile = candidate_extract_to_profile(extract, source_url=url)
    profile["profile_url"] = url
    return profile
