"""Sessions / tools / heatmap / alerts / weekly report on a throwaway DB."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from tokenscope import db, insights, queries
from tokenscope.parser import UPSERT_SQL, parse_file, tool_names


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(insights.Path, "home", staticmethod(lambda: tmp_path))
    db.reset_conn()
    yield db.get_conn()
    db.reset_conn()


def _line(msg_id, ts, *, session="s1", cwd="C:\\Users\\alex\\Desktop\\MyApp", tools=(),
          sidechain=False, agent=None, output=100, cache_read=5000, cache_write=100, model="claude-opus-5"):
    content = [{"type": "tool_use", "name": n, "input": {}} for n in tools] or [{"type": "text", "text": "hi"}]
    obj = {
        "type": "assistant", "requestId": f"req_{msg_id}", "timestamp": ts, "cwd": cwd,
        "sessionId": session, "isSidechain": sidechain,
        "message": {"id": msg_id, "model": model, "content": content,
                    "usage": {"input_tokens": 10, "output_tokens": output,
                              "cache_creation_input_tokens": cache_write,
                              "cache_read_input_tokens": cache_read}},
    }
    if agent:
        obj["attributionAgent"] = agent
    return json.dumps(obj)


def _load(conn, path):
    res = parse_file(path)
    conn.executemany(UPSERT_SQL, res.events)
    conn.commit()
    return res


def test_parser_extracts_tools_and_sidechain(tmp_path, fresh_db):
    f = tmp_path / "a.jsonl"
    f.write_text("\n".join([
        _line("m1", "2026-09-01T02:00:00Z", tools=("Read", "Bash")),
        _line("m2", "2026-09-01T02:01:00Z", sidechain=True, agent="Explore"),
    ]), encoding="utf-8")
    res = _load(fresh_db, f)
    by_id = {e[0]: e for e in res.events}
    assert json.loads(by_id["m1"][13]) == ["Read", "Bash"] and by_id["m1"][14] == 2
    assert by_id["m1"][15] == 0
    assert by_id["m2"][15] == 1 and by_id["m2"][16] == "Explore"
    assert tool_names({"content": "plain string"}) == []


def test_subagent_dir_marks_sidechain_even_without_flag(tmp_path, fresh_db):
    sub = tmp_path / "sess" / "subagents"
    sub.mkdir(parents=True)
    f = sub / "agent-1.jsonl"
    f.write_text(_line("m9", "2026-09-01T02:00:00Z"), encoding="utf-8")
    res = _load(fresh_db, f)
    assert res.events[0][15] == 1


@pytest.fixture()
def seeded(tmp_path, fresh_db):
    """Two sessions today (one with a subagent), one session 3 days ago."""
    now = datetime.now(timezone.utc)
    t0 = now - timedelta(hours=2)
    old = now - timedelta(days=3)
    iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        _line("a1", iso(t0), tools=("Read",), cache_read=1000),
        _line("a2", iso(t0 + timedelta(minutes=1)), tools=("Bash", "Edit"), cache_read=50_000),
        _line("a3", iso(t0 + timedelta(minutes=2)), cache_read=200_000, output=2000),
        _line("a4", iso(t0 + timedelta(minutes=3)), session="s1", sidechain=True, agent="Explore",
              tools=("Grep",), cache_read=20_000),
        _line("b1", iso(t0 + timedelta(minutes=10)), session="s2", cwd="C:\\Users\\alex\\Desktop\\Other",
              cache_read=3000),
        _line("c1", iso(old), session="s3", cache_read=3000, output=50),
    ]
    f = tmp_path / "x.jsonl"
    f.write_text("\n".join(lines), encoding="utf-8")
    _load(fresh_db, f)
    return fresh_db


def test_sessions_roll_up_subagents_and_peak_context(seeded):
    got = insights.sessions("today", sort="cost")
    assert got["total"] == 2
    top = got["items"][0]
    assert top["session_id"] == "s1"
    assert top["messages"] == 4
    assert top["subagent_events"] == 1 and top["subagent_cost"] > 0
    assert top["ctx_max"] == 10 + 100 + 200_000
    assert top["tool_calls"] == 4
    assert top["name"] == "MyApp"
    assert got["items"][1]["session_id"] == "s2"


def test_sessions_all_includes_older_and_search_filters(seeded):
    assert insights.sessions("all")["total"] == 3
    assert insights.sessions("all", q="Other")["total"] == 1
    assert insights.sessions("all", q="s3")["items"][0]["session_id"] == "s3"


def test_session_detail_timeline(seeded):
    d = insights.session_detail("s1")
    assert d is not None
    assert [m["i"] for m in d["messages"]] == [0, 1, 2, 3]
    assert d["messages"][1]["tools"] == ["Bash", "Edit"]
    assert d["messages"][3]["sidechain"] and d["messages"][3]["agent"] == "Explore"
    assert d["peak_context"]["i"] == 2
    assert d["messages"][-1]["cumulative_cost"] == pytest.approx(d["session"]["cost"], abs=1e-3)
    assert insights.session_detail("nope") is None


def test_tools_breakdown_splits_cost_evenly(seeded):
    tb = insights.tools_breakdown("today")
    names = {t["name"]: t for t in tb["tools"]}
    assert set(names) == {"Read", "Bash", "Edit", "Grep"}
    assert names["Bash"]["cost"] == pytest.approx(names["Edit"]["cost"])
    assert names["Bash"]["calls"] == 1
    assert tb["text_only"]["messages"] == 2  # a3 and b1
    assert tb["subagents"]["events"] == 1
    assert tb["subagents"]["by_agent"][0]["agent"] == "Explore"
    assert tb["totals"]["events"] == 5
    assert sum(t["cost"] for t in tb["tools"]) + tb["text_only"]["cost"] == pytest.approx(tb["totals"]["cost"], abs=1e-3)


def test_heatmap_has_168_cells_and_a_peak(seeded):
    hm = insights.heatmap("7d")
    assert len(hm["cells"]) == 168
    assert hm["peak"] is not None
    assert hm["total_cost"] == pytest.approx(sum(hm["by_dow"]), abs=1e-3)
    assert sum(c["events"] for c in hm["cells"]) == 6


def test_efficiency_on_summary_and_projects(seeded):
    cards = queries.summary_cards()
    eff = cards["today"]["efficiency"]
    assert 0 < eff["cache_hit_rate"] < 1
    assert eff["cache_saved"] > 0
    assert eff["cost_per_1k_output"] > 0
    proj = queries.projects_list("all")["items"][0]
    assert "cache_hit_rate" in proj["efficiency"]


def test_alerts_flag_context_bloat_and_retention(seeded):
    got = insights.alerts()
    kinds = {a["kind"]: a for a in got["items"]}
    assert "context_bloat" in kinds
    assert kinds["context_bloat"]["params"]["ctx_max"] >= insights.CONTEXT_BLOAT_TOKENS
    # settings.json absent → default 30-day cleanup → retention hint
    assert "retention" in kinds
    levels = [a["level"] for a in got["items"]]
    assert levels == sorted(levels, key={"danger": 0, "warn": 1, "info": 2}.get)


def test_pricing_status_and_retention_info(fresh_db, tmp_path):
    ps = insights.pricing_status()
    assert ps["last_verified"] and isinstance(ps["stale"], bool)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"cleanupPeriodDays": 365}', encoding="utf-8")
    ri = insights.retention_info()
    assert ri["cleanup_days"] == 365 and ri["configured"]


def test_weekly_report_and_markdown(seeded):
    rep = insights.weekly_report(0)
    assert rep["week"]["is_current"]
    assert rep["totals"]["events"] >= 5
    assert len(rep["days"]) == 7
    assert rep["top_projects"][0]["name"] in ("MyApp", "Other")
    md_zh = insights.render_weekly_markdown(rep, "zh")
    md_en = insights.render_weekly_markdown(rep, "en")
    assert md_zh.startswith("# TokenScope 周报") and "| MyApp |" in md_zh
    assert md_en.startswith("# TokenScope weekly")
    empty = insights.weekly_report(40)
    assert "(no records this week)" in insights.render_weekly_markdown(empty, "en")
