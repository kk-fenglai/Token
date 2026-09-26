"""F26 dev-project tracker: porcelain parsing, classification, discovery merge,
real git repos in tmp_path, and the daily toast dedupe."""
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

import pytest

from tokenscope import db, dev_projects

HAS_GIT = shutil.which("git") is not None
needs_git = pytest.mark.skipif(not HAS_GIT, reason="git not installed")

CFG = dict(dev_projects.DEFAULTS)
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------- pure parts ----

def test_parse_porcelain_v2_headers_and_entries():
    raw = b"\0".join([
        b"# branch.oid abc",
        b"# branch.head main",
        b"# branch.upstream origin/main",
        b"# branch.ab +3 -1",
        b"1 .M N... 100644 100644 100644 aaa bbb src/app.py",
        b"1 A. N... 000000 100644 100644 000 ccc new.txt",
        b"2 R. N... 100644 100644 100644 ddd eee R100 renamed.txt", b"old.txt",
        b"u UU N... 100644 100644 100644 100644 fff ggg hhh conflict.txt",
        b"? \xe6\x96\x87\xe4\xbb\xb6.txt",
        b"",
    ])
    st = dev_projects.parse_porcelain_v2(raw)
    assert st["branch"] == "main" and not st["detached"] and st["has_upstream"]
    assert (st["ahead"], st["behind"]) == (3, 1)
    assert st["modified"] == 2  # .M worktree change + unmerged
    assert st["staged"] == 2    # A. and R.
    assert st["untracked"] == 1
    assert "文件.txt" in st["paths"] and "renamed.txt" in st["paths"] and "old.txt" not in st["paths"]


def test_parse_porcelain_v2_detached_without_upstream():
    raw = b"# branch.oid abc\0# branch.head (detached)\0"
    st = dev_projects.parse_porcelain_v2(raw)
    assert st["detached"] and st["branch"] is None and not st["has_upstream"]
    assert st["ahead"] == 0 and st["paths"] == []


@pytest.mark.parametrize("url, expect", [
    ("https://github.com/me/proj.git", "https://github.com/me/proj"),
    ("https://github.com/me/proj", "https://github.com/me/proj"),
    ("git@github.com:me/proj.git", "https://github.com/me/proj"),
    ("ssh://git@github.com/me/proj.git", "https://github.com/me/proj"),
    ("https://user@github.com/me/proj.git", "https://github.com/me/proj"),
])
def test_parse_remote_github_shapes(url, expect):
    assert dev_projects.parse_remote(url) == (True, expect)


@pytest.mark.parametrize("url", [None, "", "https://gitlab.com/me/proj.git", "git@bitbucket.org:me/p.git",
                                 "https://notgithub.company.com/x/y"])
def test_parse_remote_non_github(url):
    assert dev_projects.parse_remote(url) == (False, None)


def _info(**over):
    base = {"is_repo": True, "error": None, "ahead": 0, "changes": 0, "remote_url": "https://github.com/a/b",
            "is_github": True, "has_upstream": True, "detached": False,
            "oldest_unpushed_at": None, "newest_change_at": None}
    base.update(over)
    return base


def test_classify_matrix():
    c = dev_projects.classify
    assert c(_info(), CFG, NOW) == ("ok", [])
    assert c(_info(ahead=2, oldest_unpushed_at=_iso(NOW - timedelta(hours=2))), CFG, NOW) == ("warn", ["unpushed"])
    assert c(_info(ahead=2, oldest_unpushed_at=_iso(NOW - timedelta(hours=30))), CFG, NOW) == ("danger", ["unpushed_stale"])
    assert c(_info(changes=3, newest_change_at=_iso(NOW - timedelta(hours=1))), CFG, NOW) == ("ok", ["dirty_fresh"])
    assert c(_info(changes=3, newest_change_at=_iso(NOW - timedelta(hours=48))), CFG, NOW) == ("warn", ["dirty_stale"])
    assert c(_info(remote_url=None, is_github=False, has_upstream=False), CFG, NOW) == ("info", ["no_remote"])
    assert c(_info(remote_url="https://gitlab.com/a/b", is_github=False), CFG, NOW) == ("info", ["not_github"])
    assert c(_info(has_upstream=False), CFG, NOW) == ("info", ["no_upstream"])
    assert c(_info(detached=True), CFG, NOW) == ("info", ["detached"])
    assert c(_info(error="timeout"), CFG, NOW) == ("info", ["git_error"])
    assert c(_info(is_repo=False), CFG, NOW) == ("info", ["not_repo"])
    # thresholds come from config
    tight = {**CFG, "unpushed_danger_hours": 1}
    assert c(_info(ahead=1, oldest_unpushed_at=_iso(NOW - timedelta(hours=2))), tight, NOW)[0] == "danger"


def test_merge_candidates_dedupes_and_filters():
    repos = {"c:/dev/a", "c:/dev/b", "c:/dev/pinned"}
    out = dev_projects.merge_candidates(
        sessions={"C:\\dev\\a\\": "2026-09-20T00:00:00Z", "c:/dev/notrepo": "2026-09-21T00:00:00Z",
                  "c:/dev/ignored": "2026-09-22T00:00:00Z"},
        workspace=["c:/dev/a", "c:/dev/b", "c:/dev/ignored"],
        extra=["c:/dev/manual-missing", "C:/dev/pinned"],
        ignored=["C:\\dev\\ignored"], pinned=["c:/dev/pinned"],
        is_repo=lambda p: p in repos,
    )
    by = {x["path"]: x for x in out}
    assert set(by) == {"c:/dev/a", "c:/dev/b", "c:/dev/pinned", "c:/dev/manual-missing"}
    assert by["c:/dev/a"]["sources"] == ["sessions", "workspace"]
    assert by["c:/dev/a"]["last_active"] == "2026-09-20T00:00:00Z"
    assert by["c:/dev/b"]["last_active"] is None
    assert by["c:/dev/pinned"]["pinned"] and not by["c:/dev/a"]["pinned"]
    assert by["c:/dev/manual-missing"]["is_repo"] is False


def test_repo_root_for_walks_up_to_the_folded_key():
    repos = {"c:/users/x/desktop/token/tokenscope"}
    f = dev_projects.repo_root_for
    assert f(r"C:\Users\x\Desktop\token\tokenscope\frontend\src", "c:/Users/x/Desktop/token",
             is_repo=lambda p: p.lower() in repos) == "c:/Users/x/Desktop/token/tokenscope"
    assert f("c:/Users/x/Desktop/token/docs", "c:/Users/x/Desktop/token", is_repo=lambda p: False) is None
    # never climbs above the folded key even if a parent is a repo
    assert f("c:/Users/x/Desktop/token/docs", "c:/Users/x/Desktop/token",
             is_repo=lambda p: p == "c:/Users/x/Desktop") is None


def test_dev_cfg_fills_defaults_and_normalizes():
    dc = dev_projects.dev_cfg({"dev_projects": {"pinned": ["C:\\X\\Y\\"], "active_days": "7", "dirty_warn_hours": 0}})
    assert dc["pinned"] == ["c:/X/Y"] and dc["extra"] == [] and dc["ignored"] == []
    assert dc["active_days"] == 7 and dc["dirty_warn_hours"] == 1
    assert dc["unpushed_danger_hours"] == 24 and dc["desktop_notify"] is True


# ----------------------------------------------------------- real git repos ----

def _git(path, *args, env=None):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True,
                   env={**os.environ, **(env or {})})


@pytest.fixture()
def repo(tmp_path):
    work, bare = tmp_path / "work", tmp_path / "remote.git"
    work.mkdir()
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True, capture_output=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@example.com")
    _git(work, "config", "user.name", "t")
    _git(work, "config", "commit.gpgsign", "false")
    (work / "a.txt").write_text("1", encoding="utf-8")
    _git(work, "add", ".")
    _git(work, "commit", "-qm", "init")
    _git(work, "remote", "add", "origin", str(bare))
    _git(work, "push", "-qu", "origin", "main")
    # Looks like GitHub for classification; @{upstream} still resolves locally.
    _git(work, "remote", "set-url", "origin", "https://github.com/me/proj.git")
    return work


@needs_git
def test_clean_pushed_repo_is_ok(repo):
    info = dev_projects.inspect_repo(str(repo))
    assert info["error"] is None and info["branch"] == "main" and info["has_upstream"]
    assert info["ahead"] == 0 and info["changes"] == 0
    assert info["is_github"] and info["github_url"] == "https://github.com/me/proj"
    assert info["last_commit_at"] is not None
    assert dev_projects.classify(info, CFG) == ("ok", [])


@needs_git
def test_unpushed_commit_warns_then_danger_when_stale(repo):
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "fresh")
    info = dev_projects.inspect_repo(str(repo))
    assert info["ahead"] == 1 and info["oldest_unpushed_at"] is not None
    assert dev_projects.classify(info, CFG) == ("warn", ["unpushed"])

    old = (datetime.now(timezone.utc) - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _git(repo, "commit", "-q", "--amend", "--no-edit", "--date", old,
         env={"GIT_COMMITTER_DATE": old})
    info = dev_projects.inspect_repo(str(repo))
    level, reasons = dev_projects.classify(info, CFG)
    assert level == "danger" and reasons == ["unpushed_stale"]


@needs_git
def test_oldest_unpushed_is_the_first_of_several(repo):
    old = (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (repo / "b.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "old", "--date", old, env={"GIT_COMMITTER_DATE": old})
    (repo / "c.txt").write_text("3", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "new")
    info = dev_projects.inspect_repo(str(repo))
    assert info["ahead"] == 2
    oldest = datetime.strptime(info["oldest_unpushed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert oldest < datetime.now(timezone.utc) - timedelta(days=4)


@needs_git
def test_dirty_fresh_is_ok_but_stale_warns(repo):
    (repo / "a.txt").write_text("changed", encoding="utf-8")
    (repo / "文件.txt").write_text("new", encoding="utf-8")
    info = dev_projects.inspect_repo(str(repo))
    assert info["modified"] == 1 and info["untracked"] == 1 and info["changes"] == 2
    assert dev_projects.classify(info, CFG) == ("ok", ["dirty_fresh"])

    two_days = time.time() - 2 * 86400
    for name in ("a.txt", "文件.txt"):
        os.utime(repo / name, (two_days, two_days))
    info = dev_projects.inspect_repo(str(repo))
    assert dev_projects.classify(info, CFG) == ("warn", ["dirty_stale"])


@needs_git
def test_remote_variants_and_detached(repo):
    _git(repo, "remote", "set-url", "origin", "https://gitlab.com/me/proj.git")
    info = dev_projects.inspect_repo(str(repo))
    assert not info["is_github"] and dev_projects.classify(info, CFG) == ("info", ["not_github"])

    _git(repo, "remote", "remove", "origin")
    info = dev_projects.inspect_repo(str(repo))
    assert info["remote_url"] is None and not info["has_upstream"]
    assert dev_projects.classify(info, CFG) == ("info", ["no_remote"])

    _git(repo, "checkout", "-q", "--detach")
    info = dev_projects.inspect_repo(str(repo))
    assert info["detached"] and info["branch"] is None
    assert "detached" in dev_projects.classify(info, CFG)[1]


@needs_git
def test_non_repo_directory(tmp_path):
    info = dev_projects.inspect_repo(str(tmp_path))
    assert info["is_repo"] is False and dev_projects.classify(info, CFG) == ("info", ["not_repo"])


def test_git_missing_and_timeout_do_not_raise(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()

    def missing(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(dev_projects, "_run", missing)
    info = dev_projects.inspect_repo(str(tmp_path))
    assert info["error"] == "git_not_found" and dev_projects.git_available is False
    assert dev_projects.classify(info, CFG) == ("info", ["git_error"])

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("git", 1)
    monkeypatch.setattr(dev_projects, "_run", slow)
    assert dev_projects.inspect_repo(str(tmp_path))["error"] == "timeout"
    dev_projects.git_available = True


# ------------------------------------------------------ alerts + notification ----

def _item(path="c:/dev/a", level="danger", reasons=("unpushed_stale",), ahead=2, changes=0):
    return {"path": path, "name": path.rsplit("/", 1)[-1], "level": level, "reasons": list(reasons),
            "ahead": ahead, "changes": changes, "unpushed_age_hours": 30.0, "dirty_age_hours": None,
            "is_repo": True, "error": None, "remote_url": "https://github.com/a/b", "is_github": True,
            "has_upstream": True}


def test_alert_items_from_snapshot(monkeypatch):
    items = [
        _item("c:/dev/a", "danger", ("unpushed_stale",)),
        _item("c:/dev/b", "warn", ("unpushed", "dirty_stale"), ahead=1, changes=4),
        _item("c:/dev/c", "info", ("no_remote",), ahead=0),
        _item("c:/dev/d", "ok", ("dirty_fresh",), ahead=0, changes=1),
    ]
    monkeypatch.setattr(dev_projects, "snapshot", lambda *a, **k: {"items": items})
    out = dev_projects.alert_items()
    kinds = [(a["kind"], a["level"], a["params"]["name"]) for a in out]
    assert kinds == [("git_unpushed", "danger", "a"), ("git_unpushed", "warn", "b"),
                     ("git_dirty", "warn", "b"), ("git_no_remote", "info", "c")]
    assert out[0]["params"]["path"] == "c:/dev/a" and out[0]["params"]["ahead"] == 2


@pytest.fixture()
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENSCOPE_DATA_DIR", str(tmp_path))
    db.reset_conn()
    yield db.get_conn()
    db.reset_conn()


def test_check_and_notify_once_per_day(fresh_db, monkeypatch):
    sent = []
    monkeypatch.setattr(dev_projects, "snapshot",
                        lambda *a, **k: {"items": [_item("c:/dev/a"), _item("c:/dev/ok", "ok", ())]})
    monkeypatch.setattr(dev_projects, "load_config",
                        lambda: {"port": 8787, "dev_projects": {"desktop_notify": True}})

    def fake_toast(title, body, url=None):
        sent.append((title, body, url))
        return True

    r1 = dev_projects.check_and_notify(toast=fake_toast)
    assert r1["sent"] and r1["notified"] == ["c:/dev/a"] and len(sent) == 1
    assert "a" in sent[0][1] and sent[0][2].endswith("/#/dev-projects")
    assert db.get_meta("notify:dev:c:/dev/a") == datetime.now().astimezone().strftime("%Y-%m-%d")

    r2 = dev_projects.check_and_notify(toast=fake_toast)
    assert not r2["sent"] and r2["skipped"] == 1 and len(sent) == 1

    # A failed toast does not consume the day's slot.
    db.set_meta("notify:dev:c:/dev/a", "2000-01-01")
    r3 = dev_projects.check_and_notify(toast=lambda *a: False)
    assert not r3["sent"] and db.get_meta("notify:dev:c:/dev/a") == "2000-01-01"


def test_check_and_notify_respects_toggle_and_never_raises(fresh_db, monkeypatch):
    monkeypatch.setattr(dev_projects, "load_config", lambda: {"dev_projects": {"desktop_notify": False}})
    called = []
    monkeypatch.setattr(dev_projects, "snapshot", lambda *a, **k: called.append(1) or {"items": []})
    assert dev_projects.check_and_notify(toast=lambda *a: True)["sent"] is False and not called

    monkeypatch.setattr(dev_projects, "load_config", lambda: {"dev_projects": {"desktop_notify": True}})

    def boom(*a, **k):
        raise RuntimeError("git exploded")
    monkeypatch.setattr(dev_projects, "snapshot", boom)
    r = dev_projects.check_and_notify(toast=lambda *a: True)
    assert r["sent"] is False and "git exploded" in dev_projects.notify_status["last_error"]


@pytest.mark.skipif(sys.platform != "win32", reason="startfile is Windows-only")
def test_flags_set_on_windows():
    assert dev_projects._FLAGS == subprocess.CREATE_NO_WINDOW
