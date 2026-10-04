"""Branches and worktrees of a tracked dev project, for the assistant.

  worktrees(path)             every worktree of the repo: branch, dirty file
                              count, ahead / behind the base branch
  branches(path, base)        local branches with upstream tracking, how far
                              each is ahead of (unmerged into) / behind base,
                              and which worktree has it checked out
  compare(path, base, head)   the commits on head that base lacks (unmerged)
                              and vice versa, merge base, diff stat, and
                              optionally the diff text
  create_worktree / remove_worktree / delete_branch / prune_worktrees
                              the narrow write operations

Safety rules, on top of dev_projects' "path must be tracked": every ref the
model names is resolved with `rev-parse --verify` to a SHA before it reaches
another git command, so nothing can be smuggled in as an option; branch names
go through `check-ref-format --branch`. Nothing here force-deletes: a worktree
with uncommitted or untracked files is refused, and branches are deleted with
`git branch -d`, which git itself refuses for unmerged work. No merge, rebase,
reset, checkout or network access.
"""
from __future__ import annotations

import os
import re

from . import dev_projects, git_publish
from .dev_project_detail import NotTracked, tracked_item

MAX_BRANCHES = 60
MAX_COMMITS = 50
MAX_FILES = 200
WRITE_TIMEOUT = 120.0


class BranchError(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


# --------------------------------------------------------------- plumbing ----

def _git(path: str, *args: str, timeout: float = dev_projects.STATUS_TIMEOUT) -> tuple[int, str, str]:
    return git_publish._git(path, *args, timeout=timeout)


def _key(p: str) -> str:
    """Comparable form of a path as git or the snapshot spells it."""
    return os.path.normcase(os.path.normpath(p.replace("/", os.sep)))


def _repo(path: str) -> str:
    """The filesystem path of a tracked project, or BranchError."""
    try:
        tracked_item(path)
    except NotTracked:
        raise BranchError("not_tracked") from None
    fs = os.path.normpath(path)
    if _git(fs, "rev-parse", "--git-dir")[0] != 0:
        raise BranchError("not_a_repo")
    return fs


def _resolve(fs: str, ref: str) -> str:
    """SHA of a commit-ish, refusing anything that looks like an option."""
    ref = (ref or "").strip()
    if not ref or ref.startswith("-") or len(ref) > 250 or any(c in ref for c in "\0\n\r"):
        raise BranchError("bad_ref", ref[:80])
    rc, out, _ = _git(fs, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{ref}^{{commit}}")
    if rc != 0 or not out.strip():
        raise BranchError("unknown_ref", ref)
    return out.strip()


def _valid_branch(fs: str, name: str) -> str:
    name = (name or "").strip()
    if not name or name.startswith("-") or len(name) > 200:
        raise BranchError("bad_branch_name", name[:80])
    rc, out, _ = _git(fs, "check-ref-format", "--branch", name)
    if rc != 0:
        raise BranchError("bad_branch_name", name)
    return out.strip() or name


def _branch_exists(fs: str, name: str) -> bool:
    return _git(fs, "show-ref", "--verify", "--quiet", f"refs/heads/{name}")[0] == 0


def default_base(fs: str) -> str | None:
    """origin/HEAD's target, else a local main / master, else HEAD's branch."""
    rc, out, _ = _git(fs, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if rc == 0 and out.strip():
        local = out.strip().split("/", 1)[-1]
        return local if _branch_exists(fs, local) else out.strip()
    for name in ("main", "master"):
        if _branch_exists(fs, name):
            return name
    rc, out, _ = _git(fs, "symbolic-ref", "--quiet", "--short", "HEAD")
    return out.strip() if rc == 0 and out.strip() else None


def _ahead_behind(fs: str, base_sha: str, head_sha: str) -> tuple[int, int]:
    """(commits on head not in base, commits on base not in head)."""
    rc, out, _ = _git(fs, "rev-list", "--left-right", "--count", f"{base_sha}...{head_sha}")
    parts = out.split() if rc == 0 else []
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        return 0, 0
    return int(parts[1]), int(parts[0])


# -------------------------------------------------------------- worktrees ----

def parse_worktree_list(raw: str) -> list[dict]:
    """`git worktree list --porcelain` → one dict per worktree, main first."""
    items: list[dict] = []
    cur: dict | None = None
    for line in raw.splitlines():
        if not line.strip():
            cur = None
            continue
        word, _, rest = line.partition(" ")
        if word == "worktree":
            cur = {"path": rest, "head": None, "branch": None, "detached": False, "bare": False,
                   "locked": None, "prunable": None}
            items.append(cur)
        elif cur is None:
            continue
        elif word == "HEAD":
            cur["head"] = rest
        elif word == "branch":
            cur["branch"] = rest.removeprefix("refs/heads/")
        elif word in ("detached", "bare"):
            cur[word] = True
        elif word in ("locked", "prunable"):
            cur[word] = rest or True
    for i, w in enumerate(items):
        w["main"] = i == 0
    return items


def _list(fs: str) -> list[dict]:
    rc, out, err = _git(fs, "worktree", "list", "--porcelain")
    if rc != 0:
        raise BranchError("git_failed", err.strip()[:300])
    return parse_worktree_list(out)


def _dirty(wt: str) -> list[str] | None:
    """Changed + untracked files of one worktree, or None if unreadable."""
    rc, out, _ = _git(wt, "status", "--porcelain=v1", "-z", "--untracked-files=normal")
    if rc != 0:
        return None
    return [f["path"] for f in git_publish.parse_porcelain_v1(out)]


def worktrees(path: str, base: str | None = None) -> dict:
    fs = _repo(path)
    base = base or default_base(fs)
    base_sha = _resolve(fs, base) if base else None
    items = []
    for w in _list(fs):
        exists = os.path.isdir(w["path"])
        dirty = _dirty(w["path"]) if exists and not w["bare"] else None
        ahead = behind = None
        if base_sha and w["head"]:
            ahead, behind = _ahead_behind(fs, base_sha, w["head"])
        items.append({**w, "exists": exists,
                      "dirty_files": len(dirty) if dirty is not None else None,
                      "dirty_sample": (dirty or [])[:10],
                      "ahead_of_base": ahead, "behind_base": behind})
    return {"path": path, "base": base, "worktrees": items}


# --------------------------------------------------------------- branches ----

def branches(path: str, base: str | None = None) -> dict:
    fs = _repo(path)
    base = base or default_base(fs)
    base_sha = _resolve(fs, base) if base else None
    checked_out = {w["branch"]: w["path"] for w in _list(fs) if w["branch"]}
    rc, out, err = _git(fs, "for-each-ref", "refs/heads", "--sort=-committerdate",
                        "--format=%(refname:short)%1f%(objectname)%1f%(upstream:short)%1f"
                        "%(upstream:track)%1f%(committerdate:unix)%1f%(subject)")
    if rc != 0:
        raise BranchError("git_failed", err.strip()[:300])
    items = []
    lines = out.splitlines()
    for line in lines[:MAX_BRANCHES]:
        parts = line.split("\x1f")
        if len(parts) != 6:
            continue
        name, sha, upstream, track, epoch, subject = parts
        up_ahead = re.search(r"ahead (\d+)", track)
        up_behind = re.search(r"behind (\d+)", track)
        item = {
            "name": name, "sha": sha[:10], "last_commit_at": dev_projects._iso(float(epoch)) if epoch.isdigit() else None,
            "last_subject": subject[:200], "upstream": upstream or None, "upstream_gone": "gone" in track,
            "unpushed": int(up_ahead.group(1)) if up_ahead else 0,
            "behind_upstream": int(up_behind.group(1)) if up_behind else 0,
            "worktree": checked_out.get(name),
        }
        if base_sha:
            ahead, behind = _ahead_behind(fs, base_sha, sha)
            item.update(unmerged_commits=ahead, behind_base=behind, merged_into_base=ahead == 0)
        items.append(item)
    return {"path": path, "base": base, "branches": items, "total": len(lines),
            "truncated": len(lines) > MAX_BRANCHES}


def _log(fs: str, rng: str, limit: int) -> list[dict]:
    rc, out, _ = _git(fs, "log", f"-{limit}", "--format=%h%x1f%ct%x1f%an%x1f%s", rng)
    commits = []
    for line in out.splitlines() if rc == 0 else []:
        p = line.split("\x1f")
        if len(p) == 4 and p[1].isdigit():
            commits.append({"sha": p[0], "at": dev_projects._iso(float(p[1])), "author": p[2], "subject": p[3][:200]})
    return commits


def compare(path: str, base: str | None, head: str, include_diff: bool = False, max_chars: int = 12000) -> dict:
    fs = _repo(path)
    base = base or default_base(fs)
    if not base:
        raise BranchError("no_base")
    base_sha, head_sha = _resolve(fs, base), _resolve(fs, head)
    ahead, behind = _ahead_behind(fs, base_sha, head_sha)
    rc, mb, _ = _git(fs, "merge-base", base_sha, head_sha)
    merge_base = mb.strip() if rc == 0 and mb.strip() else None
    out: dict = {
        "path": path, "base": base, "head": head, "merge_base": merge_base[:10] if merge_base else None,
        "unmerged_count": ahead, "behind_count": behind,
        "unmerged_commits": _log(fs, f"{base_sha}..{head_sha}", MAX_COMMITS),
        "missing_from_head": _log(fs, f"{head_sha}..{base_sha}", 20),
        "files": [], "stat": "", "diff": None, "diff_truncated": False, "sensitive_skipped": [],
    }
    if not merge_base:
        return out  # unrelated histories: no three-dot diff
    # Three-dot: what head changed since it forked, i.e. what a merge would bring in.
    rng = f"{merge_base}..{head_sha}"
    rc, names, _ = _git(fs, "diff", "--name-status", "-z", rng)
    tokens = names.split("\0") if rc == 0 else []
    i = 0
    while i < len(tokens) - 1:
        status = tokens[i]
        if status[:1] in ("R", "C") and i + 2 < len(tokens):
            out["files"].append({"status": status[:1], "path": tokens[i + 2], "from": tokens[i + 1]})
            i += 3
        else:
            out["files"].append({"status": status[:1], "path": tokens[i + 1]})
            i += 2
    out["file_count"] = len(out["files"])
    out["files"] = out["files"][:MAX_FILES]
    _, stat, _ = _git(fs, "diff", "--stat", rng)
    out["stat"] = stat.strip()[-4000:]
    if include_diff and out["files"]:
        paths = [f["path"] for f in out["files"]]
        safe = [p for p in paths if not git_publish.is_sensitive(p)]
        out["sensitive_skipped"] = [p for p in paths if git_publish.is_sensitive(p)][:50]
        if safe:
            max_chars = max(1000, min(30000, int(max_chars)))
            _, diff, _ = _git(fs, "diff", "--no-color", rng, "--", *safe, timeout=30)
            out["diff"], out["diff_truncated"] = diff[:max_chars], len(diff) > max_chars
    return out


# ----------------------------------------------------------------- writes ----

def _step(fs: str, *args: str) -> dict:
    rc, out, err = _git(fs, *args, timeout=WRITE_TIMEOUT)
    return {"cmd": "git " + " ".join(args), "ok": rc == 0,
            "output": git_publish._redact((out + err).strip())[-2000:]}


def _default_dest(main_wt: str, branch: str) -> str:
    """`<repo>.worktrees/<branch>` next to the main worktree, the layout git's
    own docs suggest — outside the repo, so nothing needs ignoring."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", branch).strip("-.") or "worktree"
    parent, name = os.path.split(os.path.normpath(main_wt))
    return os.path.join(parent, f"{name}.worktrees", safe)


def create_worktree(path: str, branch: str, base: str | None = None, dest: str | None = None) -> dict:
    fs = _repo(path)
    with git_publish._lock_for(path):
        wts = _list(fs)
        branch = _valid_branch(fs, branch)
        if any(w["branch"] == branch for w in wts):
            raise BranchError("branch_checked_out", next(w["path"] for w in wts if w["branch"] == branch))
        target = os.path.normpath(dest.strip().strip('"')) if dest else _default_dest(wts[0]["path"], branch)
        if not os.path.isabs(target):
            raise BranchError("dest_not_absolute", target)
        if os.path.exists(target) and (not os.path.isdir(target) or os.listdir(target)):
            raise BranchError("dest_exists", target)
        existing = _branch_exists(fs, branch)
        if existing:
            args = ["worktree", "add", "--", target, branch]
        else:
            start = _resolve(fs, base or default_base(fs) or "HEAD")
            args = ["worktree", "add", "-b", branch, "--", target, start]
        step = _step(fs, *args)
    dev_projects.invalidate()
    if not step["ok"]:
        return {"ok": False, "error": "git_failed", "steps": [step]}
    return {"ok": True, "worktree": target.replace("\\", "/"), "branch": branch,
            "new_branch": not existing, "base": None if existing else (base or default_base(fs)), "steps": [step]}


def remove_worktree(path: str, worktree: str, delete_branch: bool = False) -> dict:
    fs = _repo(path)
    with git_publish._lock_for(path):
        wts = _list(fs)
        match = next((w for w in wts if _key(w["path"]) == _key(worktree.strip().strip('"'))), None)
        if match is None:
            raise BranchError("unknown_worktree", worktree)
        if match["main"]:
            raise BranchError("main_worktree")
        if match["locked"]:
            raise BranchError("locked", str(match["locked"]))
        main = wts[0]["path"]
        steps = []
        if os.path.isdir(match["path"]):
            dirty = _dirty(match["path"])
            if dirty is None:
                raise BranchError("status_failed", match["path"])
            if dirty:
                return {"ok": False, "blocked": True, "error": "worktree_dirty", "files": dirty[:30],
                        "detail": "Uncommitted or untracked files would be lost; commit or remove them first."}
            steps.append(_step(main, "worktree", "remove", "--", match["path"]))
        else:
            steps.append(_step(main, "worktree", "prune", "-v"))  # folder already gone
        if steps[-1]["ok"] and delete_branch and match["branch"]:
            steps.append(_step(main, "branch", "-d", "--", match["branch"]))
    dev_projects.invalidate()
    ok = all(s["ok"] for s in steps)
    return {"ok": ok, "removed": match["path"], "branch": match["branch"],
            "branch_deleted": delete_branch and len(steps) == 2 and steps[1]["ok"],
            "steps": steps, **({} if ok else {"error": "git_failed"})}


def delete_branch(path: str, branch: str) -> dict:
    fs = _repo(path)
    with git_publish._lock_for(path):
        branch = _valid_branch(fs, branch)
        if not _branch_exists(fs, branch):
            raise BranchError("unknown_branch", branch)
        holder = next((w["path"] for w in _list(fs) if w["branch"] == branch), None)
        if holder:
            raise BranchError("branch_checked_out", holder)
        step = _step(fs, "branch", "-d", "--", branch)
    if not step["ok"]:
        unmerged = "not fully merged" in step["output"]
        return {"ok": False, "error": "not_merged" if unmerged else "git_failed", "steps": [step]}
    return {"ok": True, "deleted": branch, "steps": [step]}


def prune_worktrees(path: str) -> dict:
    fs = _repo(path)
    with git_publish._lock_for(path):
        step = _step(fs, "worktree", "prune", "-v")
    dev_projects.invalidate()
    return {"ok": step["ok"], "steps": [step]}
