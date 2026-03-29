"""
Talent Registry — browse, search, and download cloned .dna blocks.

Each DNA block lives at DNAS_DIR/{team_id}/{handle}/ and contains:
  manifest.json, eval.json, sources.json, consent.json, profile.md,
  adapter_config.json, adapter_model.safetensors (or bin), tokenizer files.
"""

from __future__ import annotations

import io
import json
import logging
import os
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/registry", tags=["registry"])

_DNAS_ROOT = Path(os.getenv("DNAS_DIR", "dnas"))

# Files included in a .dna download zip (adapter weight files are added dynamically)
_METADATA_FILES = [
    "manifest.json",
    "eval.json",
    "sources.json",
    "consent.json",
    "profile.md",
    "adapter_config.json",
]

# Adapter weight file patterns to include in downloads
_WEIGHT_PATTERNS = ["*.safetensors", "*.bin", "tokenizer*", "special_tokens_map.json"]


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _collect_block(team_id: str, handle: str, block_dir: Path) -> dict | None:
    """Read a single DNA block directory and return its summary dict."""
    manifest_path = block_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    manifest = _read_json(manifest_path)
    eval_data = _read_json(block_dir / "eval.json")
    return {
        "team_id": team_id,
        "handle": handle,
        "path": str(block_dir),
        "manifest": manifest,
        "eval": eval_data,
    }


def _all_blocks() -> list[dict]:
    """Walk DNAS_DIR and collect every valid DNA block."""
    blocks: list[dict] = []
    if not _DNAS_ROOT.exists():
        return blocks
    for team_dir in sorted(_DNAS_ROOT.iterdir()):
        if not team_dir.is_dir():
            continue
        for handle_dir in sorted(team_dir.iterdir()):
            if not handle_dir.is_dir():
                continue
            block = _collect_block(team_dir.name, handle_dir.name, handle_dir)
            if block:
                blocks.append(block)
    return blocks


# ── List all DNA blocks ───────────────────────────────────────────────────────

@router.get("")
def list_registry():
    """
    List all cloned DNA blocks across all teams.
    Returns manifest + eval summary for each block.
    """
    blocks = _all_blocks()
    return {
        "total": len(blocks),
        "blocks": [
            {
                "team_id": b["team_id"],
                "handle": b["handle"],
                "name": b["manifest"].get("name"),
                "version": b["manifest"].get("version"),
                "expertise_domains": b["manifest"].get("candidate", {}).get("expertise_domains", []),
                "tags": b["manifest"].get("tags", []),
                "base_model": b["manifest"].get("base_model"),
                "vllm_compatible": b["manifest"].get("vllm_compatible", False),
                "created": b["manifest"].get("created"),
                "eval_summary": b["manifest"].get("eval_summary", {}),
                "training_pairs": b["manifest"].get("training_pairs"),
            }
            for b in blocks
        ],
    }


# ── Search by skills / domain ─────────────────────────────────────────────────

@router.get("/search")
def search_registry(
    skills: str | None = Query(None, description="Comma-separated skill keywords to match"),
    domain: str | None = Query(None, description="Domain keyword to match in expertise_domains"),
    q: str | None = Query(None, description="Free-text search across handle, name, tags"),
):
    """
    Search DNA blocks by skills, domain, or free text.
    Returns blocks where any filter term matches expertise_domains or tags.
    """
    blocks = _all_blocks()

    skill_terms = [s.strip().lower() for s in skills.split(",")] if skills else []
    domain_term = domain.strip().lower() if domain else None
    q_term = q.strip().lower() if q else None

    def _matches(block: dict) -> bool:
        manifest = block["manifest"]
        candidate = manifest.get("candidate", {})
        domains = [d.lower() for d in candidate.get("expertise_domains", [])]
        tags = [t.lower() for t in manifest.get("tags", [])]
        handle = block["handle"].lower()
        name = (manifest.get("candidate", {}).get("name") or "").lower()
        searchable = domains + tags + [handle, name]

        if skill_terms and not any(
            term in field for term in skill_terms for field in searchable
        ):
            return False
        if domain_term and not any(domain_term in field for field in searchable):
            return False
        if q_term and not any(q_term in field for field in searchable):
            return False
        return True

    results = [b for b in blocks if _matches(b)]
    return {
        "query": {"skills": skills, "domain": domain, "q": q},
        "total": len(results),
        "blocks": [
            {
                "team_id": b["team_id"],
                "handle": b["handle"],
                "name": b["manifest"].get("name"),
                "expertise_domains": b["manifest"].get("candidate", {}).get("expertise_domains", []),
                "tags": b["manifest"].get("tags", []),
                "base_model": b["manifest"].get("base_model"),
                "created": b["manifest"].get("created"),
                "eval_summary": b["manifest"].get("eval_summary", {}),
            }
            for b in results
        ],
    }


# ── Single block detail ───────────────────────────────────────────────────────

@router.get("/{team_id}/{handle}")
def get_block(team_id: str, handle: str):
    """
    Return full detail for a single DNA block: manifest, eval, sources, consent.
    """
    block_dir = _DNAS_ROOT / team_id / handle
    if not block_dir.exists():
        raise HTTPException(404, f"DNA block '{handle}' not found for team {team_id}")

    block = _collect_block(team_id, handle, block_dir)
    if not block:
        raise HTTPException(404, "Block found on disk but manifest.json is missing or invalid")

    sources = _read_json(block_dir / "sources.json")
    consent = _read_json(block_dir / "consent.json")
    profile_path = block_dir / "profile.md"
    profile_md = profile_path.read_text() if profile_path.exists() else None

    return {
        "team_id": team_id,
        "handle": handle,
        "manifest": block["manifest"],
        "eval": block["eval"],
        "sources": sources,
        "consent": consent,
        "profile_md": profile_md,
    }


# ── Download a DNA block as a zip ─────────────────────────────────────────────

@router.get("/{team_id}/{handle}/download")
def download_block(team_id: str, handle: str):
    """
    Download a DNA block as a zip archive containing metadata + adapter weights.
    The zip is streamed from memory — adapter weights can be large (50–500 MB).
    """
    block_dir = _DNAS_ROOT / team_id / handle
    if not block_dir.exists() or not (block_dir / "manifest.json").exists():
        raise HTTPException(404, f"DNA block '{handle}' not found for team {team_id}")

    def _iter_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # Metadata files
            for fname in _METADATA_FILES:
                fpath = block_dir / fname
                if fpath.exists():
                    zf.write(fpath, arcname=fname)

            # Adapter weight files and tokenizer
            for pattern in _WEIGHT_PATTERNS:
                for fpath in block_dir.glob(pattern):
                    if fpath.is_file():
                        zf.write(fpath, arcname=fpath.name)

        buf.seek(0)
        yield buf.read()

    filename = f"{handle}-dna.zip"
    return StreamingResponse(
        _iter_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
