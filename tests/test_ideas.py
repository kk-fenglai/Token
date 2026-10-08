"""F30 inspiration board: TrustMRR normalization, the throttled sync run
against a fake server, clusters, card rules and scoring, and the routes."""
import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from tokenscope import db, ideas, ideas_sync

LOCAL = {"host": "127.0.0.1:8787"}


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv(ideas_sync.ENV_VAR, raising=False)
    db.reset_conn()
    ideas._ready = None
    yield db.get_conn()
    db.reset_conn()
    ideas._ready = None


def api_item(slug, mrr_cents, customers=100, growth=10, **kw):
    return {"name": slug.title(), "slug": slug, "description": f"{slug} helps people", "category": "productivity",
            "paymentProvider": "stripe", "targetAudience": "b2c",
            "revenue": {"last30Days": mrr_cents, "mrr": mrr_cents, "total": mrr_cents * 10},
            "customers": customers, "activeSubscriptions": customers, "growth30d": growth, "onSale": False, **kw}


def disc_item(slug, mrr_dollars, **kw):
    return {"name": slug, "slug": slug, "description": None, "category": "Social Media",
            "paymentProvider": "stripe", "revenue": {"last30Days": mrr_dollars, "mrr": mrr_dollars, "total": 1},
            "growth30d": 5, "onSale": False, "stealthMode": False, **kw}


class FakeResponse(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body.encode("utf-8"))
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeServer:
    """Routes urllib requests to canned TrustMRR answers and records them."""

    def __init__(self, pages, details=None, discovery=None):
        self.pages, self.details = pages, details or {}
        self.discovery = discovery or {"recentlyAddedStartups": [], "fastestGrowingStartups": []}
        self.calls = []

    def __call__(self, req, timeout=None):
        url = req.full_url
        self.calls.append((url, req.headers.get("Authorization")))
        if url.endswith("/api/ai/discovery"):
            return FakeResponse(json.dumps(self.discovery))
        if "/api/v1/startups?" in url:
            page = int(url.split("page=")[1].split("&")[0])
            data = self.pages[page - 1] if page <= len(self.pages) else []
            return FakeResponse(json.dumps({"data": data, "meta": {"total": 99, "page": page, "limit": 10,
                                                                    "hasMore": page < len(self.pages)}}))
        slug = url.rsplit("/", 1)[1]
        if slug in self.details:
            return FakeResponse(json.dumps({"data": self.details[slug]}))
        raise urllib.error.HTTPError(url, 404, "nf", {}, io.BytesIO(b'{"error":"Startup not found"}'))


def client_for(server, key="tmrr_test"):
    return ideas_sync.Client(key, 10, opener=server, sleep=lambda s: None)


# ------------------------------------------------------------ normalize ----

def test_normalize_converts_cents_and_dollars():
    a = ideas_sync.normalize(api_item("alpha", 250_000), cents=True, source="trustmrr_api")
    assert a["mrr"] == 2500 and a["revenue_total"] == 25000 and a["customers"] == 100
    assert a["url"] == "https://trustmrr.com/startup/alpha"
    d = ideas_sync.normalize(disc_item("beta", 1234.5), cents=False, source="discovery")
    assert d["mrr"] == 1234.5 and d["category"] == "social-media" and d["customers"] is None
    assert ideas_sync.normalize({"name": "no slug"}, cents=True, source="x") is None


def test_normalize_strips_control_chars_from_untrusted_text():
    p = ideas_sync.normalize(api_item("x", 100, description="hi\x00\x1b[31m there"), cents=True, source="a")
    assert p["description"] == "hi[31m there"


# ------------------------------------------------------------------ sync ----

def test_run_without_key_uses_only_public_discovery(fresh_db):
    server = FakeServer([], discovery={"recentlyAddedStartups": [disc_item("new1", 10)],
                                       "fastestGrowingStartups": [disc_item("fast1", 3000)]})
    res = ideas_sync.run_once(ideas_sync.Client(None, 10, opener=server, sleep=lambda s: None))
    assert res["status"] == "ok" and res["requests"] == 1
    assert all(auth is None for _, auth in server.calls)
    new = ideas.list_products(view="new")["items"]
    assert [p["slug"] for p in new] == ["new1"]  # first-ever fastest-growing rows are baseline


def test_run_with_key_sweeps_pages_and_fetches_details(fresh_db, monkeypatch):
    monkeypatch.setenv(ideas_sync.ENV_VAR, "tmrr_test")
    pages = [[api_item(f"p{i}", 150_000 + i) for i in range(10)], [api_item("p10", 500_000)]]
    details = {"p10": {**api_item("p10", 500_000), "startupInsights": {"targetPersona": "Nail salon owners"},
                       "techStack": [{"slug": "nextjs", "category": "framework"}]}}
    server = FakeServer(pages, details)
    res = ideas_sync.run_once(client_for(server))
    assert res["status"] == "ok"
    list_calls = [u for u, _ in server.calls if "/api/v1/startups?" in u]
    assert len(list_calls) == 2 and "minMrr=100000" in list_calls[0] and "maxMrr=2000000" in list_calls[0]
    assert all(a == "Bearer tmrr_test" for u, a in server.calls if "/api/v1/" in u)
    p = ideas.get_product("p10")
    assert p["mrr"] == 5000 and p["detail"]["target_persona"] == "Nail salon owners"
    assert p["detail"]["tech_stack"] == [{"slug": "nextjs", "category": "framework"}]
    assert db.get_meta("ideas.last_full_sweep") is not None
    # Unknown slugs (404) are skipped rather than failing the run.
    assert res["details"] == 1


def test_run_resumes_list_from_cursor_when_budget_runs_out(fresh_db, monkeypatch):
    monkeypatch.setenv(ideas_sync.ENV_VAR, "tmrr_test")
    ideas_sync.save_cfg({"max_requests": 4, "max_details": 1})
    pages = [[api_item(f"a{p}{i}", 200_000) for i in range(10)] for p in range(6)]
    ideas_sync.run_once(client_for(FakeServer(pages)))
    assert db.get_meta("ideas.list_page") == "3"  # discovery + 2 pages, 1 request kept for details
    server = FakeServer(pages)
    ideas_sync.run_once(client_for(server))
    first = next(u for u, _ in server.calls if "/api/v1/startups?" in u)
    assert "page=3" in first


def test_bad_key_is_reported_not_raised(fresh_db, monkeypatch):
    monkeypatch.setenv(ideas_sync.ENV_VAR, "tmrr_bad")

    def opener(req, timeout=None):
        if "discovery" in req.full_url:
            return FakeResponse('{"recentlyAddedStartups": [], "fastestGrowingStartups": []}')
        raise urllib.error.HTTPError(req.full_url, 401, "u", {}, io.BytesIO(b"{}"))

    res = ideas_sync.run_once(ideas_sync.Client("tmrr_bad", 10, opener=opener, sleep=lambda s: None))
    assert res["status"] == "error" and "401" in res["error"]
    assert ideas_sync.status()["runs"][0]["status"] == "error"


def test_client_throttles_and_waits_on_429():
    slept, t = [], [0.0]

    def sleep(s):
        slept.append(s)
        t[0] += s

    calls = []

    def opener(req, timeout=None):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 429, "r", {"X-RateLimit-Reset": "0"}, io.BytesIO(b"{}"))
        return FakeResponse("{}")

    c = ideas_sync.Client("k", 10, opener=opener, sleep=sleep, clock=lambda: t[0])
    c.get("/a")
    c.get("/b")
    assert slept[0] == 60          # 429 without a usable reset → one minute
    assert slept[1] == pytest.approx(6.2)  # second call waits out the 10/min gap


def test_due_respects_interval(fresh_db):
    assert ideas_sync.due()
    db.set_meta("ideas.last_sync", ideas.now_iso())
    assert not ideas_sync.due()
    ideas_sync.save_cfg({"auto_sync": False})
    db.set_meta("ideas.last_sync", "2000-01-01T00:00:00+00:00")
    assert not ideas_sync.due()


# ------------------------------------------------- clusters, cards, rules ----

def seed(n=4, mrr=2000):
    rows = [ideas_sync.normalize(api_item(f"s{i}", (mrr + i * 1000) * 100, customers=200), cents=True,
                                 source="trustmrr_api") for i in range(n)]
    ideas.upsert_products(rows)
    return [r["slug"] for r in rows]


def test_cluster_stats_and_card_suggestions(fresh_db):
    slugs = seed(4)
    c = ideas.create_cluster("美甲店自助预约")
    for s in slugs:
        c = ideas.set_cluster_product(c["id"], s, True)
    st = c["stats"]
    assert st["count"] == 4 and st["paying_count"] == 4 and st["mrr_median"] == 3500
    assert ideas.list_products(mark="interested")["total"] == 4  # clustering marks interest
    card = ideas.create_card(c["id"])
    assert card["need"] == "美甲店自助预约"
    sug = card["suggested"]
    assert sug["gates"] == {"paying": True, "recurring": True}
    assert sug["scores"]["strength"] == 1 and sug["scores"]["breadth"] == 2 and sug["scores"]["trend"] == 2


def test_evaluate_tiers_and_red_flags():
    gates = {k: True for k in ideas.GATES}
    full = {k: 2 for k in ideas.SCORES}
    assert ideas.evaluate(gates, full, [])["verdict"] == "validate"
    assert ideas.evaluate(gates, full, ["peer_loop"])["verdict"] == "watch"
    assert ideas.evaluate(gates, {"strength": 2, "breadth": 2, "trend": 2}, [])["verdict"] == "watch"
    assert ideas.evaluate(gates, {"strength": 1}, [])["verdict"] == "drop"
    assert ideas.evaluate({**gates, "reach": False}, full, [])["verdict"] == "gates"


def test_card_cannot_leave_draft_without_signals_and_life_mapping(fresh_db):
    slugs = seed(2)
    c = ideas.create_cluster("x")
    for s in slugs:
        ideas.set_cluster_product(c["id"], s, True)
    card = ideas.create_card(c["id"])
    with pytest.raises(ideas.DraftRule) as e:
        ideas.update_card(card["id"], {"status": "validating"})
    assert set(e.value.reasons) == {"signals", "life_mapping"}
    ideas.upsert_products([ideas_sync.normalize(api_item("third", 300_000), cents=True, source="trustmrr_api")])
    ideas.set_cluster_product(c["id"], "third", True)
    out = ideas.update_card(card["id"], {"status": "validating", "life_mapping": "楼下美甲店"})
    assert out["status"] == "validating"


def test_stale_validating_card_and_markdown_has_no_metrics(fresh_db):
    slugs = seed(3)
    c = ideas.create_cluster("预约")
    for s in slugs:
        ideas.set_cluster_product(c["id"], s, True)
    card = ideas.create_card(c["id"])
    ideas.update_card(card["id"], {"status": "validating", "life_mapping": "朋友的工作室"})
    with db.locked_conn() as conn:
        conn.execute("UPDATE idea_cards SET updated_at = '2020-01-01T00:00:00+00:00' WHERE id = ?", (card["id"],))
        conn.commit()
    assert ideas.get_card(card["id"])["stale"]
    assert ideas.week()["validating"][0]["stale"]
    card = ideas.add_validation(card["id"], "聊 3 位店主", "2026-10-05", "2 位愿意试用")
    assert not card["stale"]
    md = ideas.card_markdown(card)
    assert "https://trustmrr.com/startup/s0" in md and "聊 3 位店主" in md
    assert "$" not in md and "2000" not in md


def test_search_covers_products_cards_and_observations(fresh_db):
    seed(1)
    ideas.add_observation("物业通知全靠微信群,老人经常错过", ["社区"])
    card = ideas.create_card(None, "物业通知")
    res = ideas.search("物业")
    assert len(res["observations"]) == 1 and res["cards"][0]["id"] == card["id"]
    assert ideas.search("helps")["products"][0]["slug"] == "s0"


def test_ignored_products_drop_out_of_default_list(fresh_db):
    seed(3)
    ideas.set_mark("s1", "ignored")
    assert {p["slug"] for p in ideas.list_products()["items"]} == {"s0", "s2"}
    assert ideas.list_products(view="todo")["total"] == 2
    assert [p["slug"] for p in ideas.list_products(mark="ignored")["items"]] == ["s1"]


# ---------------------------------------------------------------- routes ----

def test_routes_round_trip(fresh_db):
    from tokenscope.web import app
    client = TestClient(app)
    seed(3)
    c = client.post("/api/ideas/clusters", json={"name": "需求A", "slug": "s0"}, headers=LOCAL).json()
    for s in ("s1", "s2"):
        client.put(f"/api/ideas/clusters/{c['id']}/products/{s}", headers=LOCAL)
    card = client.post("/api/ideas/cards", json={"cluster_id": c["id"]}, headers=LOCAL).json()
    r = client.put(f"/api/ideas/cards/{card['id']}", json={"status": "doing"}, headers=LOCAL)
    assert r.status_code == 409 and r.json()["detail"]["reasons"] == ["life_mapping"]
    r = client.put(f"/api/ideas/cards/{card['id']}",
                   json={"life_mapping": "身边的人", "scores": {"reach": 2}, "red_flags": ["peer_loop"]}, headers=LOCAL)
    assert r.status_code == 200 and r.json()["scores"] == {"reach": 2}
    assert client.put(f"/api/ideas/cards/{card['id']}", json={"scores": {"reach": 3}},
                      headers=LOCAL).status_code == 422
    assert client.get(f"/api/ideas/cards?ids={card['id']}", headers=LOCAL).json()[0]["id"] == card["id"]
    md = client.get(f"/api/ideas/cards/{card['id']}/markdown", headers=LOCAL)
    assert md.status_code == 200 and md.text.startswith("# 需求A")
    week = client.get("/api/ideas/week", headers=LOCAL).json()
    assert week["clusters"] == 1 and week["sync"]["key"]["configured"] is False
    assert client.put("/api/ideas/settings", json={"min_mrr": 9000, "max_mrr": 100},
                      headers=LOCAL).status_code == 422
    assert client.put("/api/ideas/key", json={"key": "sk-nope"}, headers=LOCAL).status_code == 422


def test_routes_refuse_non_local_hosts(fresh_db):
    from tokenscope.web import app
    client = TestClient(app)
    assert client.get("/api/ideas/week", headers={"host": "evil.example"}).status_code == 403
