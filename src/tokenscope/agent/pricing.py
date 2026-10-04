"""Estimated USD cost of one DeepSeek request from its usage block."""
from __future__ import annotations

from datetime import datetime, timezone


def is_offpeak(ts: datetime, offpeak: dict) -> bool:
    if not offpeak.get("enabled"):
        return False
    utc = ts.astimezone(timezone.utc)
    if offpeak.get("weekdays_only", True) and utc.weekday() >= 5:
        return True  # weekends are billed off-peak
    hour = utc.hour + utc.minute / 60
    return not any(lo <= hour < hi for lo, hi in offpeak.get("peak_utc") or [])


def cost_usd(model: str, hit: int, miss: int, out: int, cfg: dict, ts: datetime | None = None) -> float:
    rates = (cfg.get("pricing") or {}).get(model)
    if not rates:
        # Unknown model: price it like the most expensive known one rather
        # than silently showing $0.
        known = list((cfg.get("pricing") or {}).values())
        if not known:
            return 0.0
        rates = max(known, key=lambda r: r.get("output", 0))
    cost = (hit * rates["input_hit"] + miss * rates["input_miss"] + out * rates["output"]) / 1_000_000
    if is_offpeak(ts or datetime.now(timezone.utc), cfg.get("offpeak") or {}):
        cost /= 2
    return round(cost, 6)
