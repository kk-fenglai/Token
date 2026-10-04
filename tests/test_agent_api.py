"""F29 agent routes: loopback guard on every route, key handling never leaks
the key, settings validation, SSE chat end to end with a fake client."""
import json

import pytest
from agent_fakes import FakeClient, text
from fastapi.testclient import TestClient

from tokenscope import db
from tokenscope.agent import llm, loop, store

LOCAL = {"host": "127.0.0.1:8787"}
KEY = "sk-abcdefghijklmnop1234"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    db.reset_conn()
    from tokenscope.web import app
    yield TestClient(app)
    db.reset_conn()


ROUTES = [
    ("post", "/api/agent/chat", {"message": "hi"}),
    ("post", "/api/agent/runs/x/cancel", None),
    ("post", "/api/agent/runs/x/confirm", {"tool_call_id": "a", "approve": True}),
    ("get", "/api/agent/conversations", None),
    ("get", "/api/agent/conversations/x", None),
    ("patch", "/api/agent/conversations/x", {"title": "t"}),
    ("delete", "/api/agent/conversations/x", None),
    ("get", "/api/agent/settings", None),
    ("put", "/api/agent/settings", {"thinking": False}),
    ("put", "/api/agent/key", {"api_key": KEY}),
    ("delete", "/api/agent/key", None),
    ("post", "/api/agent/test", None),
    ("get", "/api/agent/usage", None),
    ("get", "/api/agent/patrol", None),
    ("post", "/api/agent/patrol/run", None),
]


@pytest.mark.parametrize("method, url, body", ROUTES)
def test_every_route_is_loopback_only(client, method, url, body):
    kw = {"json": body} if body is not None else {}
    assert getattr(client, method)(url, headers={"host": "evil.example:8787"}, **kw).status_code == 403
    assert getattr(client, method)(url, headers={**LOCAL, "origin": "https://evil.example"}, **kw).status_code == 403


def test_key_is_write_only(client):
    s = client.get("/api/agent/settings", headers=LOCAL).json()
    assert s["key"] == {"configured": False, "source": "none", "masked": None}
    r = client.put("/api/agent/key", json={"api_key": KEY}, headers=LOCAL)
    assert r.status_code == 200 and r.json()["masked"] == "sk-…1234"
    for payload in (client.get("/api/agent/settings", headers=LOCAL).text, r.text):
        assert KEY not in payload and "abcdefghijklmnop" not in payload
    assert client.put("/api/agent/key", json={"api_key": "has space"}, headers=LOCAL).status_code == 422
    assert client.delete("/api/agent/key", headers=LOCAL).json()["configured"] is False


def test_env_key_wins(client, monkeypatch):
    client.put("/api/agent/key", json={"api_key": KEY}, headers=LOCAL)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-from-env-9999")
    assert client.get("/api/agent/settings", headers=LOCAL).json()["key"]["source"] == "env"


def test_settings_validation_and_merge(client):
    r = client.put("/api/agent/settings", json={"model": "deepseek-v4-pro", "patrol": {"enabled": True, "time": "07:30"}},
                   headers=LOCAL)
    assert r.status_code == 200
    s = r.json()
    assert s["model"] == "deepseek-v4-pro" and s["patrol"]["enabled"] and s["patrol"]["time"] == "07:30"
    assert s["patrol"]["schedule"] == "daily"  # untouched sub-key survives
    bad = client.put("/api/agent/settings", json={"patrol": {"time": "25:00"}, "max_iterations": 0, "x": 1},
                     headers=LOCAL)
    assert bad.status_code == 422 and len(bad.json()["detail"]["detail"]) == 3


def _sse(raw: str) -> list[tuple[str, dict]]:
    out = []
    for block in raw.split("\n\n"):
        ev, data = None, None
        for line in block.splitlines():
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = json.loads(line[6:])
        if ev:
            out.append((ev, data))
    return out


def test_chat_streams_and_persists(client, monkeypatch):
    assert client.post("/api/agent/chat", json={"message": "hi"}, headers=LOCAL).status_code == 412  # no key
    client.put("/api/agent/key", json={"api_key": KEY}, headers=LOCAL)
    fake = FakeClient([text("你好,本月花费 $12.34。", reasoning="look it up")])
    monkeypatch.setattr(llm, "make_client", lambda key, cfg: fake)

    r = client.post("/api/agent/chat", json={"message": "花了多少", "page_context": {"route": "/projects"}},
                    headers=LOCAL)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = _sse(r.text)
    names = [e for e, _ in events]
    assert names[0] == "run_start" and names[-1] == "done" and "text_delta" in names and "reasoning_delta" in names
    cid = events[0][1]["conversation_id"]
    body = "".join(d["text"] for e, d in events if e == "text_delta")
    assert body == "你好,本月花费 $12.34。"
    assert "/projects" in fake.requests[0]["messages"][1]["content"]

    conv = client.get(f"/api/agent/conversations/{cid}", headers=LOCAL).json()
    assert conv["title"] == "花了多少" and [m["role"] for m in conv["messages"]] == ["user", "assistant"]
    assert conv["usage"]["requests"] == 1
    lst = client.get("/api/agent/conversations", headers=LOCAL).json()["items"]
    assert [c["id"] for c in lst] == [cid]
    assert client.get("/api/agent/usage", headers=LOCAL).json()["requests"] == 1

    assert client.patch(f"/api/agent/conversations/{cid}", json={"title": "改名"}, headers=LOCAL).json()["title"] == "改名"
    loop._BUSY.add(cid)
    try:
        assert client.post("/api/agent/chat", json={"message": "again", "conversation_id": cid},
                           headers=LOCAL).status_code == 409
        assert client.delete(f"/api/agent/conversations/{cid}", headers=LOCAL).status_code == 409
    finally:
        loop._BUSY.discard(cid)
    assert client.delete(f"/api/agent/conversations/{cid}", headers=LOCAL).json() == {"ok": True}
    assert store.get_conversation(cid) is None


def test_chat_validation(client):
    client.put("/api/agent/key", json={"api_key": KEY}, headers=LOCAL)
    assert client.post("/api/agent/chat", json={"message": ""}, headers=LOCAL).status_code == 422
    assert client.post("/api/agent/chat", json={"message": "x", "conversation_id": "nope"},
                       headers=LOCAL).status_code == 404
    assert client.post("/api/agent/chat", json={"message": "x", "page_context": "str"},
                       headers=LOCAL).status_code == 422


def test_test_connection(client, monkeypatch):
    assert client.post("/api/agent/test", headers=LOCAL).json()["code"] == "no_key"
    client.put("/api/agent/key", json={"api_key": KEY}, headers=LOCAL)
    monkeypatch.setattr("tokenscope.api.routes_agent.make_client", lambda key, cfg: FakeClient([]))
    r = client.post("/api/agent/test", headers=LOCAL).json()
    assert r["ok"] and r["configured_available"] and "deepseek-v4-pro" in r["models"]
