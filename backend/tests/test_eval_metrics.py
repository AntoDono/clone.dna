"""Tests for the training evaluation functions in trainer/training.py."""

from __future__ import annotations

import pytest

from trainer.training import (
    compute_domain_accuracy,
    compute_humaneval_proxy,
    compute_style_metrics,
    estimate_latency_overhead_ms,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

PYTHON_SNAKE_CODE = """\
import os
from pathlib import Path

def fetch_user_data(user_id: int) -> dict:
    # Validate the user ID before querying
    if user_id <= 0:
        raise ValueError("user_id must be positive")
    result = _query_database(user_id)
    return result

def _query_database(uid: int) -> dict:
    try:
        conn = get_connection()
        return conn.execute("SELECT * FROM users WHERE id = ?", (uid,))
    except Exception as e:
        raise RuntimeError(f"DB error: {e}")
"""

JS_CAMEL_CODE = """\
import { fetchData } from './api';

function getUserProfile(userId) {
    const userData = fetchData(`/users/${userId}`);
    const formattedName = formatDisplayName(userData.name);
    return { ...userData, formattedName };
}

async function updateUserSettings(userId, newSettings) {
    try {
        const response = await fetch(`/api/users/${userId}/settings`, {
            method: 'POST',
            body: JSON.stringify(newSettings),
        });
        return response.json();
    } catch (error) {
        throw new Error(`Settings update failed: ${error.message}`);
    }
}
"""


def _make_pairs(*code_samples: str) -> list[dict]:
    return [
        {"instruction": f"Task {i}", "response": code}
        for i, code in enumerate(code_samples)
    ]


# ── compute_style_metrics ─────────────────────────────────────────────────────


class TestComputeStyleMetrics:
    def test_empty_pairs(self):
        result = compute_style_metrics([])
        assert result == {"consistency_score": None}

    def test_blank_responses(self):
        result = compute_style_metrics([{"instruction": "x", "response": ""}])
        assert result == {"consistency_score": None}

    def test_snake_case_detection(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE)
        result = compute_style_metrics(pairs)
        assert result["naming_convention"] == "snake_case"
        assert result["naming_dominance"] > 0.5

    def test_camel_case_detection(self):
        pairs = _make_pairs(JS_CAMEL_CODE)
        result = compute_style_metrics(pairs)
        assert result["naming_convention"] == "camelCase"
        assert result["naming_dominance"] > 0.5

    def test_consistency_score_bounded(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE, PYTHON_SNAKE_CODE)
        result = compute_style_metrics(pairs)
        assert result["consistency_score"] is not None
        assert 0.0 <= result["consistency_score"] <= 1.0

    def test_avg_line_length_positive(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE)
        result = compute_style_metrics(pairs)
        assert result["avg_line_length"] > 0

    def test_comment_density_nonnegative(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE)
        result = compute_style_metrics(pairs)
        assert result["comment_density"] >= 0.0

    def test_all_keys_present(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE)
        result = compute_style_metrics(pairs)
        expected_keys = {
            "naming_convention",
            "naming_dominance",
            "avg_line_length",
            "comment_density",
            "avg_function_length",
            "consistency_score",
        }
        assert set(result.keys()) == expected_keys

    def test_high_consistency_for_uniform_style(self):
        uniform = _make_pairs(PYTHON_SNAKE_CODE, PYTHON_SNAKE_CODE, PYTHON_SNAKE_CODE)
        result = compute_style_metrics(uniform)
        assert result["consistency_score"] >= 0.7


# ── compute_domain_accuracy ───────────────────────────────────────────────────


class TestComputeDomainAccuracy:
    def test_empty_pairs(self):
        assert compute_domain_accuracy([], {"skills": ["python"]}) is None

    def test_no_keywords(self):
        pairs = _make_pairs("some code")
        candidate = {"skills": [], "languages": {}, "top_repos": []}
        assert compute_domain_accuracy(pairs, candidate) is None

    def test_single_char_keywords_filtered(self):
        pairs = _make_pairs("x = 1")
        candidate = {"skills": ["x"], "languages": {}, "top_repos": []}
        assert compute_domain_accuracy(pairs, candidate) is None

    def test_full_coverage(self):
        pairs = [{"instruction": "Build a python backend with fastapi", "response": "import fastapi"}]
        candidate = {"skills": ["python", "fastapi"], "languages": {}, "top_repos": []}
        score = compute_domain_accuracy(pairs, candidate)
        assert score is not None
        assert score > 0.5

    def test_partial_coverage(self):
        pairs = [{"instruction": "Build with python", "response": "print('hello')"}]
        candidate = {
            "skills": ["python", "rust", "kubernetes"],
            "languages": {},
            "top_repos": [],
        }
        score = compute_domain_accuracy(pairs, candidate)
        assert score is not None
        assert 0.0 < score < 1.0

    def test_bounded_zero_to_one(self):
        pairs = _make_pairs("completely unrelated code with no keywords")
        candidate = {
            "skills": ["quantum", "aerospace"],
            "languages": {"haskell": 100},
            "top_repos": [],
        }
        score = compute_domain_accuracy(pairs, candidate)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_includes_repo_topics(self):
        pairs = [{"instruction": "Use graphql", "response": "query { user { name } }"}]
        candidate = {
            "skills": [],
            "languages": {},
            "top_repos": [{"topics": ["graphql"]}],
        }
        score = compute_domain_accuracy(pairs, candidate)
        assert score is not None
        assert score > 0.0


# ── compute_humaneval_proxy ───────────────────────────────────────────────────


class TestComputeHumanevalProxy:
    def test_empty_pairs(self):
        assert compute_humaneval_proxy([]) is None

    def test_blank_responses(self):
        assert compute_humaneval_proxy([{"response": "   "}]) is None

    def test_high_quality_code(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE)
        score = compute_humaneval_proxy(pairs)
        assert score is not None
        assert score >= 0.6

    def test_minimal_code(self):
        pairs = _make_pairs("x = 1")
        score = compute_humaneval_proxy(pairs)
        assert score is not None
        assert score < 0.5

    def test_bounded_zero_to_one(self):
        pairs = _make_pairs(PYTHON_SNAKE_CODE, JS_CAMEL_CODE)
        score = compute_humaneval_proxy(pairs)
        assert score is not None
        assert 0.0 <= score <= 1.0


# ── estimate_latency_overhead_ms ──────────────────────────────────────────────


class TestEstimateLatencyOverhead:
    def test_default_params(self):
        ms = estimate_latency_overhead_ms()
        assert ms > 0
        assert ms <= 50.0

    def test_higher_rank_more_overhead(self):
        low = estimate_latency_overhead_ms(rank=8)
        high = estimate_latency_overhead_ms(rank=64)
        assert high > low

    def test_more_modules_more_overhead(self):
        few = estimate_latency_overhead_ms(num_adapted_modules=2)
        many = estimate_latency_overhead_ms(num_adapted_modules=8)
        assert many > few

    def test_minimum_clamp(self):
        ms = estimate_latency_overhead_ms(rank=1, num_adapted_modules=1)
        assert ms >= 1.0

    def test_maximum_clamp(self):
        ms = estimate_latency_overhead_ms(rank=128, num_adapted_modules=16)
        assert ms <= 50.0
