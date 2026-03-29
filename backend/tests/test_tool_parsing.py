"""Tests for tool-call parsing and tool execution in trainer/inference.py and trainer/tools.py."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

from trainer.inference import _parse_tool_calls
from trainer.tools import execute_tool, _safe_path


# ── _parse_tool_calls ────────────────────────────────────────────────────────


class TestParseToolCalls:
    def test_single_tool_call(self):
        text = '<tool_call>\n{"name": "write_file", "arguments": {"path": "main.py", "content": "print(1)"}}\n</tool_call>'
        calls = _parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "write_file"
        assert calls[0]["arguments"]["path"] == "main.py"

    def test_multiple_tool_calls(self):
        text = (
            '<tool_call>{"name": "read_file", "arguments": {"path": "a.py"}}</tool_call>\n'
            'Some text in between\n'
            '<tool_call>{"name": "list_files", "arguments": {}}</tool_call>'
        )
        calls = _parse_tool_calls(text)
        assert len(calls) == 2
        assert calls[0]["name"] == "read_file"
        assert calls[1]["name"] == "list_files"

    def test_no_tool_calls(self):
        assert _parse_tool_calls("Just regular text, no tools here.") == []

    def test_invalid_json_skipped(self):
        text = '<tool_call>not valid json</tool_call>'
        assert _parse_tool_calls(text) == []

    def test_missing_name_skipped(self):
        text = '<tool_call>{"arguments": {"path": "x.py"}}</tool_call>'
        assert _parse_tool_calls(text) == []

    def test_whitespace_tolerance(self):
        text = '<tool_call>  \n  {"name": "read_file", "arguments": {"path": "f.py"}}  \n  </tool_call>'
        calls = _parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["name"] == "read_file"

    def test_tool_call_amid_prose(self):
        text = (
            "Let me create the file for you.\n\n"
            '<tool_call>\n{"name": "write_file", "arguments": {"path": "app.py", "content": "# hello"}}\n</tool_call>\n\n'
            "The file has been created."
        )
        calls = _parse_tool_calls(text)
        assert len(calls) == 1
        assert calls[0]["arguments"]["content"] == "# hello"


# ── _safe_path ────────────────────────────────────────────────────────────────


class TestSafePath:
    def test_normal_path(self, tmp_path):
        result = _safe_path(tmp_path, "subdir/file.txt")
        assert str(result).startswith(str(tmp_path.resolve()))

    def test_traversal_blocked(self, tmp_path):
        with pytest.raises(PermissionError, match="escapes workspace"):
            _safe_path(tmp_path, "../../etc/passwd")

    def test_absolute_path_blocked(self, tmp_path):
        with pytest.raises(PermissionError):
            _safe_path(tmp_path, "/etc/passwd")


# ── execute_tool ──────────────────────────────────────────────────────────────


class TestExecuteTool:
    def test_write_and_read_file(self, tmp_path):
        ws = str(tmp_path)
        result, ok = execute_tool(ws, "write_file", {"path": "test.txt", "content": "hello world"})
        assert ok
        assert "Wrote" in result

        content, ok = execute_tool(ws, "read_file", {"path": "test.txt"})
        assert ok
        assert content == "hello world"

    def test_read_nonexistent(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "read_file", {"path": "nope.txt"})
        assert ok
        assert "not found" in result

    def test_create_folder(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "create_folder", {"path": "my/nested/dir"})
        assert ok
        assert (tmp_path / "my" / "nested" / "dir").is_dir()

    def test_list_files(self, tmp_path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result, ok = execute_tool(str(tmp_path), "list_files", {"path": "."})
        assert ok
        assert "a.txt" in result
        assert "b.txt" in result

    def test_edit_file(self, tmp_path):
        (tmp_path / "code.py").write_text("x = 1\ny = 2\n")
        result, ok = execute_tool(str(tmp_path), "edit_file", {
            "path": "code.py",
            "old_string": "x = 1",
            "new_string": "x = 42",
        })
        assert ok
        assert (tmp_path / "code.py").read_text() == "x = 42\ny = 2\n"

    def test_edit_file_not_found(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "edit_file", {
            "path": "nope.py",
            "old_string": "a",
            "new_string": "b",
        })
        assert ok
        assert "not found" in result

    def test_run_command(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "run_command", {"command": "echo hello"})
        assert ok
        assert "hello" in result

    def test_run_command_blocks_shell_chaining(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "run_command", {"command": "echo hi && pwd"})
        assert not ok
        assert "blocked" in result.lower() or "single command" in result.lower()

    def test_run_command_blocks_destructive_prefixes(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "run_command", {"command": "rm -rf ."})
        assert not ok
        assert "blocked" in result.lower()

    def test_tool_execution_is_audited(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "write_file", {"path": "audit.txt", "content": "tracked"})
        assert ok
        assert "Wrote" in result

        audit_path = tmp_path / ".clone_dna" / "tool_audit.jsonl"
        assert audit_path.exists()
        lines = audit_path.read_text().splitlines()
        assert lines
        last = json.loads(lines[-1])
        assert last["tool"] == "write_file"
        assert last["arguments"]["path"] == "audit.txt"
        assert last["success"] is True

    def test_unknown_tool(self, tmp_path):
        result, ok = execute_tool(str(tmp_path), "nonexistent_tool", {})
        assert not ok
        assert "Unknown tool" in result
