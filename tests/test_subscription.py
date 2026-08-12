import json
from datetime import datetime, timezone

import pytest

from tokenscope import subscription

MAX5 = {"plan": "max5", "label": "Max 5x", "monthly_usd": 100.0, "comparable": True,
        "source": "detected", "since": "2026-04-16T16:27:57Z"}
API = {"plan": "api", "label": "API 按量付费", "monthly_usd": 0.0, "comparable": False,
       "source": "detected", "since": None}


def _account(tmp_path, monkeypatch, **fields):
    (tmp_path / ".claude.json").write_text(
        json.dumps({"oauthAccount": fields}), encoding="utf-8")
    monkeypatch.setattr(subscription.Path, "home", staticmethod(lambda: tmp_path))


# ---------- detection ----------

def test_detects_max_5x_from_the_rate_limit_tier(tmp_path, monkeypatch):
    _account(tmp_path, monkeypatch, organizationType="claude_max",
             organizationRateLimitTier="default_claude_max_5x",
             subscriptionCreatedAt="2026-04-16T16:27:57Z")
    got = subscription.detect()
    assert got["plan"] == "max5"
    assert got["since"] == "2026-04-16T16:27:57Z"


def test_detects_max_20x(tmp_path, monkeypatch):
    _account(tmp_path, monkeypatch, organizationType="claude_max",
             organizationRateLimitTier="default_claude_max_20x")
    assert subscription.detect()["plan"] == "max20"


def test_user_tier_overrides_the_org_default(tmp_path, monkeypatch):
    _account(tmp_path, monkeypatch, organizationType="claude_max",
             organizationRateLimitTier="default_claude_max_5x",
             userRateLimitTier="default_claude_max_20x")
    assert subscription.detect()["plan"] == "max20"


def test_max_org_with_unknown_tier_assumes_the_cheaper_rung(tmp_path, monkeypatch):
    # Overstating the fee would understate savings; the reverse would be a lie.
    _account(tmp_path, monkeypatch, organizationType="claude_max",
             organizationRateLimitTier="something_new")
    assert subscription.detect()["plan"] == "max5"


def test_api_billing_is_detected_and_not_comparable(tmp_path, monkeypatch):
    _account(tmp_path, monkeypatch, billingType="api_credits")
    assert subscription.detect()["plan"] == "api"


def test_missing_file_yields_no_plan(tmp_path, monkeypatch):
    monkeypatch.setattr(subscription.Path, "home", staticmethod(lambda: tmp_path))
    assert subscription.detect()["plan"] is None


def test_corrupt_file_does_not_raise(tmp_path, monkeypatch):
    (tmp_path / ".claude.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(subscription.Path, "home", staticmethod(lambda: tmp_path))
    assert subscription.detect()["plan"] is None


# ---------- savings ----------

def _now(day: int) -> datetime:
    return datetime(2026, 8, day, 12, 0, tzinfo=timezone.utc)


def test_savings_is_api_cost_minus_the_fee():
    s = subscription.savings(1000.0, MAX5, _now(31))
    assert s["saved"] == 900.0
    assert s["multiple"] == 10.0
    assert s["breakeven_reached"] is True
    assert s["remaining_to_breakeven"] == 0.0


def test_below_breakeven_reports_the_shortfall():
    s = subscription.savings(30.0, MAX5, _now(31))
    assert s["saved"] == -70.0
    assert s["breakeven_reached"] is False
    assert s["remaining_to_breakeven"] == 70.0


def test_projection_scales_month_to_date_to_the_full_month():
    # Midday on the 16th of a 31-day month ≈ half elapsed.
    s = subscription.savings(500.0, MAX5, _now(16))
    assert s["projected_api_cost"] == pytest.approx(1000.0, rel=0.05)


def test_pay_as_you_go_has_nothing_to_compare():
    assert subscription.savings(1000.0, API, _now(15))["comparable"] is False


# ---------- timeline ----------

def test_timeline_accumulates_and_skips_months_before_the_subscription():
    costs = [{"month": "2026-03", "cost": 50.0},   # pre-subscription: no fee
             {"month": "2026-04", "cost": 300.0},
             {"month": "2026-05", "cost": 200.0}]
    t = subscription.savings_timeline(costs, MAX5, datetime(2026, 5, 31, tzinfo=timezone.utc))
    by_month = {p["month"]: p for p in t["points"]}
    # Pre-subscription months are shown but contribute nothing to the total:
    # no fee was paid that month, so no money was saved by not paying API price.
    assert by_month["2026-03"]["fee"] == 0.0
    assert by_month["2026-03"]["subscribed"] is False
    assert by_month["2026-03"]["saved"] == 0.0
    assert by_month["2026-03"]["cumulative_saved"] == 0.0
    assert by_month["2026-04"]["saved"] == 200.0
    assert by_month["2026-05"]["cumulative_saved"] == 300.0
    assert t["paid_months"] == 2
    assert t["total_api_cost"] == 500.0  # 2026-03 excluded
    assert t["total_saved"] == t["total_api_cost"] - t["total_fees"]


def test_months_with_pruned_logs_still_pay_their_fee():
    # Claude Code deletes transcripts after ~30 days: a gap means "records gone",
    # not "no usage" — so total_saved must stay a floor, never an overstatement.
    costs = [{"month": "2026-04", "cost": 300.0}, {"month": "2026-07", "cost": 300.0}]
    t = subscription.savings_timeline(costs, MAX5, datetime(2026, 7, 31, tzinfo=timezone.utc))
    months = [p["month"] for p in t["points"]]
    assert months == ["2026-04", "2026-05", "2026-06", "2026-07"]
    gap = [p for p in t["points"] if p["month"] == "2026-05"][0]
    assert gap["data_missing"] is True and gap["fee"] == 100.0 and gap["saved"] == -100.0
    assert t["months_missing_data"] == 2
    assert t["total_saved"] == 200.0  # 200 + 200 - 100 - 100


def test_timeline_marks_the_current_month_partial():
    costs = [{"month": "2026-08", "cost": 10.0}]
    t = subscription.savings_timeline(costs, MAX5, _now(12))
    assert t["points"][-1]["partial"] is True


def test_timeline_on_api_billing_claims_no_savings():
    # The virtual cost IS the bill, so there is no fee to beat and nothing saved.
    t = subscription.savings_timeline([{"month": "2026-08", "cost": 500.0}], API, _now(12))
    assert t["comparable"] is False
    assert t["total_fees"] == 0.0
    assert t["total_saved"] == 0.0
    assert t["points"][-1]["api_cost"] == 500.0  # usage still visible
