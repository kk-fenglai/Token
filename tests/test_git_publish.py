"""F27 one-click publish: pure helpers, plan/publish against real git repos
with a local bare remote, the gh create path (gh stubbed), and the endpoint's
loopback guard."""
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from tokenscope import dev_projects, git_publish
from tokenscope.parser import normalize_cwd

HAS_GIT = shutil.which("git") is not None
needs_git = pytest.mark.skipif(not HAS_GIT, reason="git not installed")


def _git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


# --------------------------------------------------------------- pure parts ----

def test_parse_porcelain_v1_with_rename_and_untracked():
    raw = " M src/app.py\0A  new.txt\0R  renamed.txt\0old.txt\0?? 文件.txt\0"
    files = git_publish.parse_porcelain_v1(raw)
    assert files == [
        {"path": "src/app.py", "status": ".M"},
        {"path": "new.txt", "status": "A."},
        {"path": "renamed.txt", "status": "R."},
        {"path": "文件.txt", "status": "??"},
    ]


@pytest.mark.parametrize("path, expect", [
    (".env", True), ("app/.env.local", True), (".env.example", False), ("config/.env.sample", False),
    ("certs/server.pem", True), ("id_rsa", True), ("id_ed25519.pub", True),
    ("gcp-service-account.json", True), ("credentials.json", True), (".npmrc", True),
    ("src/env.py", False), ("README.md", False), ("keys.ts", False),
])
def test_is_sensitive(path, expect):
    assert git_publish.is_sensitive(path) is expect


def test_repo_name_helpers():
    assert git_publish.suggest_repo_name("c:/users/me/desktop/Token消耗量") == "Token"
    assert git_publish.suggest_repo_name("c:/dev/项目") == "my-project"
    assert git_publish.suggest_repo_name("c:/dev/my app (v2)") == "my-app-v2"
    assert git_publish.valid_repo_name("my-app.v2") and git_publish.valid_repo_name("org/my_app")
    for bad in ("", "..", "has space", "a/b/c", "中文", "x" * 101):
        assert not git_publish.valid_repo_name(bad), bad


def test_default_message():
    files = [{"path": p, "status": ".M"} for p in ("src/a.py", "b.txt", "docs/c.md", "d", "e")]
    assert git_publish.default_message(files) == "Update a.py, b.txt, c.md and 2 more"
    assert git_publish.default_message(files[:1]) == "Update a.py"
    assert git_publish.default_message([]) == ""


@pytest.mark.parametrize("text, code", [
    ("Author identity unknown\n*** Please tell me who you are.", "identity"),
    (" ! [rejected]        main -> main (fetch first)", "rejected"),
    ("fatal: Authentication failed for 'https://github.com/a/b.git/'", "auth"),
    ("GraphQL: Name already exists on this account (createRepository)", "repo_exists"),
    ("remote: error: GH013: Repository rule violations found", "rejected_by_github"),
    ("something odd", "failed"),
])
def test_classify_failure(text, code):
    assert git_publish._classify_failure(text) == code


def test_redact_strips_credentials_from_urls():
    assert git_publish._redact("To https://me:ghp_secret@github.com/a/b.git") == "To https://***@github.com/a/b.git"


# ------------------------------------------------------------ real git repos ----

@pytest.fixture()
def repo(tmp_path, monkeypatch):
    """A work repo pushed to a local bare remote, registered as tracked."""
    work, bare = tmp_path / "work", tmp_path / "remote.git"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "a.txt").write_text("1", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-qm", "init")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-qu", "origin", "main")
    key = normalize_cwd(str(work))
    monkeypatch.setattr(dev_projects, "snapshot",
                        lambda *a, **k: {"items": [{"path": key, "name": "work"}]})
    return SimpleNamespace(dir=work, key=key, bare=bare)


def _remote_log(bare) -> list[str]:
    r = subprocess.run(["git", "-C", str(bare), "log", "--format=%s", "main"],
                       capture_output=True, check=True)
    return r.stdout.decode().split("\n")[:-1]


@needs_git
def test_not_tracked_is_refused(repo):
    with pytest.raises(git_publish.PublishError) as e:
        git_publish.plan("c:/somewhere/else")
    assert e.value.code == "not_tracked"


@needs_git
def test_clean_repo_has_nothing_to_do(repo):
    p = git_publish.plan(repo.key)
    assert p["action"] == "nothing" and p["file_count"] == 0 and p["commits"] == []
    with pytest.raises(git_publish.PublishError) as e:
        git_publish.publish(repo.key)
    assert e.value.code == "nothing_to_push"


@needs_git
def test_commit_and_push_dirty_changes(repo):
    (repo.dir / "a.txt").write_text("2", encoding="utf-8")
    (repo.dir / "sub").mkdir()
    (repo.dir / "sub" / "new.py").write_text("x", encoding="utf-8")
    (repo.dir / ".env").write_text("TOKEN=1", encoding="utf-8")
    p = git_publish.plan(repo.key)
    assert p["action"] == "push" and p["file_count"] == 3
    assert {f["path"] for f in p["files"]} == {"a.txt", "sub/new.py", ".env"}  # untracked dirs expanded
    assert p["sensitive"] == [".env"]
    assert p["default_message"].startswith("Update ")

    r = git_publish.publish(repo.key, message="ship it")
    assert r["ok"] and r["error"] is None and r["ahead"] == 0 and r["changes"] == 0
    assert [s["step"] for s in r["steps"]] == ["add", "commit", "push"]
    assert r["steps"][0]["cmd"] == "git add -A"
    assert _remote_log(repo.bare)[0] == "ship it"


@needs_git
def test_push_only_leaves_uncommitted_changes_alone(repo):
    (repo.dir / "b.txt").write_text("b", encoding="utf-8")
    _git(repo.dir, "add", ".")
    _git(repo.dir, "commit", "-qm", "second")
    (repo.dir / "wip.txt").write_text("wip", encoding="utf-8")
    p = git_publish.plan(repo.key)
    assert p["ahead"] == 1 and [c["subject"] for c in p["commits"]] == ["second"]
    r = git_publish.publish(repo.key, commit=False)
    assert r["ok"] and [s["step"] for s in r["steps"]] == ["push"]
    assert r["changes"] == 1 and _remote_log(repo.bare)[0] == "second"


@needs_git
def test_new_branch_is_pushed_with_upstream(repo):
    _git(repo.dir, "checkout", "-qb", "feature")
    (repo.dir / "f.txt").write_text("f", encoding="utf-8")
    _git(repo.dir, "add", ".")
    _git(repo.dir, "commit", "-qm", "on feature")
    (repo.dir / "g.txt").write_text("g", encoding="utf-8")
    p = git_publish.plan(repo.key)
    assert p["action"] == "push_upstream" and p["remote"] == "origin"
    assert [c["subject"] for c in p["commits"]] == ["on feature"]  # not "init", origin has it
    r = git_publish.publish(repo.key, message="feature work")
    assert r["ok"] and r["steps"][-1]["cmd"] == "git push -u origin feature"
    assert dev_projects.inspect_repo(repo.key)["has_upstream"]


@needs_git
def test_rejected_push_is_reported_not_forced(repo, tmp_path):
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(repo.bare), str(other)], check=True, capture_output=True)
    _git(other, "config", "user.email", "o@example.com")
    _git(other, "config", "user.name", "o")
    (other / "o.txt").write_text("o", encoding="utf-8")
    _git(other, "add", ".")
    _git(other, "commit", "-qm", "from elsewhere")
    _git(other, "push", "-q")

    (repo.dir / "mine.txt").write_text("m", encoding="utf-8")
    r = git_publish.publish(repo.key, message="mine")
    assert not r["ok"] and r["error"] == "rejected"
    assert [s["ok"] for s in r["steps"]] == [True, True, False]  # the commit stays local
    assert _remote_log(repo.bare)[0] == "from elsewhere"


@needs_git
def test_detached_head_is_blocked(repo):
    _git(repo.dir, "checkout", "-q", "--detach")
    p = git_publish.plan(repo.key)
    assert p["action"] == "blocked" and p["blocked_reason"] == "detached"
    with pytest.raises(git_publish.PublishError) as e:
        git_publish.publish(repo.key)
    assert e.value.code == "detached"


@needs_git
def test_no_remote_creates_repo_with_gh(repo, monkeypatch):
    _git(repo.dir, "remote", "remove", "origin")
    (repo.dir / "n.txt").write_text("n", encoding="utf-8")

    monkeypatch.setattr(git_publish, "gh_status", lambda force=False: {"available": False, "user": None})
    assert git_publish.plan(repo.key)["blocked_reason"] == "gh_missing"
    monkeypatch.setattr(git_publish, "gh_status", lambda force=False: {"available": True, "user": None})
    assert git_publish.plan(repo.key)["blocked_reason"] == "gh_logged_out"

    monkeypatch.setattr(git_publish, "gh_status", lambda force=False: {"available": True, "user": "me"})
    monkeypatch.setattr(git_publish, "gh_path", lambda: "C:/Program Files/GitHub CLI/gh.exe")
    real_run, calls = git_publish._run, []

    def fake_run(cmd, cwd, timeout):
        if cmd[0].endswith("gh.exe"):
            calls.append(cmd)
            return 0, "https://github.com/me/work\n", ""
        return real_run(cmd, cwd, timeout)
    monkeypatch.setattr(git_publish, "_run", fake_run)

    p = git_publish.plan(repo.key)
    assert p["action"] == "create_repo" and p["default_repo_name"] == "work"
    with pytest.raises(git_publish.PublishError) as e:
        git_publish.publish(repo.key, repo_name="bad name")
    assert e.value.code == "bad_repo_name"

    r = git_publish.publish(repo.key, message="first", repo_name="work", private=True)
    assert r["ok"]
    assert calls[-1][1:] == ["repo", "create", "work", "--private", "--source",
                             os.path.normpath(repo.key), "--remote", "origin", "--push"]
    assert r["steps"][-1]["cmd"] == "gh repo create work --private --source . --remote origin --push"


# ------------------------------------------------------------------ endpoint ----

@needs_git
def test_endpoint_rejects_non_local_callers(repo):
    from tokenscope.web import app
    client = TestClient(app)
    url = f"/api/dev-projects/publish-plan?path={repo.key}"
    assert client.get(url, headers={"host": "evil.example:8787"}).status_code == 403
    assert client.get(url, headers={"host": "127.0.0.1:8787",
                                    "origin": "https://evil.example"}).status_code == 403
    ok = client.get(url, headers={"host": "127.0.0.1:8787", "origin": "http://localhost:5173"})
    assert ok.status_code == 200 and ok.json()["action"] == "nothing"
    r = client.post("/api/dev-projects/publish", json={"path": repo.key},
                    headers={"host": "localhost:8787"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "nothing_to_push"
    r = client.post("/api/dev-projects/publish", json={"path": "c:/nope"},
                    headers={"host": "localhost:8787"})
    assert r.status_code == 404
