"""
Model path resolution with optional local GPTQ quantization.

If QUANTIZATION_BITS is set, resolve_model_path() will:
  1. Check QUANTIZED_MODELS_DIR for an already-quantized copy of the model
  2. If missing, download the full-precision model, quantize it with GPTQ
     using wikitext-2 calibration data, and save it to disk
  3. Return the local path so from_pretrained() loads the quantized copy

This is a one-time operation per model — subsequent runs hit the cache.
If QUANTIZATION_BITS is not set, the original HF model name is returned as-is.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


def resolve_model_path(
    base_model: str,
    log: Callable[[str], None] | None = None,
) -> str:
    def _log(msg: str) -> None:
        logger.info(msg)
        if log:
            log(msg)

    quant_bits_str = os.getenv("QUANTIZATION_BITS", "").strip()
    if not quant_bits_str:
        return base_model

    bits = int(quant_bits_str)
    safe_name = base_model.replace("/", "__")
    quant_root = Path(os.getenv("QUANTIZED_MODELS_DIR", "quantized_models"))
    quant_dir = quant_root / f"{safe_name}-gptq-int{bits}"

    if (quant_dir / "config.json").exists():
        _log(f"Loading cached GPTQ-Int{bits} model from {quant_dir}")
        return str(quant_dir)

    _log(
        f"No cached quantization found — quantizing '{base_model}' to "
        f"GPTQ-Int{bits} (one-time operation, this will take a while)..."
    )

    try:
        from datasets import load_dataset
        from gptqmodel import GPTQModel, QuantizeConfig

        calibration_data = [
            t
            for t in load_dataset("wikitext", "wikitext-2-raw-v1", split="train")["text"]
            if len(t.strip()) > 50
        ][:512]

        quant_config = QuantizeConfig(bits=bits, group_size=128)
        _log(f"Loading full-precision model for quantization...")
        model = GPTQModel.load(base_model, quant_config)

        _log(f"Running GPTQ calibration ({len(calibration_data)} samples)...")
        model.quantize(calibration_data)

        quant_dir.mkdir(parents=True, exist_ok=True)
        model.save(str(quant_dir))
        _log(f"Saved GPTQ-Int{bits} model to {quant_dir}")
        return str(quant_dir)

    except Exception as e:
        logger.warning("Quantization failed (%s) — falling back to original model", e)
        return base_model
