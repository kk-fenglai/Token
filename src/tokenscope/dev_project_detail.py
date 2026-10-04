"""F28 — dev-project detail page: an overview of one tracked repo plus the
user's own notes about it.

  Meta (user-authored)  alias / description / tags / stage / notes, stored in
                        the `dev_project_meta` table keyed by normalized path.
  Overview (derived)    README excerpt, languages by bytes from `git ls-files`,
                        a detected stack (package.json / pyproject / …), git
                        history and branches, and the Token usage of the
                        project the repo folds into.

Everything derived is read-only and offline, same rules as dev_projects.
Writes that leave the machine (the GitHub description) run only on a click.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone

from . import dev_projects, queries
from .db import locked_conn
from .projects import Folder

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10: no stdlib TOML reader, skip pyproject
    tomllib = None

STAGES = ("idea", "active", "maintenance", "paused", "archived")
MAX_README_BYTES = 200_000
MAX_LS_FILES = 20_000
MAX_STAT_FILES = 8_000
MAX_TAGS = 12
MAX_TAG_LEN = 32
FIELD_LIMITS = {"alias": 80, "description": 2000, "notes": 20_000}

# extension → language; only what is worth naming in a summary.
LANGS = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".vue": "Vue",
    ".svelte": "Svelte", ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".less": "Less",
    ".go": "Go", ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift",
    ".c": "C", ".h": "C", ".cpp": "C++", ".cc": "C++", ".hpp": "C++", ".cs": "C#",
    ".rb": "Ruby", ".php": "PHP", ".dart": "Dart", ".lua": "Lua", ".r": "R",
    ".sql": "SQL", ".sh": "Shell", ".ps1": "PowerShell", ".bat": "Batchfile",
    ".ipynb": "Jupyter Notebook", ".md": "Markdown", ".json": "JSON", ".yml": "YAML",
    ".yaml": "YAML", ".toml": "TOML",
}
# Build output and vendored code do not say what a repo is written in.
_GENERATED_DIRS = {"dist", "build", "out", "vendor", "node_modules", "third_party", ".next",
                   "coverage", "__pycache__", "site-packages"}
_HASHED_ASSET_RE = re.compile(r"[-.][A-Za-z0-9_-]{8,}\.(?:js|css)$")


def is_generated(rel: str) -> bool:
    parts = rel.lower().split("/")
    if any(p in _GENERATED_DIRS for p in parts[:-1]):
        return True
    name = parts[-1]
    if ".min." in name or name.endswith((".map", "-lock.json", ".lock")):
        return True
    # Vite / webpack output: `assets/index-C376JtGx.js`
    return "assets" in parts[:-1] and bool(_HASHED_ASSET_RE.search(name))


# Data / docs formats are listed, but never "the" language of a repo.
MARKUP = {"Markdown", "JSON", "YAML", "TOML"}

# dependency name → label, checked in order (first hits are listed first).
JS_STACK = (
    ("next", "Next.js"), ("nuxt", "Nuxt"), ("react", "React"), ("vue", "Vue"),
    ("svelte", "Svelte"), ("@angular/core", "Angular"), ("electron", "Electron"),
    ("vite", "Vite"), ("tailwindcss", "Tailwind CSS"), ("express", "Express"),
    ("@nestjs/core", "NestJS"), ("prisma", "Prisma"), ("typescript", "TypeScript"),
)
PY_STACK = (
    ("fastapi", "FastAPI"), ("django", "Django"), ("flask", "Flask"),
    ("streamlit", "Streamlit"), ("pandas", "pandas"), ("torch", "PyTorch"),
    ("anthropic", "Anthropic SDK"), ("openai", "OpenAI SDK"), ("pytest", "pytest"),
)
MARKER_FILES = (
    ("Cargo.toml", "Rust / Cargo"), ("go.mod", "Go modules"), ("pom.xml", "Maven"),
    ("build.gradle", "Gradle"), ("Dockerfile", "Docker"), ("docker-compose.yml", "Docker Compose"),
    (".claude-plugin", "Claude Code plugin"), ("pubspec.yaml", "Flutter / Dart"),
)


# ------------------------------------------------------------------- meta ----

_SCHEMA = """
CREATE TABLE IF NOT EXISTS dev_project_meta (
  path        TEXT PRIMARY KEY,
  alias       TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  tags        TEXT NOT NULL DEFAULT '[]',
  stage       TEXT NOT NULL DEFAULT '',
  notes       TEXT NOT NULL DEFAULT '',
  updated_at  TEXT
)
"""

EMPTY_META = {"alias": "", "description": "", "tags": [], "stage": "", "notes": "", "updated_at": None}


def _ensure(conn) -> None:
    conn.execute(_SCHEMA)


def _row_meta(row) -> dict:
    try:
        tags = json.loads(row["tags"] or "[]")
    except ValueError:
        tags = []
    return {"alias": row["alias"], "description": row["description"],
            "tags": [t for t in tags if isinstance(t, str)], "stage": row["stage"],
            "notes": row["notes"], "updated_at": row["updated_at"]}


def get_meta(path: str) -> dict:
    with locked_conn() as conn:
        _ensure(conn)
        row = conn.execute("SELECT * FROM dev_project_meta WHERE path=?", (path,)).fetchone()
    return _row_meta(row) if row else dict(EMPTY_META)


def all_meta() -> dict[str, dict]:
    with locked_conn() as conn:
        _ensure(conn)
        rows = conn.execute("SELECT * FROM dev_project_meta").fetchall()
    return {r["path"]: _row_meta(r) for r in rows}


def clean_meta(body: dict) -> tuple[dict, list[str]]:
    """Validate a partial update. Returns (fields to set, errors)."""
    out: dict = {}
    errors: list[str] = []
    for k, limit in FIELD_LIMITS.items():
        if k in body:
            v = body[k]
            if not isinstance(v, str):
                errors.append(f"{k} must be a string")
            elif len(v) > limit:
                errors.append(f"{k} is longer than {limit} characters")
            else:
                out[k] = v.strip() if k != "notes" else v.rstrip()
    if "tags" in body:
        v = body["tags"]
        if not (isinstance(v, list) and all(isinstance(t, str) for t in v)):
            errors.append("tags must be a list of strings")
        else:
            seen: list[str] = []
            for t in v:
                t = re.sub(r"\s+", " ", t).strip()[:MAX_TAG_LEN]
                if t and t.lower() not in {s.lower() for s in seen}:
                    seen.append(t)
            if len(seen) > MAX_TAGS:
                errors.append(f"at most {MAX_TAGS} tags")
            out["tags"] = seen[:MAX_TAGS]
    if "stage" in body:
        v = body["stage"]
        if v not in ("", *STAGES):
            errors.append(f"stage must be one of {', '.join(STAGES)} or empty")
        else:
            out["stage"] = v
    unknown = set(body) - set(FIELD_LIMITS) - {"tags", "stage", "path"}
    if unknown:
        errors.append(f"unknown keys: {', '.join(sorted(unknown))}")
    return out, errors


def save_meta(path: str, fields: dict) -> dict:
    merged = {**get_meta(path), **fields}
    merged["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with locked_conn() as conn:
        _ensure(conn)
        conn.execute(
            "INSERT INTO dev_project_meta(path, alias, description, tags, stage, notes, updated_at) "
            "VALUES(?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET alias=excluded.alias, "
            "description=excluded.description, tags=excluded.tags, stage=excluded.stage, "
            "notes=excluded.notes, updated_at=excluded.updated_at",
            (path, merged["alias"], merged["description"], json.dumps(merged["tags"], ensure_ascii=False),
             merged["stage"], merged["notes"], merged["updated_at"]),
        )
        conn.commit()
    return merged


# ----------------------------------------------------------------- readme ----

_README_NAMES = ("readme.md", "readme.markdown", "readme.rst", "readme.txt", "readme")


def find_readme(root: str) -> str | None:
    try:
        names = {n.lower(): n for n in os.listdir(root)}
    except OSError:
        return None
    for cand in _README_NAMES:
        if cand in names and os.path.isfile(os.path.join(root, names[cand])):
            return os.path.join(root, names[cand])
    return None


_BADGE_RE = re.compile(r"\[?!\[[^\]]*\]\([^)]*\)\]?(\([^)]*\))?")
_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_HTML_RE = re.compile(r"<[^>]+>")


def readme_summary(text: str) -> dict:
    """First H1 as the title and the first prose paragraph as the summary,
    with badges, links, HTML and emphasis markers stripped."""
    title = None
    para: list[str] = []
    in_code = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("```") or line.startswith("~~~"):
            in_code = not in_code
            if para:
                break
            continue
        if in_code:
            continue
        if line.startswith("#"):
            if para:
                break
            if title is None and re.match(r"^#\s", line):
                title = _plain(line.lstrip("#").strip())
            continue
        if not line:
            if para:
                break
            continue
        # tables, lists, quotes and rules are not a summary
        if re.match(r"^([|>*+-]|\d+\.\s|={3,}|-{3,})", line):
            if para:
                break
            continue
        plain = _plain(line)
        if plain:
            para.append(plain)
        elif para:
            break
    summary = " ".join(para)
    if len(summary) > 400:
        summary = summary[:400].rsplit(" ", 1)[0] + "…"
    return {"title": title or None, "summary": summary or None}


def _plain(s: str) -> str:
    s = _BADGE_RE.sub("", s)
    s = _LINK_RE.sub(r"\1", s)
    s = _HTML_RE.sub("", s)
    s = re.sub(r"[*_`]{1,3}([^*_`]+)[*_`]{1,3}", r"\1", s)
    return s.strip()


def read_readme(root: str) -> dict | None:
    path = find_readme(root)
    if not path:
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read(MAX_README_BYTES + 1)
    except OSError:
        return None
    text = raw[:MAX_README_BYTES].decode("utf-8", "replace")
    return {"file": os.path.basename(path), "content": text,
            "truncated": len(raw) > MAX_README_BYTES,
            "markdown": path.lower().endswith((".md", ".markdown")), **readme_summary(text)}


# ------------------------------------------------------------------ stack ----

def _git(path: str, *args: str, timeout: float = dev_projects.PROBE_TIMEOUT) -> tuple[int, bytes]:
    return dev_projects._run(path, *args, timeout=timeout)


def languages(root: str, files: list[str], stat=os.path.getsize) -> list[dict]:
    """Bytes per language over tracked files (like GitHub's bar), top 8.
    Markup/data formats only count when there is no code at all."""
    sizes: dict[str, int] = {}
    for rel in [f for f in files if not is_generated(f)][:MAX_STAT_FILES]:
        lang = LANGS.get(os.path.splitext(rel)[1].lower())
        if not lang:
            continue
        try:
            sizes[lang] = sizes.get(lang, 0) + stat(os.path.join(root, rel))
        except OSError:
            continue
    code = {k: v for k, v in sizes.items() if k not in MARKUP}
    pick = code or sizes
    total = sum(pick.values())
    if not total:
        return []
    out = [{"name": k, "bytes": v, "pct": round(v / total * 100, 1)}
           for k, v in sorted(pick.items(), key=lambda kv: -kv[1])]
    return out[:8]


def _deps_js(pkg: dict) -> set[str]:
    names: set[str] = set()
    for k in ("dependencies", "devDependencies", "peerDependencies"):
        v = pkg.get(k)
        if isinstance(v, dict):
            names |= set(v)
    return names


def _deps_py(text: str) -> set[str]:
    return {m.group(1).lower() for m in re.finditer(r"^\s*\"?([A-Za-z0-9_.-]+)", text, re.M)}


def detect_stack(root: str, files: list[str]) -> dict:
    """Stack labels plus the manifest's own name / description / version."""
    stack: list[str] = []
    manifest: dict = {}
    fileset = set(files)

    def add(label: str) -> None:
        if label not in stack:
            stack.append(label)

    for rel in sorted((f for f in files if f.endswith("package.json") and "node_modules/" not in f),
                      key=lambda f: f.count("/"))[:5]:
        try:
            with open(os.path.join(root, rel), encoding="utf-8") as fh:
                pkg = json.load(fh)
        except (OSError, ValueError):
            continue
        if not isinstance(pkg, dict):
            continue
        deps = _deps_js(pkg)
        for dep, label in JS_STACK:
            if dep in deps:
                add(label)
        if rel == "package.json" and not manifest:
            manifest = {"kind": "package.json", "name": pkg.get("name"),
                        "description": pkg.get("description"), "version": pkg.get("version")}

    py_deps: set[str] = set()
    if "pyproject.toml" in fileset and tomllib is not None:
        try:
            with open(os.path.join(root, "pyproject.toml"), "rb") as fh:
                data = tomllib.load(fh)
            proj = data.get("project") or data.get("tool", {}).get("poetry") or {}
            deps = proj.get("dependencies") or []
            if isinstance(deps, dict):
                deps = list(deps)
            for d in deps:
                if isinstance(d, str):
                    py_deps |= _deps_py(d)
            opt = proj.get("optional-dependencies") or {}
            for group in opt.values() if isinstance(opt, dict) else []:
                for d in group if isinstance(group, list) else []:
                    if isinstance(d, str):
                        py_deps |= _deps_py(d)
            if not manifest:
                manifest = {"kind": "pyproject.toml", "name": proj.get("name"),
                            "description": proj.get("description"), "version": proj.get("version")}
        except (OSError, ValueError):  # TOMLDecodeError is a ValueError
            pass
    for req in ("requirements.txt", "requirements-dev.txt"):
        if req in fileset:
            try:
                with open(os.path.join(root, req), encoding="utf-8", errors="replace") as fh:
                    py_deps |= _deps_py(fh.read())
            except OSError:
                pass
    for dep, label in PY_STACK:
        if dep in py_deps:
            add(label)

    tops = {f.split("/", 1)[0] for f in files}
    for marker, label in MARKER_FILES:
        if marker in fileset or marker in tops:
            add(label)
    return {"stack": stack, "manifest": manifest or None}


# -------------------------------------------------------------------- git ----

def git_overview(path: str) -> dict:
    out: dict = {"commit_count": None, "first_commit_at": None, "recent_commits": [],
                 "branches": [], "contributors": [], "file_count": 0}
    rc, raw = _git(path, "rev-list", "--count", "HEAD")
    if rc == 0 and raw.strip().isdigit():
        out["commit_count"] = int(raw.strip())
    rc, raw = _git(path, "rev-list", "--max-parents=0", "--format=%ct", "HEAD")
    epochs = [float(x) for x in raw.decode("utf-8", "replace").split() if x.isdigit()] if rc == 0 else []
    if epochs:
        out["first_commit_at"] = dev_projects._iso(min(epochs))
    rc, raw = _git(path, "log", "-20", "--format=%h%x1f%ct%x1f%an%x1f%s", "HEAD")
    for line in raw.decode("utf-8", "replace").splitlines() if rc == 0 else []:
        parts = line.split("\x1f")
        if len(parts) == 4 and parts[1].isdigit():
            out["recent_commits"].append({"sha": parts[0], "at": dev_projects._iso(float(parts[1])),
                                          "author": parts[2], "subject": parts[3]})
    rc, raw = _git(path, "for-each-ref", "refs/heads", "--sort=-committerdate",
                   "--format=%(refname:short)%1f%(upstream:short)%1f%(upstream:track)%1f%(committerdate:unix)%1f%(HEAD)")
    for line in raw.decode("utf-8", "replace").splitlines() if rc == 0 else []:
        parts = line.split("\x1f")
        if len(parts) == 5:
            track = parts[2]
            ahead = re.search(r"ahead (\d+)", track)
            behind = re.search(r"behind (\d+)", track)
            out["branches"].append({
                "name": parts[0], "upstream": parts[1] or None, "current": parts[4] == "*",
                "ahead": int(ahead.group(1)) if ahead else 0, "behind": int(behind.group(1)) if behind else 0,
                "gone": "gone" in track,
                "last_commit_at": dev_projects._iso(float(parts[3])) if parts[3].isdigit() else None,
            })
    out["branches"] = out["branches"][:30]
    # -sn groups by author name, so one person committing from two emails
    # (laptop + GitHub web UI) shows once.
    rc, raw = _git(path, "shortlog", "-sn", "HEAD", timeout=dev_projects.STATUS_TIMEOUT)
    for line in raw.decode("utf-8", "replace").splitlines() if rc == 0 else []:
        m = re.match(r"^\s*(\d+)\s+(.+?)\s*$", line)
        if m:
            out["contributors"].append({"name": m.group(2), "commits": int(m.group(1))})
    out["contributors"] = out["contributors"][:10]
    return out


def tracked_files(path: str) -> list[str]:
    rc, raw = _git(path, "ls-files", "-z", timeout=dev_projects.STATUS_TIMEOUT)
    if rc != 0:
        return []
    return [f for f in raw.decode("utf-8", "replace").split("\0") if f][:MAX_LS_FILES]


# ----------------------------------------------------------------- tokens ----

def token_usage(path: str) -> dict | None:
    """Usage of the Token project this repo folds into (which may be a parent
    folder: sessions in `Token消耗量/tokenscope` count under `Token消耗量`)."""
    key = Folder().fold(path)
    try:
        d = queries.project_detail(key)
    except Exception:  # noqa: BLE001 — a broken pricing file must not hide the page
        return None
    if not d:
        return None
    return {"key": d.get("path", key), "name": d.get("name"), "tokens": d.get("tokens", 0),
            "cost": d.get("cost", 0.0), "sessions": d.get("sessions", 0),
            "month_tokens": d.get("month_tokens", 0), "last_active": d.get("last_active"),
            "same_path": normalize(d.get("path", key)) == normalize(path)}


def normalize(p: str) -> str:
    return p.rstrip("/").lower()


# ----------------------------------------------------------------- detail ----

class NotTracked(Exception):
    pass


def tracked_item(path: str) -> dict:
    snap = dev_projects.snapshot()
    item = next((x for x in snap["items"] if x["path"] == path), None)
    if item is None:
        raise NotTracked(path)
    return item


def detail(path: str) -> dict:
    item = tracked_item(path)
    fs = os.path.normpath(item["path"])
    info = {**item, **dev_projects.inspect_repo(item["path"])}
    level, reasons = dev_projects.classify(info, dev_projects.dev_cfg())
    info["level"], info["reasons"] = level, reasons
    files = tracked_files(fs) if info["is_repo"] and not info["error"] else []
    git = git_overview(fs) if files or info.get("last_commit_at") else {
        "commit_count": 0, "first_commit_at": None, "recent_commits": [], "branches": [],
        "contributors": [], "file_count": 0}
    git["file_count"] = len(files)
    return {
        "item": info,
        "meta": get_meta(item["path"]),
        "readme": read_readme(fs),
        "languages": languages(fs, files),
        **detect_stack(fs, files),
        "git": git,
        "tokens": token_usage(item["path"]),
        "editor": editor_path() is not None,
        "stages": list(STAGES),
    }


# ---------------------------------------------------------------- actions ----

def editor_path() -> str | None:
    """VS Code's CLI shim, if installed."""
    for name in ("code", "code.cmd"):
        found = shutil.which(name)
        if found:
            return found
    local = os.environ.get("LOCALAPPDATA")
    if local:
        cand = os.path.join(local, "Programs", "Microsoft VS Code", "bin", "code.cmd")
        if os.path.isfile(cand):
            return cand
    return None


def open_in_editor(path: str) -> bool:
    exe = editor_path()
    if not exe:
        return False
    # code.cmd is a batch file; pass the folder as its own argv entry and
    # never through shell=True (the path is from the tracked snapshot anyway).
    subprocess.Popen([exe, os.path.normpath(path)], creationflags=dev_projects._FLAGS,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    return True


def push_github_description(path: str, description: str) -> dict:
    """`gh repo edit --description` for a repo whose remote is on GitHub."""
    from . import git_publish
    item = tracked_item(path)
    info = dev_projects.inspect_repo(item["path"])
    if not info["is_github"] or not info["github_url"]:
        return {"ok": False, "error": "not_github", "output": ""}
    exe = git_publish.gh_path()
    if not exe:
        return {"ok": False, "error": "gh_missing", "output": ""}
    slug = info["github_url"].removeprefix("https://github.com/")
    desc = re.sub(r"\s+", " ", description).strip()[:350]  # GitHub's limit
    try:
        rc, out, err = git_publish._run([exe, "repo", "edit", slug, "--description", desc],
                                        os.path.normpath(item["path"]), git_publish.PUSH_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"ok": False, "error": "failed", "output": str(e)}
    text = git_publish._redact((out + "\n" + err).strip())[-git_publish.MAX_OUTPUT:]
    return {"ok": rc == 0, "error": None if rc == 0 else git_publish._classify_failure(text), "output": text}
