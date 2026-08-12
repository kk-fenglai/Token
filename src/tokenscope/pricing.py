"""pricing.json load/validate/save and virtual-cost math.

Costs are always computed at query time from the current pricing file, so
editing prices retroactively corrects all history (PRD R3).

Rates come from `families` (fable/opus/sonnet/haiku/other). An optional
`models` map overrides individual model ids — `claude-opus-4-8` and
`claude-opus-5` are both the "opus" family but need not share a price. Overrides
are partial: any rate key left out falls back to the family rate.
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
    models = doc.get("models")
    if models is not None:
        if not isinstance(models, dict):
            errors.append("models must be an object")
        else:
            for model, rates in models.items():
                if not isinstance(rates, dict):
                    errors.append(f"models.{model} must be an object")
                    continue
                for k, v in rates.items():
                    if k not in RATE_KEYS:
                        errors.append(f"models.{model}.{k} is not a rate key")
                    elif not isinstance(v, (int, float)) or v < 0:
                        errors.append(f"models.{model}.{k} must be a number >= 0")
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


def rates_for_model(model: str, family: str, pricing: dict | None = None) -> dict:
    """Family rates with any per-model override applied (partial overrides ok)."""
    doc = pricing if pricing is not None else load_pricing()
    base = rates_for(family, doc)
    override = (doc.get("models") or {}).get(model) if isinstance(doc.get("models"), dict) else None
    if isinstance(override, dict):
        return {k: float(override[k]) if isinstance(override.get(k), (int, float)) else base[k]
                for k in RATE_KEYS}
    return base


def has_model_override(model: str, pricing: dict | None = None) -> bool:
    doc = pricing if pricing is not None else load_pricing()
    models = doc.get("models")
    return isinstance(models, dict) and isinstance(models.get(model), dict)


def _apply(r: dict, input_t: int, output_t: int, cache_w: int, cache_r: int) -> float:
    return (input_t * r["input"] + output_t * r["output"]
            + cache_w * r["cache_write"] + cache_r * r["cache_read"]) / 1_000_000


def cost_of(family: str, input_t: int, output_t: int, cache_w: int, cache_r: int,
            pricing: dict | None = None) -> float:
    return _apply(rates_for(family, pricing), input_t, output_t, cache_w, cache_r)


def cost_of_model(model: str, family: str, input_t: int, output_t: int,
                  cache_w: int, cache_r: int, pricing: dict | None = None) -> float:
    """Cost at the model's own rate — the one all aggregation should use."""
    return _apply(rates_for_model(model, family, pricing),
                  input_t, output_t, cache_w, cache_r)
