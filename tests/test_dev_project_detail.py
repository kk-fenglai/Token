"""F28 dev-project detail: README summary, language / stack detection, meta
validation and storage, the detail payload on a real repo, and the routes."""
import json
import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient

from tokenscope import db, dev_project_detail as dpd, dev_projects
from tokenscope.parser import normalize_cwd

HAS_GIT = shutil.which("git") is not None
needs_git = pytest.mark.skipif(not HAS_GIT, reason="git not installed")
LOCAL = {"host": "127.0.0.1:8787"}


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path))
    db.reset_conn()
    yield db.get_conn()
    db.reset_conn()


# --------------------------------------------------------------- pure parts ----

def test_readme_summary_skips_badges_code_and_lists():
    text = """# My App

[![CI](https://x/badge.svg)](https://x) ![v](https://y.svg)

<p align="center"><img src="logo.png"></p>

```bash
npm i
```

A **tiny** tool that [does things](https://example.com) well.
Second line of the same paragraph.

- a list item
"""
    s = dpd.readme_summary(text)
    assert s["title"] == "My App"
    assert s["summary"] == "A tiny tool that does things well. Second line of the same paragraph."


def test_readme_summary_without_prose():
    assert dpd.readme_summary("## Setup\n\n- one\n- two\n") == {"title": None, "summary": None}


def test_languages_by_bytes_ignores_generated_and_markup():
    sizes = {"src/a.py": 700, "web/b.ts": 300, "README.md": 10_000, "dist/bundle.js": 90_000,
             "static/assets/index-C376JtGx.js": 50_000, "x.min.js": 5_000, "package-lock.json": 9_999}
    langs = dpd.languages("r", list(sizes), stat=lambda p: sizes[p.replace("\\", "/").split("r/", 1)[1]])
    assert [(l["name"], l["pct"]) for l in langs] == [("Python", 70.0), ("TypeScript", 30.0)]
    only_docs = dpd.languages("r", ["README.md"], stat=lambda p: 10)
    assert only_docs == [{"name": "Markdown", "bytes": 10, "pct": 100.0}]


def test_is_generated():
    assert dpd.is_generated("frontend/dist/app.js")
    assert dpd.is_generated("src/tokenscope/static/assets/DevProjects-CYt_KSVC.js")
    assert not dpd.is_generated("src/assets/logo.js")
    assert not dpd.is_generated("src/build_tools.py")


def test_detect_stack_from_manifests(tmp_path):
    (tmp_path / "package.json").write_text(json.dumps({
        "name": "web", "description": "the web app", "version": "1.2.0",
        "dependencies": {"react": "^18", "next": "14"}, "devDependencies": {"typescript": "5"}}), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "api"\ndependencies = ["fastapi>=0.1", "anthropic"]\n', encoding="utf-8")
    (tmp_path / "Dockerfile").write_text("FROM x", encoding="utf-8")
    out = dpd.detect_stack(str(tmp_path), ["package.json", "pyproject.toml", "Dockerfile"])
    assert out["stack"] == ["Next.js", "React", "TypeScript", "FastAPI", "Anthropic SDK", "Docker"]
    assert out["manifest"] == {"kind": "package.json", "name": "web", "description": "the web app", "version": "1.2.0"}


def test_detect_stack_survives_broken_manifests(tmp_path):
    (tmp_path / "package.json").write_text("{nope", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[[[", encoding="utf-8")
    assert dpd.detect_stack(str(tmp_path), ["package.json", "pyproject.toml"]) == {"stack": [], "manifest": None}


def test_clean_meta_validates_and_normalizes():
    fields, errors = dpd.clean_meta({"alias": "  My App ", "tags": ["web", " Web ", "a  b", ""],
                                     "stage": "active", "notes": "todo\n\n"})
    assert errors == []
    assert fields == {"alias": "My App", "tags": ["web", "a b"], "stage": "active", "notes": "todo"}
    _, errors = dpd.clean_meta({"alias": 3, "stage": "done", "tags": "x", "color": "red"})
    assert len(errors) == 4
    _, errors = dpd.clean_meta({"tags": [str(i) for i in range(13)]})
    assert errors == ["at most 12 tags"]
    _, errors = dpd.clean_meta({"description": "x" * 2001})
    assert errors


def test_meta_roundtrip(fresh_db):
    assert dpd.get_meta("c:/a") == dpd.EMPTY_META
    dpd.save_meta("c:/a", {"alias": "A", "tags": ["中文", "x"]})
    m = dpd.save_meta("c:/a", {"stage": "paused"})  # partial update keeps the rest
    assert (m["alias"], m["tags"], m["stage"]) == ("A", ["中文", "x"], "paused") and m["updated_at"]
    assert dpd.get_meta("c:/a") == m
    assert set(dpd.all_meta()) == {"c:/a"}


# ------------------------------------------------------------------ real repo ----

def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path, monkeypatch, fresh_db):
    work = tmp_path / "work"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, capture_output=True)
    for k, v in (("user.email", "t@example.com"), ("user.name", "Tess"), ("commit.gpgsign", "false")):
        _git(work, "config", k, v)
    (work / "README.md").write_text("# Work\n\nDoes the work.\n", encoding="utf-8")
    (work / "app.py").write_text("print(1)\n" * 20, encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-qm", "init")
    (work / "b.py").write_text("x = 1\n", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-qm", "second")
    _git(work, "branch", "feature")
    key = normalize_cwd(str(work))
    monkeypatch.setattr(dev_projects, "snapshot", lambda *a, **k: {"items": [{
        "path": key, "name": "work", "sources": ["manual"], "pinned": False, "last_active": None}]})
    monkeypatch.setattr(dpd, "token_usage", lambda p: None)
    return key


@needs_git
def test_detail_payload(repo):
    d = dpd.detail(repo)
    assert d["item"]["branch"] == "main" and d["item"]["level"] == "info"  # no remote
    assert d["readme"]["title"] == "Work" and d["readme"]["summary"] == "Does the work."
    assert d["languages"][0]["name"] == "Python"
    g = d["git"]
    assert g["commit_count"] == 2 and g["file_count"] == 3 and g["first_commit_at"]
    assert [c["subject"] for c in g["recent_commits"]] == ["second", "init"]
    assert {b["name"] for b in g["branches"]} == {"main", "feature"}
    assert next(b for b in g["branches"] if b["name"] == "main")["current"]
    assert g["contributors"] == [{"name": "Tess", "commits": 2}]
    assert d["meta"] == dpd.EMPTY_META and d["stages"] == list(dpd.STAGES)


@needs_git
def test_detail_of_untracked_path(repo):
    with pytest.raises(dpd.NotTracked):
        dpd.detail("c:/elsewhere")


# -------------------------------------------------------------------- routes ----

@needs_git
def test_routes(repo, monkeypatch):
    from tokenscope.web import app
    client = TestClient(app)
    r = client.get(f"/api/dev-projects/detail?path={repo}", headers=LOCAL)
    assert r.status_code == 200 and r.json()["git"]["commit_count"] == 2
    assert client.get(f"/api/dev-projects/detail?path={repo}", headers={"host": "evil.example"}).status_code == 403
    assert client.get("/api/dev-projects/detail?path=c:/nope", headers=LOCAL).status_code == 404

    r = client.put("/api/dev-projects/meta", json={"path": repo, "alias": "工作", "tags": ["cli"]}, headers=LOCAL)
    assert r.status_code == 200 and r.json()["alias"] == "工作"
    assert client.put("/api/dev-projects/meta", json={"path": repo, "stage": "bogus"}, headers=LOCAL).status_code == 422
    assert client.put("/api/dev-projects/meta", json={"path": "c:/nope", "alias": "x"}, headers=LOCAL).status_code == 404
    assert client.put("/api/dev-projects/meta", json={"path": repo, "alias": "x"},
                      headers={**LOCAL, "origin": "https://evil.example"}).status_code == 403

    items = client.get("/api/dev-projects").json()["items"]
    assert items[0]["meta"]["alias"] == "工作" and items[0]["meta"]["tags"] == ["cli"]

    r = client.post("/api/dev-projects/github-description", json={"path": repo}, headers=LOCAL)
    assert r.status_code == 200 and r.json() == {"ok": False, "error": "not_github", "output": ""}

    monkeypatch.setattr(dpd, "editor_path", lambda: None)
    assert client.post("/api/dev-projects/open-editor", json={"path": repo}, headers=LOCAL).status_code == 501
    opened = []
    monkeypatch.setattr(dpd, "open_in_editor", lambda p: opened.append(p) or True)
    assert client.post("/api/dev-projects/open-editor", json={"path": repo}, headers=LOCAL).json() == {"ok": True}
    assert opened == [repo]
