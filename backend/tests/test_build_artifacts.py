"""Tests for workspace artifact persistence in the build router."""

from __future__ import annotations

import json

from routes import build as build_routes


def test_persist_workspace_artifact(tmp_path, monkeypatch):
    monkeypatch.setattr(build_routes, "_WORKSPACE_ROOT", tmp_path)

    path = build_routes._persist_workspace_artifact(7, "sample.json", {"ok": True})

    assert path == tmp_path / "7" / ".clone_dna" / "sample.json"
    assert json.loads(path.read_text()) == {"ok": True}


def test_persist_orchestration_run_writes_latest_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(build_routes, "_WORKSPACE_ROOT", tmp_path)
    payload = {
        "team_id": 3,
        "prompt": "Ship the feature",
        "assignments": [{"handle": "alice", "task": "Implement API"}],
    }

    run_path = build_routes._persist_orchestration_run(3, payload)
    latest_path = tmp_path / "3" / ".clone_dna" / "latest_orchestration.json"

    assert run_path.exists()
    assert run_path.parent == tmp_path / "3" / ".clone_dna" / "orchestrations"
    assert latest_path.exists()
    assert json.loads(run_path.read_text()) == payload
    assert json.loads(latest_path.read_text()) == payload
