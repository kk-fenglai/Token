"""Subscription plan detection and "API price vs. monthly fee" savings math.

Claude Code writes the signed-in account's plan into `~/.claude.json` under
`oauthAccount`: `organizationType` ("claude_max" / "claude_pro") plus
`organizationRateLimitTier` ("default_claude_max_5x" / "..._20x"). Only those
non-secret profile fields are read — credentials live in a separate file
(`~/.claude/.credentials.json`) that this module never opens.

Detection is best-effort by nature (Team seats, mid-month plan changes, annual
billing), so `config.json -> subscription` can pin the plan or the monthly fee
and always wins. This module holds no DB knowledge: callers pass in the costs,
which keeps it importable from `queries` without a cycle.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import load_config, save_config

# List price in USD/month. `api` means pay-as-you-go: the virtual cost IS the
# bill, so there is nothing to compare against and no savings to report.
PLANS: dict[str, dict] = {
    "pro":   {"label": "Pro",            "monthly_usd": 20.0},
    "max5":  {"label": "Max 5x",         "monthly_usd": 100.0},
    "max20": {"label": "Max 20x",        "monthly_usd": 200.0},
    "team":  {"label": "Team (per seat)", "monthly_usd": 30.0},
    "api":   {"label": "API 按量付费",    "monthly_usd": 0.0},
}

UNKNOWN = {"label": "未识别", "monthly_usd": 0.0}


def _oauth_account() -> dict:
    """The `oauthAccount` profile block from ~/.claude.json, or {}."""
    path = Path.home() / ".claude.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    acct = doc.get("oauthAccount") if isinstance(doc, dict) else None
    return acct if isinstance(acct, dict) else {}


def detect() -> dict:
    """Best-effort plan detection. Always returns a dict; `plan` may be None."""
    acct = _oauth_account()
    if not acct:
        return {"plan": None, "reason": "未找到 ~/.claude.json 的 oauthAccount", "evidence": {}}

    # A user-level tier overrides the org default (Team/Enterprise seats).
    tier = str(acct.get("userRateLimitTier") or acct.get("organizationRateLimitTier") or "").lower()
    org_type = str(acct.get("organizationType") or "").lower()
    billing = str(acct.get("billingType") or "").lower()
    seat = str(acct.get("seatTier") or "").lower()
    evidence = {
        "organizationType": acct.get("organizationType"),
        "organizationRateLimitTier": acct.get("organizationRateLimitTier"),
        "userRateLimitTier": acct.get("userRateLimitTier"),
        "seatTier": acct.get("seatTier"),
        "billingType": acct.get("billingType"),
        "subscriptionCreatedAt": acct.get("subscriptionCreatedAt"),
        "hasExtraUsageEnabled": acct.get("hasExtraUsageEnabled"),
    }
    blob = f"{tier} {seat} {org_type}"

    if "20x" in blob:
        plan, reason = "max20", f"rate limit tier = {tier}"
    elif "5x" in blob:
        plan, reason = "max5", f"rate limit tier = {tier}"
    elif "team" in blob or "enterprise" in blob:
        plan, reason = "team", f"seat/org tier = {seat or org_type}"
    elif "pro" in blob:
        plan, reason = "pro", f"org type = {org_type or tier}"
    elif "max" in org_type:
        # Max org with an unrecognised tier string — assume the cheaper rung
        # rather than overstating savings.
        plan, reason = "max5", f"org type = {org_type}(档位字符串未识别,按低档估)"
    elif billing and "subscription" not in billing:
        plan, reason = "api", f"billing type = {billing}"
    else:
        plan, reason = None, "账号字段中没有可识别的套餐标记"

    return {"plan": plan, "reason": reason, "evidence": evidence,
            "since": acct.get("subscriptionCreatedAt")}


def plan_info() -> dict:
    """Effective plan: manual config override if set, else detection."""
    cfg = load_config()
    sub = cfg.get("subscription") if isinstance(cfg.get("subscription"), dict) else {}
    detected = detect()
    mode = str(sub.get("mode") or "auto").lower()
    override_plan = sub.get("plan")
    override_fee = sub.get("monthly_usd")

    plan = override_plan if (mode == "manual" and override_plan) else detected["plan"]
    source = "manual" if (mode == "manual" and override_plan) else "detected"
    if not plan:
        plan, source = None, "unknown"

    spec = PLANS.get(plan or "", UNKNOWN)
    fee = float(override_fee) if isinstance(override_fee, (int, float)) and override_fee >= 0 else spec["monthly_usd"]

    return {
        "plan": plan,
        "label": spec["label"],
        "monthly_usd": fee,
        "source": source,
        "mode": mode,
        "detected_plan": detected["plan"],
        "detect_reason": detected.get("reason"),
        "evidence": detected.get("evidence", {}),
        "since": detected.get("since"),
        "fee_overridden": fee != spec["monthly_usd"],
        # Only a paid subscription has a fixed fee to beat.
        "comparable": bool(plan) and plan != "api" and fee > 0,
        "catalog": [{"id": k, **v} for k, v in PLANS.items()],
    }


def set_subscription(mode: str, plan: str | None = None,
                     monthly_usd: float | None = None) -> dict:
    """Persist the subscription override. mode='auto' clears the pin."""
    mode = (mode or "auto").lower()
    if mode not in ("auto", "manual"):
        raise ValueError("mode must be 'auto' or 'manual'")
    if mode == "manual" and plan not in PLANS:
        raise ValueError(f"plan must be one of {', '.join(PLANS)}")
    if monthly_usd is not None and (not isinstance(monthly_usd, (int, float)) or monthly_usd < 0):
        raise ValueError("monthly_usd must be a number >= 0")

    cfg = load_config()
    sub: dict = {"mode": mode}
    if mode == "manual":
        sub["plan"] = plan
        if monthly_usd is not None:
            sub["monthly_usd"] = float(monthly_usd)
    cfg["subscription"] = sub
    save_config(cfg)
    return plan_info()


def _days_in_month(d: datetime) -> int:
    nxt = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (nxt - timedelta(days=1)).day


def month_progress(now: datetime | None = None) -> dict:
    now = now or datetime.now().astimezone()
    total = _days_in_month(now)
    # Fractional so an early-morning check doesn't project off ~0 days.
    elapsed = (now.day - 1) + (now.hour * 3600 + now.minute * 60 + now.second) / 86400
    elapsed = max(elapsed, 1 / 24)
    return {"day": now.day, "days_in_month": total,
            "elapsed_days": round(elapsed, 3), "fraction": round(elapsed / total, 4)}


def savings(month_api_cost: float, info: dict | None = None,
            now: datetime | None = None) -> dict:
    """Month-to-date subscription savings, plus an end-of-month projection."""
    info = info or plan_info()
    fee = float(info["monthly_usd"])
    prog = month_progress(now)
    projected = month_api_cost / prog["fraction"] if prog["fraction"] > 0 else month_api_cost

    saved = month_api_cost - fee
    return {
        "comparable": info["comparable"],
        "plan": info["plan"],
        "plan_label": info["label"],
        "source": info["source"],
        "monthly_fee": round(fee, 2),
        "api_cost_mtd": round(month_api_cost, 2),
        "saved": round(saved, 2),
        "multiple": round(month_api_cost / fee, 2) if fee > 0 else None,
        "breakeven_reached": month_api_cost >= fee > 0,
        # Fee still to be earned back, in dollars of API price.
        "remaining_to_breakeven": round(max(fee - month_api_cost, 0.0), 2),
        "projected_api_cost": round(projected, 2),
        "projected_saved": round(projected - fee, 2),
        "month_progress": prog,
    }


def _month_range(first: str, last: str) -> list[str]:
    y, m = int(first[:4]), int(first[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= last:
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def savings_timeline(monthly_costs: list[dict], info: dict | None = None,
                     now: datetime | None = None) -> dict:
    """Per-month savings since the subscription started, plus the running total.

    `monthly_costs` is [{"month": "YYYY-MM", "cost": float}, ...]. Months before
    `since` carry a zero fee — usage existed, but nothing was being paid for.

    Subscribed months absent from the data are still charged their fee: Claude
    Code prunes logs after ~30 days, so a gap means "records deleted", not "no
    usage". Counting the fee against $0 of recorded usage makes `total_saved` a
    conservative floor rather than an overstatement; `months_missing_data`
    tells the UI how much of the window is guesswork.
    """
    info = info or plan_info()
    fee = float(info["monthly_usd"])
    since_month = str(info["since"])[:7] if info.get("since") else None

    now = now or datetime.now().astimezone()
    this_month = now.strftime("%Y-%m")

    costs = {r["month"]: float(r["cost"] or 0.0) for r in monthly_costs}
    observed = sorted(costs)
    if not observed and not since_month:
        months: list[str] = []
    else:
        first = min([m for m in (since_month, *observed) if m])
        months = _month_range(first, max(this_month, *(observed or [this_month])))

    points, cumulative, paid_months, missing = [], 0.0, 0, 0
    billed_api_cost = 0.0
    for m in months:
        cost = costs.get(m, 0.0)
        subscribed = info["comparable"] and (since_month is None or m >= since_month)
        m_fee = fee if subscribed else 0.0
        no_data = m not in costs
        # Months before the subscription started are shown for context but
        # contribute nothing: no fee was paid, so nothing was saved either.
        saved = cost - m_fee if subscribed else 0.0
        if subscribed:
            paid_months += 1
            billed_api_cost += cost
            cumulative += saved
            if no_data:
                missing += 1
        points.append({
            "month": m, "api_cost": round(cost, 2), "fee": round(m_fee, 2),
            "saved": round(saved, 2), "subscribed": subscribed,
            "partial": m == this_month, "data_missing": no_data,
            "cumulative_saved": round(cumulative, 2),
        })

    return {
        "comparable": info["comparable"],
        "plan_label": info["label"],
        "monthly_fee": round(fee, 2),
        "since": since_month,
        "points": points,
        # Totals cover subscribed months only, so the identity holds:
        # total_saved == total_api_cost - total_fees.
        "total_api_cost": round(billed_api_cost, 2),
        "total_fees": round(sum(p["fee"] for p in points), 2),
        "total_saved": round(cumulative, 2),
        "paid_months": paid_months,
        "months_missing_data": missing,
    }
