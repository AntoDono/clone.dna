"""Sandboxed tool definitions and execution for DNA clone agent conversations."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_DNAS_ROOT = Path(os.getenv("DNAS_DIR", "dnas"))

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
    {
        "type": "function",
        "function": {
            "name": "search_registry",
            "description": (
                "Search the DNA talent registry for expert .dna blocks by skills or domain. "
                "Returns matching blocks with their expertise domains, eval scores, and paths."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "skills": {
                        "type": "string",
                        "description": "Comma-separated skill keywords (e.g. 'python,backend,distributed-systems')",
                    },
                    "domain": {
                        "type": "string",
                        "description": "Domain keyword to filter by (e.g. 'backend', 'ml', 'frontend')",
                    },
                },
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


def _exec_search_registry(_workspace: Path, args: dict) -> str:
    """Query the .dna registry for blocks matching skills/domain filters."""
    skills_raw = args.get("skills", "")
    domain_raw = args.get("domain", "")
    skill_terms = [s.strip().lower() for s in skills_raw.split(",") if s.strip()] if skills_raw else []
    domain_term = domain_raw.strip().lower() if domain_raw else None

    results: list[dict] = []
    if not _DNAS_ROOT.exists():
        return json.dumps({"total": 0, "blocks": [], "note": "No DNA blocks directory found."})

    for team_dir in sorted(_DNAS_ROOT.iterdir()):
        if not team_dir.is_dir():
            continue
        for handle_dir in sorted(team_dir.iterdir()):
            if not handle_dir.is_dir():
                continue
            if (handle_dir / "revoked.json").exists():
                continue
            manifest_path = handle_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            try:
                manifest = json.loads(manifest_path.read_text())
            except Exception:
                continue

            candidate = manifest.get("candidate", {})
            domains = [d.lower() for d in candidate.get("expertise_domains", [])]
            tags = [t.lower() for t in manifest.get("tags", [])]
            handle = handle_dir.name.lower()
            searchable = domains + tags + [handle]

            if skill_terms and not any(
                term in field for term in skill_terms for field in searchable
            ):
                continue
            if domain_term and not any(domain_term in field for field in searchable):
                continue

            results.append({
                "team_id": team_dir.name,
                "handle": handle_dir.name,
                "name": manifest.get("name"),
                "expertise_domains": candidate.get("expertise_domains", []),
                "tags": manifest.get("tags", []),
                "base_model": manifest.get("base_model"),
                "eval_summary": manifest.get("eval_summary", {}),
                "path": str(handle_dir),
            })

    return json.dumps({"total": len(results), "blocks": results}, indent=2)


_EXECUTORS = {
    "write_file": _exec_write_file,
    "read_file": _exec_read_file,
    "create_folder": _exec_create_folder,
    "list_files": _exec_list_files,
    "edit_file": _exec_edit_file,
    "run_command": _exec_run_command,
    "search_registry": _exec_search_registry,
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
