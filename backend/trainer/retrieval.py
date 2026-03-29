"""
RAG-DNA: Retrieval-Augmented Inference over a developer's own training pairs.

After a .dna block is minted, its training pairs are stored alongside the adapter
weights as pairs.json.  At inference time, this module retrieves the most
semantically relevant pairs for a given query and injects them as few-shot
examples into the system prompt.

This gives the DNA block a dual signal:
  1. Parametric memory — fine-tuned LoRA weights encoding the developer's style
  2. Retrieved memory  — the exact code examples most relevant to the current task

Retrieval algorithm: BM25-lite using unigram + bigram TF-IDF with inverse
document frequency computed over the block's own pair corpus.  No external
dependencies beyond the standard library — works on every deployment target.

Typical usage in build.py chat route:
    from trainer.retrieval import retrieve_context_pairs
    snippets = retrieve_context_pairs(lora_path, user_message, top_k=3)
    # snippets → list[{"instruction": str, "response": str, "score": float}]
    # Prepend to system prompt as few-shot examples.
"""

from __future__ import annotations

import json
import math
import re
import string
from pathlib import Path


# ── Tokenisation ──────────────────────────────────────────────────────────────

_PUNCT = re.compile(r"[^\w\s]")
_WS    = re.compile(r"\s+")


def _tokenise(text: str) -> list[str]:
    """Lowercase, strip punctuation, split into unigrams + bigrams."""
    text = _PUNCT.sub(" ", text.lower())
    words = [w for w in _WS.split(text) if len(w) > 1]
    unigrams = words
    bigrams  = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    return unigrams + bigrams


# ── BM25-lite ─────────────────────────────────────────────────────────────────

_K1 = 1.5  # term saturation
_B  = 0.75 # length normalisation


class _BM25Index:
    """In-memory BM25 index built over a list of text documents."""

    def __init__(self, docs: list[str]) -> None:
        self._n = len(docs)
        self._tokens: list[list[str]] = [_tokenise(d) for d in docs]
        self._avgdl = sum(len(t) for t in self._tokens) / max(1, self._n)

        # Document frequency per term
        df: dict[str, int] = {}
        for tok_list in self._tokens:
            for term in set(tok_list):
                df[term] = df.get(term, 0) + 1
        self._idf: dict[str, float] = {
            term: math.log((self._n - freq + 0.5) / (freq + 0.5) + 1.0)
            for term, freq in df.items()
        }

    def score(self, query: str, doc_idx: int) -> float:
        """BM25 score of a single document against the query."""
        q_terms = _tokenise(query)
        tok_list = self._tokens[doc_idx]
        dl = len(tok_list)
        tf_map: dict[str, int] = {}
        for term in tok_list:
            tf_map[term] = tf_map.get(term, 0) + 1

        score = 0.0
        for term in q_terms:
            if term not in self._idf:
                continue
            tf = tf_map.get(term, 0)
            idf = self._idf[term]
            numerator   = tf * (_K1 + 1)
            denominator = tf + _K1 * (1 - _B + _B * dl / self._avgdl)
            score += idf * (numerator / denominator)
        return score

    def top_k(self, query: str, k: int = 3) -> list[tuple[int, float]]:
        """Return (doc_idx, score) pairs for the top-k matches, sorted descending."""
        scores = [(i, self.score(query, i)) for i in range(self._n)]
        scores.sort(key=lambda x: x[1], reverse=True)
        return [(i, round(s, 4)) for i, s in scores[:k] if s > 0]


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve_context_pairs(
    lora_path: str,
    query: str,
    top_k: int = 3,
) -> list[dict]:
    """
    Retrieve the most relevant training pairs from a DNA block for a given query.

    Reads pairs.json from the block directory, builds a BM25 index over the
    concatenated instruction+response text of each pair, and returns the top-k
    matches enriched with their BM25 score.

    Args:
        lora_path: Path to the .dna block directory (same path passed to load_adapter).
        query:     The user's current message / task description.
        top_k:     Number of pairs to return (default 3).

    Returns:
        List of dicts with keys: instruction, response, score.
        Empty list if pairs.json is missing or contains fewer than 2 pairs.
    """
    pairs_path = Path(lora_path) / "pairs.json"
    if not pairs_path.exists():
        return []

    try:
        pairs: list[dict] = json.loads(pairs_path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if len(pairs) < 2:
        return []

    # Build retrieval corpus: concatenated instruction + response per pair
    docs = [
        f"{p.get('instruction', '')} {p.get('response', '')}".strip()
        for p in pairs
    ]

    index = _BM25Index(docs)
    hits = index.top_k(query, k=top_k)

    return [
        {
            "instruction": pairs[i].get("instruction", ""),
            "response":    pairs[i].get("response", ""),
            "score":       score,
        }
        for i, score in hits
    ]


def format_retrieved_pairs(pairs: list[dict], max_chars: int = 1200) -> str:
    """
    Format retrieved pairs as a compact few-shot block for system prompt injection.

    Trims long responses to stay within max_chars total so the context window
    isn't overwhelmed.  Returns an empty string if pairs is empty.
    """
    if not pairs:
        return ""

    budget = max_chars
    parts: list[str] = ["--- Relevant code examples from this developer's work ---"]

    for i, pair in enumerate(pairs, 1):
        instruction = pair.get("instruction", "").strip()
        response    = pair.get("response", "").strip()

        # Trim response to fit within remaining budget
        header = f"\n[Example {i}]\nTask: {instruction}\nCode:\n"
        remaining = budget - len(header) - 10
        if remaining <= 0:
            break
        if len(response) > remaining:
            response = response[:remaining] + "…"

        block = header + response
        budget -= len(block)
        parts.append(block)

        if budget <= 0:
            break

    parts.append("--- End examples ---")
    return "\n".join(parts)
