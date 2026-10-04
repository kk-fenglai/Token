"""F27 — one-click "upload to GitHub" for a tracked dev project.

  plan(path)     what a publish would do, read-only: the files `git add -A`
                 would pick up (with secret / large-file warnings), the
                 commits that would leave the machine, and which action
                 applies — a plain push, a first push that sets the upstream,
                 or a new GitHub repo via `gh repo create --push`.
  publish(...)   re-plans server-side (never trusts the client's view), then
                 runs: optional `git add -A` + `git commit`, then the push.
                 Every step's command and output is returned so the page can
                 show exactly what happened.

Unlike dev_projects this module *does* write to the repo and the network, so
it only ever runs on an explicit click. Arguments go to git / gh as argv
lists, never through a shell. No force-push, no pull, no rebase: a rejected
push is reported, not "fixed".
"""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
import subprocess
import threading
from time import monotonic

from . import dev_projects
from .parser import project_name

PUSH_TIMEOUT = 180.0
COMMIT_TIMEOUT = 120.0
MAX_FILES = 300
MAX_COMMITS = 20
MAX_OUTPUT = 4000
LARGE_FILE_BYTES = 50 * 1024 * 1024  # GitHub warns at 50 MB, rejects at 100 MB
GH_CACHE_TTL = 300.0

# Basename globs for files that almost never belong in a repo.
SENSITIVE_GLOBS = (
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.keystore", "*.jks",
    "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*", "credentials*.json",
    "*service-account*.json", "secrets.*", ".npmrc", ".pypirc", ".netrc",
)
SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist")

_REPO_NAME_RE = re.compile(r"^(?:[A-Za-z0-9-]{1,39}/)?[A-Za-z0-9._-]{1,100}$")
_CRED_RE = re.compile(r"(://)[^@/\s]+@")

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_gh_cache: dict = {"at": 0.0, "data": None}


class PublishError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------- plumbing ----

def _redact(text: str) -> str:
    return _CRED_RE.sub(r"\1***@", text)


def _run(cmd: list[str], cwd: str, timeout: float) -> tuple[int, str, str]:
    """The only subprocess call in this module (tests monkeypatch it)."""
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, timeout=timeout,
                       creationflags=dev_projects._FLAGS,
                       env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    return (r.returncode, r.stdout.decode("utf-8", "replace"),
            r.stderr.decode("utf-8", "replace"))


def _git(path: str, *args: str, timeout: float = dev_projects.PROBE_TIMEOUT) -> tuple[int, str, str]:
    return _run(["git", "-C", path, *args], path, timeout)


def gh_path() -> str | None:
    found = shutil.which("gh")
    if found:
        return found
    # A server started from a shortcut may not see a PATH entry added later.
    for base in (os.environ.get("ProgramFiles"), os.environ.get("LOCALAPPDATA")):
        if base:
            cand = os.path.join(base, "GitHub CLI", "gh.exe")
            if os.path.isfile(cand):
                return cand
    return None


def gh_status(force: bool = False) -> dict:
    """{available, user}: is `gh` installed and logged in to github.com."""
    if not force and _gh_cache["data"] is not None and monotonic() - _gh_cache["at"] < GH_CACHE_TTL:
        return _gh_cache["data"]
    exe = gh_path()
    data = {"available": exe is not None, "user": None}
    if exe:
        try:
            rc, out, err = _run([exe, "auth", "status", "--hostname", "github.com"],
                                os.getcwd(), dev_projects.PROBE_TIMEOUT)
            text = out + "\n" + err
            # gh >= 2.40: "Logged in to github.com account NAME"; older: "... as NAME"
            m = re.search(r"Logged in to github\.com (?:account|as) ([A-Za-z0-9-]+)", text)
            if rc == 0 and m:
                data["user"] = m.group(1)
        except (OSError, subprocess.TimeoutExpired):
            pass
    _gh_cache["data"], _gh_cache["at"] = data, monotonic()
    return data


def _lock_for(path: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(path, threading.Lock())


# ------------------------------------------------------------ pure helpers ----

def parse_porcelain_v1(raw: str) -> list[dict]:
    """`git status --porcelain=v1 -z` → [{path, status}]; status is the XY pair
    with spaces as '.', e.g. '??', '.M', 'A.'."""
    out = []
    fields = raw.split("\0")
    i = 0
    while i < len(fields):
        f = fields[i]
        i += 1
        if len(f) < 4:
            continue
        xy, path = f[:2], f[3:]
        if xy[0] in "RC":
            i += 1  # the original path follows as its own field
        out.append({"path": path, "status": xy.replace(" ", ".")})
    return out


def is_sensitive(path: str) -> bool:
    base = path.rstrip("/").rsplit("/", 1)[-1].lower()
    if base.startswith(".env") and base.endswith(SAFE_ENV_SUFFIXES):
        return False
    return any(fnmatch.fnmatchcase(base, g) for g in SENSITIVE_GLOBS)


def suggest_repo_name(path: str) -> str:
    """GitHub repo names allow [A-Za-z0-9._-]; `Token消耗量` → `Token`."""
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", project_name(path)).strip("-.")
    return name[:100] or "my-project"


def default_message(files: list[dict]) -> str:
    if not files:
        return ""
    names = [f["path"].rstrip("/").rsplit("/", 1)[-1] for f in files[:3]]
    head = ", ".join(names)
    more = len(files) - len(names)
    return f"Update {head}" + (f" and {more} more" if more > 0 else "")


def valid_repo_name(name: str) -> bool:
    return bool(_REPO_NAME_RE.match(name)) and name.rsplit("/", 1)[-1] not in (".", "..")


# -------------------------------------------------------------------- plan ----

def _tracked_item(path: str) -> dict:
    """Only projects in the current snapshot can be published — the endpoint
    cannot be pointed at an arbitrary directory."""
    snap = dev_projects.snapshot()
    item = next((x for x in snap["items"] if x["path"] == path), None)
    if item is None:
        raise PublishError("not_tracked")
    return item


def _remote_name(path: str) -> str | None:
    rc, out, _ = _git(path, "remote")
    names = [n for n in out.split() if n] if rc == 0 else []
    if not names:
        return None
    return "origin" if "origin" in names else names[0]


def plan(path: str) -> dict:
    item = _tracked_item(path)
    fs_path = os.path.normpath(item["path"])
    info = dev_projects.inspect_repo(item["path"])  # fresh, not the 60 s cache
    result = {
        "path": item["path"], "name": item["name"], "branch": info["branch"],
        "detached": info["detached"], "remote": None, "remote_url": info["remote_url"],
        "is_github": info["is_github"], "github_url": info["github_url"],
        "has_upstream": info["has_upstream"], "ahead": info["ahead"], "behind": info["behind"],
        "files": [], "file_count": 0, "sensitive": [], "large": [], "commits": [],
        "has_commits": False, "action": "blocked", "blocked_reason": None, "gh": None,
        "default_message": "", "default_repo_name": suggest_repo_name(item["path"]),
    }
    if not info["is_repo"]:
        result["blocked_reason"] = "not_repo"
        return result
    if info["error"]:
        result["blocked_reason"] = "git_error"
        return result

    rc, out, _ = _git(fs_path, "status", "--porcelain=v1", "-z", "--untracked-files=all",
                      timeout=dev_projects.STATUS_TIMEOUT)
    files = parse_porcelain_v1(out) if rc == 0 else []
    result["file_count"] = len(files)
    result["files"] = files[:MAX_FILES]
    result["sensitive"] = [f["path"] for f in files if is_sensitive(f["path"])][:50]
    large = []
    for f in files[:2000]:
        if "D" in f["status"]:
            continue
        try:
            if os.path.getsize(os.path.join(fs_path, f["path"])) >= LARGE_FILE_BYTES:
                large.append(f["path"])
        except OSError:
            continue
    result["large"] = large[:50]
    result["default_message"] = default_message(files)

    rc, _, _ = _git(fs_path, "rev-parse", "--verify", "-q", "HEAD")
    result["has_commits"] = rc == 0
    result["remote"] = _remote_name(fs_path)

    if result["has_commits"]:
        # Without an upstream, "what would leave the machine" is whatever no
        # remote-tracking branch already has (everything, for a new repo).
        rng = (["@{upstream}..HEAD"] if info["has_upstream"]
               else ["-n", str(MAX_COMMITS), "HEAD", "--not", "--remotes"])
        rc, out, _ = _git(fs_path, "log", "--format=%h%x09%s", *rng)
        commits = []
        for line in out.splitlines() if rc == 0 else []:
            sha, _, subject = line.partition("\t")
            if sha:
                commits.append({"sha": sha, "subject": subject})
        result["commits"] = commits[:MAX_COMMITS]

    if info["detached"]:
        result["blocked_reason"] = "detached"
    elif not result["has_commits"] and not files:
        result["blocked_reason"] = "empty_repo"
    elif result["remote"] is None:
        gh = gh_status()
        result["gh"] = gh
        if not gh["available"]:
            result["blocked_reason"] = "gh_missing"
        elif not gh["user"]:
            result["blocked_reason"] = "gh_logged_out"
        else:
            result["action"] = "create_repo"
    elif not info["has_upstream"]:
        result["action"] = "push_upstream"
    elif info["ahead"] > 0 or files:
        result["action"] = "push"
    else:
        result["action"] = "nothing"
    return result


# ----------------------------------------------------------------- publish ----

def _classify_failure(text: str) -> str:
    t = text.lower()
    if "please tell me who you are" in t or "user.email" in t:
        return "identity"
    if "non-fast-forward" in t or "fetch first" in t or "[rejected]" in t:
        return "rejected"
    if ("authentication failed" in t or "could not read username" in t
            or "permission denied" in t or "returned error: 403" in t):
        return "auth"
    if "name already exists" in t:
        return "repo_exists"
    if "gh013" in t or "push protection" in t or "exceeds github's file size limit" in t:
        return "rejected_by_github"
    if "nothing to commit" in t:
        return "nothing_to_commit"
    return "failed"


def publish(path: str, *, commit: bool = True, message: str = "",
            repo_name: str | None = None, private: bool = True) -> dict:
    lock = _lock_for(path)
    if not lock.acquire(blocking=False):
        raise PublishError("busy")
    try:
        p = plan(path)
        if p["action"] == "blocked":
            raise PublishError(p["blocked_reason"] or "blocked")
        fs_path = os.path.normpath(p["path"])
        steps: list[dict] = []

        def step(label: str, cmd: list[str], timeout: float) -> tuple[bool, str]:
            try:
                rc, out, err = _run(cmd, fs_path, timeout)
            except subprocess.TimeoutExpired:
                rc, out, err = -1, "", "timeout"
            except FileNotFoundError:
                rc, out, err = -1, "", f"{cmd[0]} not found"
            text = _redact((out + ("\n" if out and err else "") + err).strip())[-MAX_OUTPUT:]
            args = cmd[3:] if cmd[1:3] == ["-C", fs_path] else cmd[1:]
            shown = [os.path.splitext(os.path.basename(cmd[0]))[0],
                     *("." if a == fs_path else a for a in args)]
            steps.append({"step": label, "cmd": " ".join(shown), "ok": rc == 0, "output": text})
            return rc == 0, text

        committed = False
        if commit and p["file_count"] > 0:
            msg = message.strip() or p["default_message"] or "Update"
            if len(msg) > 5000:
                raise PublishError("bad_message")
            ok, text = step("add", ["git", "-C", fs_path, "add", "-A"], COMMIT_TIMEOUT)
            if not ok:
                return _done(p, steps, False, _classify_failure(text))
            ok, text = step("commit", ["git", "-C", fs_path, "commit", "-q", "-m", msg], COMMIT_TIMEOUT)
            if not ok:
                return _done(p, steps, False, _classify_failure(text))
            committed = True

        if p["action"] == "create_repo":
            name = (repo_name or p["default_repo_name"]).strip()
            if not valid_repo_name(name):
                raise PublishError("bad_repo_name")
            if not p["has_commits"] and not committed:
                raise PublishError("empty_repo")
            exe = gh_path() or "gh"
            ok, text = step("create", [exe, "repo", "create", name,
                                       "--private" if private else "--public",
                                       "--source", fs_path, "--remote", "origin", "--push"],
                            PUSH_TIMEOUT)
        elif p["action"] == "push_upstream":
            if not p["has_commits"] and not committed:
                raise PublishError("empty_repo")
            ok, text = step("push", ["git", "-C", fs_path, "push", "-u", p["remote"], p["branch"]],
                            PUSH_TIMEOUT)
        elif p["ahead"] > 0 or committed:
            ok, text = step("push", ["git", "-C", fs_path, "push"], PUSH_TIMEOUT)
        else:
            raise PublishError("nothing_to_push")
        return _done(p, steps, ok, None if ok else _classify_failure(text))
    finally:
        lock.release()


def _done(p: dict, steps: list[dict], ok: bool, error: str | None) -> dict:
    dev_projects.invalidate()
    info = dev_projects.inspect_repo(p["path"])
    return {"ok": ok, "error": error, "steps": steps,
            "github_url": info.get("github_url") or p["github_url"],
            "ahead": info.get("ahead", 0), "changes": info.get("changes", 0)}
