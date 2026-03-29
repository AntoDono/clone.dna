"""Tests for .dna block packaging output structure.

Validates the JSON metadata files (manifest, eval, sources, consent)
that train_lora writes to the output directory. These tests use
pre-built dna directories from the dnas/ tree rather than running
actual training, so they work without a GPU.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


_DNAS_ROOT = Path(__file__).resolve().parent.parent / "dnas"

_REQUIRED_MANIFEST_KEYS = {
    "name", "version", "type", "candidate", "base_model",
    "rank", "alpha", "vllm_compatible", "tags", "eval_summary", "created",
}
_REQUIRED_CANDIDATE_KEYS = {"handle", "sources", "expertise_domains", "consent_verified"}
_REQUIRED_EVAL_KEYS = {"handle", "base_model", "training", "benchmarks", "teacher_model", "created"}
_REQUIRED_SOURCES_KEYS = {"handle", "repos", "license_filter", "created"}
_REQUIRED_CONSENT_KEYS = {"handle", "consent_status", "public_repos_only", "revocable"}


def _find_dna_blocks() -> list[Path]:
    """Walk the dnas/ tree and return all block directories containing manifest.json."""
    blocks = []
    if not _DNAS_ROOT.exists():
        return blocks
    for team_dir in _DNAS_ROOT.iterdir():
        if not team_dir.is_dir():
            continue
        for handle_dir in team_dir.iterdir():
            if handle_dir.is_dir() and (handle_dir / "manifest.json").exists():
                blocks.append(handle_dir)
    return blocks


def _is_full_block(block_dir: Path) -> bool:
    """Return True if the block was created by the full training pipeline (not emergency calibration)."""
    manifest = json.loads((block_dir / "manifest.json").read_text())
    return "eval_summary" in manifest and "tags" in manifest


_DNA_BLOCKS = _find_dna_blocks()
_block_ids = [f"{b.parent.name}/{b.name}" for b in _DNA_BLOCKS]


_FULL_BLOCKS = [b for b in _DNA_BLOCKS if _is_full_block(b)] if _DNA_BLOCKS else []
_full_ids = [f"{b.parent.name}/{b.name}" for b in _FULL_BLOCKS]


@pytest.mark.skipif(not _DNA_BLOCKS, reason="No .dna blocks found in dnas/")
class TestDnaPackagingBasic:
    """Tests that apply to ALL blocks (including emergency-calibrated ones)."""

    @pytest.fixture(params=_DNA_BLOCKS, ids=_block_ids)
    def block_dir(self, request) -> Path:
        return request.param

    def _load(self, block_dir: Path, name: str) -> dict:
        path = block_dir / name
        assert path.exists(), f"{name} missing from {block_dir}"
        return json.loads(path.read_text())

    def test_manifest_exists_and_valid_json(self, block_dir):
        manifest = self._load(block_dir, "manifest.json")
        assert "name" in manifest
        assert "version" in manifest
        assert "candidate" in manifest
        assert "base_model" in manifest

    def test_manifest_candidate_has_handle(self, block_dir):
        manifest = self._load(block_dir, "manifest.json")
        assert "handle" in manifest["candidate"]

    def test_vllm_compatible(self, block_dir):
        manifest = self._load(block_dir, "manifest.json")
        assert manifest.get("vllm_compatible") is True


@pytest.mark.skipif(not _FULL_BLOCKS, reason="No fully-trained .dna blocks found")
class TestDnaPackaging:
    """Tests for blocks created by the full training pipeline."""

    @pytest.fixture(params=_FULL_BLOCKS, ids=_full_ids)
    def block_dir(self, request) -> Path:
        return request.param

    def _load(self, block_dir: Path, name: str) -> dict:
        path = block_dir / name
        assert path.exists(), f"{name} missing from {block_dir}"
        return json.loads(path.read_text())

    def test_manifest_has_required_keys(self, block_dir):
        manifest = self._load(block_dir, "manifest.json")
        missing = _REQUIRED_MANIFEST_KEYS - set(manifest.keys())
        assert not missing, f"manifest.json missing keys: {missing}"

    def test_manifest_candidate_structure(self, block_dir):
        manifest = self._load(block_dir, "manifest.json")
        candidate = manifest.get("candidate", {})
        missing = _REQUIRED_CANDIDATE_KEYS - set(candidate.keys())
        assert not missing, f"manifest candidate missing keys: {missing}"

    def test_manifest_eval_summary_present(self, block_dir):
        manifest = self._load(block_dir, "manifest.json")
        eval_summary = manifest.get("eval_summary", {})
        assert "teacher_model" in eval_summary
        assert "final_loss" in eval_summary or "best_loss" in eval_summary

    def test_eval_json_structure(self, block_dir):
        if not (block_dir / "eval.json").exists():
            pytest.skip("eval.json not present (emergency calibration block)")
        eval_data = self._load(block_dir, "eval.json")
        missing = _REQUIRED_EVAL_KEYS - set(eval_data.keys())
        assert not missing, f"eval.json missing keys: {missing}"

    def test_eval_benchmarks_populated(self, block_dir):
        if not (block_dir / "eval.json").exists():
            pytest.skip("eval.json not present")
        eval_data = self._load(block_dir, "eval.json")
        benchmarks = eval_data.get("benchmarks", {})
        assert "style_consistency" in benchmarks
        assert "domain_accuracy" in benchmarks

    def test_sources_json_structure(self, block_dir):
        if not (block_dir / "sources.json").exists():
            pytest.skip("sources.json not present")
        sources = self._load(block_dir, "sources.json")
        missing = _REQUIRED_SOURCES_KEYS - set(sources.keys())
        assert not missing, f"sources.json missing keys: {missing}"
        assert isinstance(sources["repos"], list)

    def test_sources_repos_have_urls(self, block_dir):
        if not (block_dir / "sources.json").exists():
            pytest.skip("sources.json not present")
        sources = self._load(block_dir, "sources.json")
        for repo in sources["repos"]:
            assert "url" in repo, f"Repo entry missing 'url': {repo}"
            assert "name" in repo, f"Repo entry missing 'name': {repo}"

    def test_consent_json_structure(self, block_dir):
        if not (block_dir / "consent.json").exists():
            pytest.skip("consent.json not present")
        consent = self._load(block_dir, "consent.json")
        missing = _REQUIRED_CONSENT_KEYS - set(consent.keys())
        assert not missing, f"consent.json missing keys: {missing}"

    def test_consent_public_repos_only(self, block_dir):
        if not (block_dir / "consent.json").exists():
            pytest.skip("consent.json not present")
        consent = self._load(block_dir, "consent.json")
        assert consent["public_repos_only"] is True

    def test_consent_is_revocable(self, block_dir):
        if not (block_dir / "consent.json").exists():
            pytest.skip("consent.json not present")
        consent = self._load(block_dir, "consent.json")
        assert consent["revocable"] is True

    def test_profile_md_exists(self, block_dir):
        assert (block_dir / "profile.md").exists(), "profile.md missing"
        content = (block_dir / "profile.md").read_text()
        assert len(content) > 50, "profile.md seems too short"
