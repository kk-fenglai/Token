"""`config["agent"]` with defaults filled in, plus validation for PUTs.

Model names are plain strings the user can edit — DeepSeek renames models
often enough that hard-coding them would age badly.
"""
from __future__ import annotations

import copy
import re

from ..config import load_config

DEFAULT_PRICING = {
    # USD per million tokens, DeepSeek peak rates (off-peak is half; see
    # `offpeak`). Estimates: shown as such everywhere in the UI.
    "deepseek-flash": {"input_miss": 0.30, "input_hit": 0.006, "output": 1.20},
    "deepseek-v4-pro": {"input_miss": 1.32, "input_hit": 0.044, "output": 3.96},
}

DEFAULTS: dict = {
    "base_url": "https://api.deepseek.com",
    "model": "deepseek-flash",
    "models": ["deepseek-flash", "deepseek-v4-pro"],
    "thinking": True,
    "confirm_side_effects": False,
    "max_iterations": 12,
    "max_context_tokens": 128_000,
    "max_external_calls": 3,
    "pricing": DEFAULT_PRICING,
    # UTC weekday hours when DeepSeek bills peak rates; outside them, half.
    "offpeak": {"enabled": True, "peak_utc": [[1, 4], [6, 10]], "weekdays_only": True},
    "patrol": {
        "enabled": False,
        "schedule": "daily",   # daily | weekly
        "time": "09:00",       # local HH:MM
        "weekday": 1,          # 1 = Monday … 7 = Sunday (weekly only)
        "use_llm": True,
        "notify": True,
        "thinking": False,
    },
}

_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MODEL_RE = re.compile(r"^[A-Za-z0-9._:/-]{1,80}$")


def agent_cfg(cfg: dict | None = None) -> dict:
    """Deep-ish merge: top level and the `patrol` / `offpeak` blocks, so a
    partial user block never drops sub-keys."""
    cfg = cfg if cfg is not None else load_config()
    raw = cfg.get("agent") if isinstance(cfg.get("agent"), dict) else {}
    out = copy.deepcopy(DEFAULTS)
    for k, v in raw.items():
        if k in ("patrol", "offpeak") and isinstance(v, dict):
            out[k] = {**out[k], **v}
        elif k == "pricing" and isinstance(v, dict):
            out[k] = {**out[k], **{m: p for m, p in v.items() if isinstance(p, dict)}}
        elif k in DEFAULTS:
            out[k] = v
    if out["model"] not in out["models"]:
        out["models"] = [out["model"], *out["models"]]
    return out


def clean_settings(body: dict) -> tuple[dict, list[str]]:
    """Validate a partial update. Returns (fields to merge, errors)."""
    out: dict = {}
    errors: list[str] = []

    def s(key: str, pattern=None, maxlen=200):
        if key not in body:
            return
        v = body[key]
        if not isinstance(v, str) or not v.strip() or len(v) > maxlen or (pattern and not pattern.match(v.strip())):
            errors.append(f"{key} is invalid")
        else:
            out[key] = v.strip()

    s("base_url", re.compile(r"^https?://[^\s]+$"))
    s("model", _MODEL_RE)
    if "models" in body:
        v = body["models"]
        if not (isinstance(v, list) and 0 < len(v) <= 10 and all(isinstance(m, str) and _MODEL_RE.match(m) for m in v)):
            errors.append("models must be a list of 1-10 model ids")
        else:
            out["models"] = list(dict.fromkeys(m.strip() for m in v))
    for key in ("thinking", "confirm_side_effects"):
        if key in body:
            if not isinstance(body[key], bool):
                errors.append(f"{key} must be a boolean")
            else:
                out[key] = body[key]
    for key, lo, hi in (("max_iterations", 1, 40), ("max_context_tokens", 16_000, 1_000_000),
                        ("max_external_calls", 0, 10)):
        if key in body:
            v = body[key]
            if not (isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi):
                errors.append(f"{key} must be an integer in [{lo}, {hi}]")
            else:
                out[key] = v
    if "pricing" in body:
        v = body["pricing"]
        ok = isinstance(v, dict) and all(
            isinstance(m, str) and isinstance(p, dict)
            and all(isinstance(p.get(r), (int, float)) and not isinstance(p.get(r), bool) and p.get(r) >= 0
                    for r in ("input_miss", "input_hit", "output"))
            for m, p in v.items())
        if not ok:
            errors.append("pricing must map model -> {input_miss, input_hit, output} (USD / 1M, >= 0)")
        else:
            out["pricing"] = {m: {r: float(p[r]) for r in ("input_miss", "input_hit", "output")} for m, p in v.items()}
    if "patrol" in body:
        p = body["patrol"]
        if not isinstance(p, dict):
            errors.append("patrol must be an object")
        else:
            pc: dict = {}
            for key in ("enabled", "use_llm", "notify", "thinking"):
                if key in p:
                    if isinstance(p[key], bool):
                        pc[key] = p[key]
                    else:
                        errors.append(f"patrol.{key} must be a boolean")
            if "schedule" in p:
                if p["schedule"] in ("daily", "weekly"):
                    pc["schedule"] = p["schedule"]
                else:
                    errors.append("patrol.schedule must be daily or weekly")
            if "time" in p:
                if isinstance(p["time"], str) and _TIME_RE.match(p["time"]):
                    pc["time"] = p["time"]
                else:
                    errors.append("patrol.time must be HH:MM")
            if "weekday" in p:
                if isinstance(p["weekday"], int) and not isinstance(p["weekday"], bool) and 1 <= p["weekday"] <= 7:
                    pc["weekday"] = p["weekday"]
                else:
                    errors.append("patrol.weekday must be 1-7")
            unknown = set(p) - {"enabled", "use_llm", "notify", "thinking", "schedule", "time", "weekday"}
            if unknown:
                errors.append(f"unknown patrol keys: {', '.join(sorted(unknown))}")
            out["patrol"] = pc
    unknown = set(body) - {"base_url", "model", "models", "thinking", "confirm_side_effects", "max_iterations",
                           "max_context_tokens", "max_external_calls", "pricing", "patrol"}
    if unknown:
        errors.append(f"unknown keys: {', '.join(sorted(unknown))}")
    return out, errors


def merge_settings(current_raw: dict, fields: dict) -> dict:
    """Apply validated `fields` onto the raw `config["agent"]` block."""
    merged = dict(current_raw)
    for k, v in fields.items():
        if k == "patrol":
            merged["patrol"] = {**(merged.get("patrol") or {}), **v}
        else:
            merged[k] = v
    return merged
