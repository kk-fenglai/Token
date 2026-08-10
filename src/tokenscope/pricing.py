"""pricing.json load/validate/save and virtual-cost math.

Costs are always computed at query time from the current pricing file, so
editing prices retroactively corrects all history (PRD R3).
"""
from __future__ import annotations

import json
import os
import tempfile

from .config import ensure_pricing_file, pricing_path

FAMILIES = ("fable", "opus", "sonnet", "haiku", "other")
RATE_KEYS = ("input", "output", "cache_write", "cache_read")


def load_pricing() -> dict:
    p = ensure_pricing_file()
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        doc = {}
    return doc if isinstance(doc, dict) else {}


def validate_pricing(doc: dict) -> list[str]:
    errors = []
    fams = doc.get("families")
    if not isinstance(fams, dict):
        return ["families must be an object"]
    for fam in FAMILIES:
        rates = fams.get(fam)
        if not isinstance(rates, dict):
            errors.append(f"families.{fam} missing")
            continue
        for k in RATE_KEYS:
            v = rates.get(k)
            if not isinstance(v, (int, float)) or v < 0:
                errors.append(f"families.{fam}.{k} must be a number >= 0")
    return errors


def save_pricing(doc: dict) -> None:
    p = pricing_path()
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def rates_for(family: str, pricing: dict | None = None) -> dict:
    fams = (pricing or load_pricing()).get("families", {})
    rates = fams.get(family) or fams.get("other") or {}
    return {k: float(rates.get(k, 0.0)) for k in RATE_KEYS}


def cost_of(family: str, input_t: int, output_t: int, cache_w: int, cache_r: int,
            pricing: dict | None = None) -> float:
    r = rates_for(family, pricing)
    return (input_t * r["input"] + output_t * r["output"]
            + cache_w * r["cache_write"] + cache_r * r["cache_read"]) / 1_000_000
