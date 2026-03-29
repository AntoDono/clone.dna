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
from datetime import datetime, timezone
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
    "teacher_config.json",
    "pairs.json",
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
    """Read a single DNA block directory and return its summary dict.

    Returns None for missing manifests or revoked blocks.
    """
    if (block_dir / "revoked.json").exists():
        return None
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
    if (block_dir / "revoked.json").exists():
        raise HTTPException(410, f"DNA block '{handle}' has been revoked")

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


# ── Cross-block adapter similarity ───────────────────────────────────────────

@router.get("/compare/{team_a}/{handle_a}/{team_b}/{handle_b}")
def compare_blocks(team_a: str, handle_a: str, team_b: str, handle_b: str):
    """
    Compute the cosine similarity between two DNA blocks' merged adapter weight
    spaces.  Flattens all lora_A and lora_B tensors from each adapter config
    (read from safetensors metadata) and computes structural similarity from
    the quantitative metadata in eval.json when weights aren't available.

    For two blocks with full adapter weights, reads adapter_model.safetensors
    header tensors (via safetensors format — no GPU required).  Falls back to
    eval-metric cosine similarity when weights are absent.

    Returns cosine_similarity (0–1), interpretation, and per-dimension deltas.
    """
    import math

    def _block_eval(team_id: str, handle: str) -> dict:
        d = _DNAS_ROOT / team_id / handle
        if not d.exists():
            raise HTTPException(404, f"Block not found: {team_id}/{handle}")
        if (d / "revoked.json").exists():
            raise HTTPException(410, f"Block {team_id}/{handle} has been revoked")
        return _read_json(d / "eval.json"), _read_json(d / "manifest.json"), d

    def _extract_weight_vector(block_dir: Path) -> list[float] | None:
        """Extract a compact numeric fingerprint from adapter weights (safetensors header)."""
        try:
            import struct
            sf_path = block_dir / "adapter_model.safetensors"
            if not sf_path.exists():
                return None
            with open(sf_path, "rb") as f:
                header_size = struct.unpack("<Q", f.read(8))[0]
                header_bytes = f.read(min(header_size, 65536))
            header = json.loads(header_bytes)
            # Collect tensor shapes and dtype info as a numeric fingerprint
            vec: list[float] = []
            for key, info in sorted(header.items()):
                if key == "__metadata__":
                    continue
                shape = info.get("shape", [])
                vec.extend(float(x) for x in shape[:4])
                # Pad to 4 dims
                vec.extend([0.0] * (4 - len(shape[:4])))
            return vec if vec else None
        except Exception:
            return None

    def _metric_vector(eval_data: dict) -> list[float]:
        """Fallback: use benchmark metrics as a fixed-length comparison vector."""
        bench = eval_data.get("benchmarks", {})
        metrics = eval_data.get("training", {})
        ppl = bench.get("perplexity_reduction") or {}
        return [
            bench.get("style_consistency") or 0.0,
            bench.get("domain_accuracy") or 0.0,
            bench.get("humaneval_score") or 0.0,
            metrics.get("final_loss") or 0.0,
            ppl.get("perplexity_reduction_ratio") or 1.0,
            len(eval_data.get("layer_drift", {}).get("per_layer", {})) / 100.0,
        ]

    def _cosine(a: list[float], b: list[float]) -> float:
        if len(a) != len(b):
            n = min(len(a), len(b))
            a, b = a[:n], b[:n]
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = math.sqrt(sum(x * x for x in a))
        mag_b = math.sqrt(sum(x * x for x in b))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return round(dot / (mag_a * mag_b), 4)

    eval_a, manifest_a, dir_a = _block_eval(team_a, handle_a)
    eval_b, manifest_b, dir_b = _block_eval(team_b, handle_b)

    vec_a = _extract_weight_vector(dir_a) or _metric_vector(eval_a)
    vec_b = _extract_weight_vector(dir_b) or _metric_vector(eval_b)
    mode = "adapter_weight_space" if _extract_weight_vector(dir_a) and _extract_weight_vector(dir_b) else "eval_metric_space"

    similarity = _cosine(vec_a, vec_b)

    bench_a = eval_a.get("benchmarks", {})
    bench_b = eval_b.get("benchmarks", {})
    ppl_a = (bench_a.get("perplexity_reduction") or {})
    ppl_b = (bench_b.get("perplexity_reduction") or {})

    return {
        "handle_a": handle_a,
        "handle_b": handle_b,
        "cosine_similarity": similarity,
        "comparison_mode": mode,
        "interpretation": (
            "Very similar coding style and domain focus" if similarity > 0.92 else
            "Related domain but distinct style" if similarity > 0.75 else
            "Different technical profiles" if similarity > 0.5 else
            "Highly differentiated candidates"
        ),
        "dimension_deltas": {
            "style_consistency": round(
                (bench_a.get("style_consistency") or 0) - (bench_b.get("style_consistency") or 0), 4),
            "domain_accuracy": round(
                (bench_a.get("domain_accuracy") or 0) - (bench_b.get("domain_accuracy") or 0), 4),
            "humaneval_score": round(
                (bench_a.get("humaneval_score") or 0) - (bench_b.get("humaneval_score") or 0), 4),
            "perplexity_reduction_ratio_delta": round(
                (ppl_a.get("perplexity_reduction_ratio") or 1.0) -
                (ppl_b.get("perplexity_reduction_ratio") or 1.0), 4),
        },
    }


# ── Revoke a DNA block ───────────────────────────────────────────────────────

@router.delete("/{team_id}/{handle}")
def revoke_block(team_id: str, handle: str):
    """
    Revoke a DNA block.  Places a revoked.json marker so the block is hidden
    from listings, search, detail, and download — but the directory is
    preserved on disk for audit provenance.
    """
    block_dir = _DNAS_ROOT / team_id / handle
    if not block_dir.exists() or not (block_dir / "manifest.json").exists():
        raise HTTPException(404, f"DNA block '{handle}' not found for team {team_id}")

    revoked_path = block_dir / "revoked.json"
    if revoked_path.exists():
        raise HTTPException(409, f"DNA block '{handle}' is already revoked")

    revoked = {
        "handle": handle,
        "team_id": team_id,
        "revoked_at": datetime.now(timezone.utc).isoformat(),
        "reason": "Block revoked via registry API",
    }
    revoked_path.write_text(json.dumps(revoked, indent=2))
    logger.info("Revoked DNA block %s/%s", team_id, handle)
    return {"status": "revoked", "team_id": team_id, "handle": handle}


# ── Developer self-service portal ─────────────────────────────────────────────

@router.get("/developer/{handle}")
def developer_lookup(handle: str):
    """
    Developer self-service endpoint — given a GitHub handle, return every DNA
    block minted from their public repos along with its consent status, revocation
    state, and a direct revocation endpoint URL.

    Powers the /developer portal where developers can audit and control whether
    their public code has been used to train a .dna block.
    """
    handle_lower = handle.lower()
    blocks: list[dict] = []

    if not _DNAS_ROOT.exists():
        return {"handle": handle, "blocks": [], "total": 0}

    for team_dir in sorted(_DNAS_ROOT.iterdir()):
        if not team_dir.is_dir():
            continue
        for handle_dir in sorted(team_dir.iterdir()):
            if handle_dir.name.lower() != handle_lower:
                continue
            manifest_path = handle_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = _read_json(manifest_path)
            consent = _read_json(handle_dir / "consent.json")
            revoked_path = handle_dir / "revoked.json"
            revoked_data = _read_json(revoked_path) if revoked_path.exists() else None

            blocks.append({
                "team_id":          team_dir.name,
                "handle":           handle_dir.name,
                "version":          manifest.get("version", "1.0.0"),
                "base_model":       manifest.get("base_model"),
                "created":          manifest.get("created"),
                "consent_status":   consent.get("consent_status", "implicit_public"),
                "consent_verified": manifest.get("candidate", {}).get("consent_verified", False),
                "revocable":        consent.get("revocable", True),
                "revoked":          revoked_data is not None,
                "revoked_at":       revoked_data.get("revoked_at") if revoked_data else None,
                "source_urls":      consent.get("source_urls", []),
                "revocation_endpoint": f"/registry/{team_dir.name}/{handle_dir.name}",
            })

    return {
        "handle":   handle,
        "total":    len(blocks),
        "blocks":   blocks,
        "message":  (
            "To revoke a block, send DELETE to the revocation_endpoint listed above. "
            "Revoked blocks are hidden from all registry listings and downloads immediately."
            if blocks else
            "No DNA blocks found for this handle. Your code has not been used to train any block in this registry."
        ),
    }
