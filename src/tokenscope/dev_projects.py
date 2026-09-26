"""F26 — local dev-project tracker with GitHub push reminders.

Three layers, kept pure where possible so they test without git:

  discover()      which repos to watch: folded cwds of recent Claude Code
                  sessions ∪ git repos directly under `workspace_roots` ∪
                  manual `extra`, minus `ignored`.
  inspect_repo()  one `git status --porcelain=v2` (plus remote / log probes),
                  all offline — never fetch, never prompt, never write.
  classify()      tiered level (ok | info | warn | danger) from the numbers.

`snapshot()` runs the three with a short TTL cache so /api/alerts and the page
do not shell out on every request; `check_and_notify()` is called from the web
scheduler and fires at most one desktop toast per project per day.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from time import monotonic

from . import queries
from .config import DEFAULT_CONFIG, load_config
from .db import get_meta, locked_conn, set_meta
from .parser import normalize_cwd, project_name
from .projects import Folder

DEFAULTS: dict = DEFAULT_CONFIG["dev_projects"]
SNAPSHOT_TTL = 60.0
STATUS_TIMEOUT = 15.0
PROBE_TIMEOUT = 5.0
MAX_STAT_PATHS = 200
LEVEL_ORDER = {"danger": 0, "warn": 1, "info": 2, "ok": 3}

_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
# Never rewrite .git/index from a status probe (OneDrive would re-sync it),
# never hang on a credential prompt.
_ENV_EXTRA = {"GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0"}

git_available: bool = True


# ------------------------------------------------------------------ config ----

def dev_cfg(cfg: dict | None = None) -> dict:
    """`dev_projects` block with defaults filled in. load_config() merges
    shallowly, so a partial user block would otherwise drop sub-keys."""
    cfg = cfg if cfg is not None else load_config()
    raw = cfg.get("dev_projects")
    out = {**DEFAULTS, **(raw if isinstance(raw, dict) else {})}
    for k in ("extra", "ignored", "pinned"):
        vals = out.get(k) or []
        out[k] = sorted({normalize_cwd(p) for p in vals if isinstance(p, str) and p.strip()})
    for k in ("active_days", "unpushed_danger_hours", "dirty_warn_hours"):
        try:
            out[k] = max(1, int(out[k]))
        except (TypeError, ValueError):
            out[k] = DEFAULTS[k]
    out["desktop_notify"] = bool(out.get("desktop_notify", True))
    return out


# --------------------------------------------------------------- discovery ----

def _is_repo(path: str) -> bool:
    # `.git` is a file in worktrees, so exists() rather than is_dir().
    try:
        return os.path.exists(os.path.join(path, ".git"))
    except OSError:
        return False


def repo_root_for(cwd: str, stop_at: str, is_repo=_is_repo) -> str | None:
    """Nearest ancestor of `cwd` (inclusive, not above `stop_at`) that is a git
    repo. Sessions in `<workspace>/Token消耗量/tokenscope` fold to `Token消耗量`,
    which is a plain folder; the repo is one level down."""
    cur = normalize_cwd(cwd)
    stop = normalize_cwd(stop_at)
    while True:
        if is_repo(cur):
            return cur
        if cur == stop or "/" not in cur.rstrip("/"):
            return None
        cur = cur.rsplit("/", 1)[0]
        if len(cur) < len(stop):
            return None


def _session_candidates(cfg: dict, active_days: int) -> dict[str, str]:
    """{repo path: last activity ISO} for cwds seen recently. The folded
    project key is used when it is a repo; otherwise the raw cwd is walked up
    to the nearest repo under that key."""
    folder = Folder(cfg)
    since = (datetime.now().astimezone() - timedelta(days=active_days)).strftime("%Y-%m-%d")
    start, _ = queries.resolve_range(None, since, None)
    with locked_conn() as conn:
        rows = conn.execute(
            "SELECT project_path p, MAX(ts) last_ts FROM events WHERE ts >= ? GROUP BY project_path",
            (start,),
        ).fetchall()
    out: dict[str, str] = {}
    for r in rows:
        key = folder.fold(r["p"])
        if key == "(unknown)":
            continue
        path = key if _is_repo(key) else repo_root_for(r["p"], key)
        if not path:
            continue
        out[path] = max(out.get(path, ""), r["last_ts"] or "")
    return out


def _workspace_candidates(cfg: dict) -> list[str]:
    found: list[str] = []
    for root in cfg.get("workspace_roots") or []:
        if not isinstance(root, str) or not os.path.isdir(root):
            continue
        try:
            with os.scandir(root) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False) and _is_repo(entry.path):
                            found.append(normalize_cwd(entry.path))
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def merge_candidates(sessions: dict[str, str], workspace: list[str], extra: list[str],
                     ignored: list[str], pinned: list[str],
                     is_repo=_is_repo) -> list[dict]:
    """Pure merge: dedupe by normalized path, union sources, drop ignored,
    drop non-repos unless added manually (so a typo stays visible)."""
    ignored_set = {normalize_cwd(p) for p in ignored}
    pinned_set = {normalize_cwd(p) for p in pinned}
    cands: dict[str, dict] = {}

    def add(path: str, source: str, last_active: str | None = None) -> None:
        key = normalize_cwd(path)
        if key in ignored_set or key == "(unknown)":
            return
        c = cands.setdefault(key, {"path": key, "sources": [], "last_active": None})
        if source not in c["sources"]:
            c["sources"].append(source)
        if last_active and (c["last_active"] is None or last_active > c["last_active"]):
            c["last_active"] = last_active

    for key, last_ts in sessions.items():
        add(key, "sessions", last_ts)
    for p in workspace:
        add(p, "workspace")
    for p in extra:
        add(p, "manual")

    out = []
    for c in cands.values():
        c["is_repo"] = is_repo(c["path"])
        c["pinned"] = c["path"] in pinned_set
        if not c["is_repo"] and "manual" not in c["sources"]:
            continue
        c["name"] = project_name(c["path"])
        out.append(c)
    return out


def discover(cfg: dict | None = None) -> list[dict]:
    cfg = cfg if cfg is not None else load_config()
    dc = dev_cfg(cfg)
    return merge_candidates(_session_candidates(cfg, dc["active_days"]),
                            _workspace_candidates(cfg), dc["extra"], dc["ignored"], dc["pinned"])


# ---------------------------------------------------------------- git probe ----

def _run(path: str, *args: str, timeout: float = PROBE_TIMEOUT) -> tuple[int, bytes]:
    """The only subprocess call in this module (tests monkeypatch it).
    Bytes out: git prints paths as UTF-8 regardless of the console code page."""
    r = subprocess.run(["git", "-C", path, *args], capture_output=True, timeout=timeout,
                       creationflags=_FLAGS, env={**os.environ, **_ENV_EXTRA})
    return r.returncode, r.stdout


def parse_porcelain_v2(raw: bytes) -> dict:
    """Parse `git status --porcelain=v2 --branch -z` output."""
    info = {"branch": None, "detached": False, "has_upstream": False, "ahead": 0, "behind": 0,
            "staged": 0, "modified": 0, "untracked": 0, "paths": []}
    fields = raw.decode("utf-8", "replace").split("\0")
    i = 0
    while i < len(fields):
        f = fields[i]
        i += 1
        if not f:
            continue
        if f.startswith("# "):
            parts = f[2:].split(" ")
            if parts[0] == "branch.head" and len(parts) > 1:
                if parts[1] == "(detached)":
                    info["detached"] = True
                else:
                    info["branch"] = parts[1]
            elif parts[0] == "branch.upstream":
                info["has_upstream"] = True
            elif parts[0] == "branch.ab" and len(parts) >= 3:
                try:
                    info["ahead"] = int(parts[1].lstrip("+"))
                    info["behind"] = int(parts[2].lstrip("-"))
                except ValueError:
                    pass
            continue
        tag = f[0]
        if tag in ("1", "2"):
            parts = f.split(" ", 8 if tag == "1" else 9)
            xy = parts[1] if len(parts) > 1 else ".."
            path = parts[-1]
            if tag == "2":
                i += 1  # rename: the original path is the next NUL field
            if len(xy) == 2:
                if xy[0] != ".":
                    info["staged"] += 1
                if xy[1] != ".":
                    info["modified"] += 1
            info["paths"].append(path)
        elif tag == "u":
            info["modified"] += 1
            info["paths"].append(f.split(" ", 10)[-1])
        elif tag == "?":
            info["untracked"] += 1
            info["paths"].append(f[2:])
        # "!" ignored entries never appear without --ignored
    return info


_GH_RE = re.compile(
    r"^(?:https?://(?:[^@/]+@)?|ssh://(?:[^@/]+@)?|git@)(?:[\w.-]+\.)?github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$",
    re.IGNORECASE,
)


def parse_remote(url: str | None) -> tuple[bool, str | None]:
    """(is_github, browsable https URL)."""
    if not url:
        return False, None
    m = _GH_RE.match(url.strip())
    if not m:
        return False, None
    return True, f"https://github.com/{m.group(1)}/{m.group(2)}"


def _iso(epoch: float | None) -> str | None:
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _epoch_lines(out: bytes) -> list[float]:
    vals = []
    for line in out.decode("utf-8", "replace").split("\n"):
        line = line.strip()
        if line.isdigit():
            vals.append(float(line))
    return vals


def inspect_repo(path: str) -> dict:
    """Offline git facts for one repo. Never raises; errors land in `error`."""
    global git_available
    info: dict = {
        "path": path, "is_repo": True, "error": None,
        "branch": None, "detached": False, "remote_url": None, "is_github": False,
        "github_url": None, "has_upstream": False, "ahead": 0, "behind": 0,
        "modified": 0, "untracked": 0, "staged": 0, "changes": 0,
        "oldest_unpushed_at": None, "last_commit_at": None, "newest_change_at": None,
    }
    if not _is_repo(path):
        info["is_repo"] = False
        return info
    try:
        rc, out = _run(path, "status", "--porcelain=v2", "--branch", "-z",
                       "--untracked-files=normal", timeout=STATUS_TIMEOUT)
        if rc != 0:
            info["error"] = f"git status exit {rc}"
            return info
        st = parse_porcelain_v2(out)
        for k in ("branch", "detached", "has_upstream", "ahead", "behind", "staged", "modified", "untracked"):
            info[k] = st[k]
        info["changes"] = st["staged"] + st["modified"] + st["untracked"]

        rc, out = _run(path, "remote", "get-url", "origin")
        url = out.decode("utf-8", "replace").strip() if rc == 0 else ""
        if not url:
            rc, out = _run(path, "remote")
            names = [n for n in out.decode("utf-8", "replace").split() if n] if rc == 0 else []
            if names:
                rc, out = _run(path, "remote", "get-url", names[0])
                url = out.decode("utf-8", "replace").strip() if rc == 0 else ""
        info["remote_url"] = url or None
        info["is_github"], info["github_url"] = parse_remote(url)

        rc, out = _run(path, "log", "-1", "--format=%ct", "HEAD")
        epochs = _epoch_lines(out) if rc == 0 else []
        info["last_commit_at"] = _iso(epochs[0]) if epochs else None

        if info["ahead"] > 0 and info["has_upstream"]:
            rc, out = _run(path, "log", "--format=%ct", "@{upstream}..HEAD")
            epochs = _epoch_lines(out) if rc == 0 else []
            # newest first, so the last line is the oldest unpushed commit
            info["oldest_unpushed_at"] = _iso(epochs[-1]) if epochs else None

        newest = None
        for rel in st["paths"][:MAX_STAT_PATHS]:
            try:
                m = os.stat(os.path.join(path, rel)).st_mtime
            except OSError:
                continue
            newest = m if newest is None or m > newest else newest
        if info["changes"]:
            info["newest_change_at"] = _iso(newest) if newest is not None else info["last_commit_at"]
        git_available = True
    except FileNotFoundError:
        git_available = False
        info["error"] = "git_not_found"
    except subprocess.TimeoutExpired:
        info["error"] = "timeout"
    except Exception as e:  # noqa: BLE001 — a probe must never take the page down
        info["error"] = f"{type(e).__name__}: {e}"
    return info


# ------------------------------------------------------------ classification ----

def _hours_since(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        then = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(0.0, (now - then).total_seconds() / 3600)


def classify(info: dict, cfg: dict, now: datetime | None = None) -> tuple[str, list[str]]:
    """Pure: (level, reasons). `cfg` is a dev_cfg() block."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    if not info.get("is_repo"):
        return "info", ["not_repo"]
    if info.get("error"):
        return "info", ["git_error"]

    unpushed_h = _hours_since(info.get("oldest_unpushed_at"), now)
    if info.get("ahead", 0) > 0:
        stale = unpushed_h is not None and unpushed_h >= cfg["unpushed_danger_hours"]
        reasons.append("unpushed_stale" if stale else "unpushed")

    dirty_h = _hours_since(info.get("newest_change_at"), now)
    if info.get("changes", 0) > 0:
        stale = dirty_h is not None and dirty_h >= cfg["dirty_warn_hours"]
        reasons.append("dirty_stale" if stale else "dirty_fresh")

    if not info.get("remote_url"):
        reasons.append("no_remote")
    elif not info.get("is_github"):
        reasons.append("not_github")
    elif not info.get("has_upstream"):
        reasons.append("no_upstream")
    if info.get("detached"):
        reasons.append("detached")

    rs = set(reasons)
    if "unpushed_stale" in rs:
        level = "danger"
    elif rs & {"unpushed", "dirty_stale"}:
        level = "warn"
    elif rs & {"no_remote", "not_github", "no_upstream", "detached"}:
        level = "info"
    else:
        level = "ok"
    return level, reasons


# ---------------------------------------------------------------- snapshot ----

_cache: dict = {"at": 0.0, "data": None}
_refresh_lock = threading.Lock()
notify_status: dict = {"last_run": None, "last_sent": None, "last_error": None}


def _build() -> dict:
    cfg = load_config()
    dc = dev_cfg(cfg)
    cands = discover(cfg)
    now = datetime.now(timezone.utc)
    if cands:
        with ThreadPoolExecutor(max_workers=min(8, len(cands))) as ex:
            infos = list(ex.map(lambda c: inspect_repo(c["path"]), cands))
    else:
        infos = []
    items = []
    for c, info in zip(cands, infos):
        level, reasons = classify(info, dc, now)
        item = {**info, "name": c["name"], "sources": c["sources"], "pinned": c["pinned"],
                "last_active": c["last_active"], "level": level, "reasons": reasons}
        h = _hours_since(info.get("oldest_unpushed_at"), now)
        item["unpushed_age_hours"] = round(h, 1) if h is not None else None
        h = _hours_since(info.get("newest_change_at"), now)
        item["dirty_age_hours"] = round(h, 1) if h is not None else None
        items.append(item)
    # Stable passes: name, then most recently active first (ISO strings sort
    # lexicographically; never-seen repos last), then pinned / severity on top.
    items.sort(key=lambda x: x["name"].lower())
    items.sort(key=lambda x: x["last_active"] or "", reverse=True)
    items.sort(key=lambda x: (not x["pinned"], LEVEL_ORDER[x["level"]]))
    summary = {
        "tracked": len(items),
        "needs_push": sum(1 for x in items if x["ahead"] > 0),
        "dirty": sum(1 for x in items if x["changes"] > 0),
        "no_remote": sum(1 for x in items if x["is_repo"] and not x["error"]
                         and (not x["remote_url"] or not x["is_github"] or not x["has_upstream"])),
        "ok": sum(1 for x in items if x["level"] == "ok"),
    }
    return {"items": items, "summary": summary, "checked_at": _iso(now.timestamp()),
            "git_available": git_available, "config": dc, "notify": dict(notify_status)}


def snapshot(force: bool = False, max_age: float = SNAPSHOT_TTL) -> dict:
    def fresh() -> bool:
        return _cache["data"] is not None and monotonic() - _cache["at"] < max_age
    if not force and fresh():
        return _cache["data"]
    with _refresh_lock:
        if not force and fresh():
            return _cache["data"]
        data = _build()
        _cache["data"], _cache["at"] = data, monotonic()
        return data


def invalidate() -> None:
    _cache["at"] = 0.0


# ------------------------------------------------------------------ alerts ----

def alert_items(project: str | None = None) -> list[dict]:
    """Alert entries for insights.alerts(): ok / fresh-dirty projects say nothing."""
    snap = snapshot()
    items = snap["items"]
    if project:
        key = Folder().fold(project)
        items = [x for x in items if x["path"] == key]
    out = []
    for x in items:
        rs = set(x["reasons"])
        base = {"name": x["name"], "path": x["path"]}
        if rs & {"unpushed", "unpushed_stale"}:
            out.append({"kind": "git_unpushed", "level": "danger" if "unpushed_stale" in rs else "warn",
                        "params": {**base, "ahead": x["ahead"], "hours": round(x["unpushed_age_hours"] or 0)}})
        if "dirty_stale" in rs:
            out.append({"kind": "git_dirty", "level": "warn",
                        "params": {**base, "changes": x["changes"], "hours": round(x["dirty_age_hours"] or 0)}})
        for reason in ("no_remote", "not_github", "no_upstream"):
            if reason in rs:
                out.append({"kind": "git_no_remote", "level": "info", "params": {**base, "reason": reason}})
                break
    return out


# ------------------------------------------------------------ notification ----

def _notify_key(path: str) -> str:
    return f"notify:dev:{path}"


def check_and_notify(toast=None, now: datetime | None = None) -> dict:
    """Scheduler hook: one desktop toast for every warn/danger project not yet
    notified today. Never raises."""
    from . import notify as _notify
    toast = toast or _notify.toast
    now = now or datetime.now().astimezone()
    today = now.strftime("%Y-%m-%d")
    result = {"sent": False, "notified": [], "skipped": 0}
    notify_status["last_run"] = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    try:
        cfg = load_config()
        dc = dev_cfg(cfg)
        if not dc["desktop_notify"]:
            return result
        snap = snapshot(force=True)
        due = [x for x in snap["items"] if x["level"] in ("warn", "danger")]
        pending = []
        for x in due:
            if get_meta(_notify_key(x["path"])) == today:
                result["skipped"] += 1
            else:
                pending.append(x)
        if not pending:
            return result
        pending.sort(key=lambda x: LEVEL_ORDER[x["level"]])
        lines = []
        for x in pending[:3]:
            bits = []
            if x["ahead"]:
                bits.append(f"{x['ahead']} 个提交未推送")
            if "dirty_stale" in x["reasons"]:
                bits.append(f"{x['changes']} 处改动未提交")
            lines.append(f"{x['name']}: {' · '.join(bits) or x['level']}")
        if len(pending) > 3:
            lines.append(f"…还有 {len(pending) - 3} 个项目")
        url = f"http://127.0.0.1:{cfg.get('port', 8787)}/#/dev-projects"
        sent = bool(toast(f"TokenScope · {len(pending)} 个项目待推送 GitHub", "\n".join(lines), url))
        result["sent"] = sent
        if sent:
            for x in pending:
                set_meta(_notify_key(x["path"]), today)
                result["notified"].append(x["path"])
            notify_status["last_sent"] = notify_status["last_run"]
        notify_status["last_error"] = None if sent else "toast_failed"
    except Exception as e:  # noqa: BLE001
        notify_status["last_error"] = f"{type(e).__name__}: {e}"
    return result
