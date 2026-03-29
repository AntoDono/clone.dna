"""Sandboxed tool definitions and execution for DNA clone agent conversations."""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a file. Parent directories are created automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path within the workspace"},
                    "content": {"type": "string", "description": "File content to write"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path within the workspace"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_folder",
            "description": "Create a directory (and any parent directories).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path within the workspace"},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files and directories at a path. Defaults to workspace root.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path (default: workspace root)", "default": "."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": "Find and replace a string in a file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative file path within the workspace"},
                    "old_string": {"type": "string", "description": "Exact string to find"},
                    "new_string": {"type": "string", "description": "Replacement string"},
                },
                "required": ["path", "old_string", "new_string"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Run a shell command in the workspace directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                },
                "required": ["command"],
            },
        },
    },
]

COMMAND_TIMEOUT = 30


def _safe_path(workspace: Path, relative: str) -> Path:
    """Resolve a relative path and verify it stays within the workspace."""
    resolved = (workspace / relative).resolve()
    ws_resolved = workspace.resolve()
    if not str(resolved).startswith(str(ws_resolved)):
        raise PermissionError(f"Path escapes workspace: {relative}")
    return resolved


def _exec_write_file(workspace: Path, args: dict) -> str:
    target = _safe_path(workspace, args["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    content = args["content"]
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {args['path']}"


def _exec_read_file(workspace: Path, args: dict) -> str:
    target = _safe_path(workspace, args["path"])
    if not target.exists():
        return f"Error: file not found: {args['path']}"
    return target.read_text(encoding="utf-8", errors="replace")[:8000]


def _exec_create_folder(workspace: Path, args: dict) -> str:
    target = _safe_path(workspace, args["path"])
    target.mkdir(parents=True, exist_ok=True)
    return f"Created directory: {args['path']}"


def _exec_list_files(workspace: Path, args: dict) -> str:
    target = _safe_path(workspace, args.get("path", "."))
    if not target.exists():
        return f"Error: directory not found: {args.get('path', '.')}"
    if not target.is_dir():
        return f"Error: not a directory: {args.get('path', '.')}"
    entries = sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    lines = []
    for entry in entries[:50]:
        rel = entry.relative_to(workspace.resolve())
        suffix = "/" if entry.is_dir() else ""
        lines.append(f"{rel}{suffix}")
    if len(entries) > 50:
        lines.append(f"... and {len(entries) - 50} more")
    return "\n".join(lines) if lines else "(empty directory)"


def _exec_edit_file(workspace: Path, args: dict) -> str:
    target = _safe_path(workspace, args["path"])
    if not target.exists():
        return f"Error: file not found: {args['path']}"
    content = target.read_text(encoding="utf-8", errors="replace")
    old = args["old_string"]
    new = args["new_string"]
    if old not in content:
        return f"Error: old_string not found in {args['path']}"
    content = content.replace(old, new, 1)
    target.write_text(content, encoding="utf-8")
    return f"Edited {args['path']}"


def _exec_run_command(workspace: Path, args: dict) -> str:
    command = args["command"]
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace.resolve()),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
        )
        output = ""
        if result.stdout:
            output += result.stdout[:4000]
        if result.stderr:
            output += ("\n--- stderr ---\n" + result.stderr[:2000]) if output else result.stderr[:4000]
        if not output:
            output = "(no output)"
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {COMMAND_TIMEOUT}s"
    except Exception as e:
        return f"Error: {e}"


_EXECUTORS = {
    "write_file": _exec_write_file,
    "read_file": _exec_read_file,
    "create_folder": _exec_create_folder,
    "list_files": _exec_list_files,
    "edit_file": _exec_edit_file,
    "run_command": _exec_run_command,
}


def execute_tool(workspace_dir: str, tool_name: str, arguments: dict) -> tuple[str, bool]:
    """
    Execute a tool in the sandboxed workspace.
    Returns (output_string, success_bool).
    """
    workspace = Path(workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)

    executor = _EXECUTORS.get(tool_name)
    if not executor:
        return f"Unknown tool: {tool_name}", False

    try:
        result = executor(workspace, arguments)
        logger.info("Tool %s executed in %s", tool_name, workspace_dir)
        return result, True
    except PermissionError as e:
        return str(e), False
    except Exception as e:
        logger.warning("Tool %s failed: %s", tool_name, e)
        return f"Error: {e}", False
