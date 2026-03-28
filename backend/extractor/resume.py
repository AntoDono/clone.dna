"""
Resume extractor — accepts raw resume text (paste or pre-parsed) and uses Grok
structured outputs to extract a clean candidate profile.
"""
from typing import Optional

from .schema import call_grok, candidate_extract_to_profile

_MIN_RESUME_LENGTH = 80   # characters — reject obviously empty input


def extract_from_resume(text: str, role: Optional[str] = None) -> Optional[dict]:
    """
    Parse raw resume text and extract a candidate profile via Grok.

    `text` should be the plain-text content of a resume (copy-pasted from PDF/Word,
    or the output of a PDF parser). HTML is also acceptable.

    Returns a profile dict in the same shape as github.build_profile(),
    or raises ValueError with a user-friendly message on failure.
    """
    text = text.strip()
    if len(text) < _MIN_RESUME_LENGTH:
        raise ValueError("Resume text is too short. Please paste more content.")

    extract = call_grok(text, role=role)
    if not extract:
        raise ValueError("Grok could not extract a structured profile from this resume.")

    profile = candidate_extract_to_profile(extract, source_url="")
    profile["profile_url"] = ""
    return profile
