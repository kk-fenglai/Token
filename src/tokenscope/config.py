r"""Runtime paths and user config.

All mutable data (DB, config.json, pricing.json) lives in %LOCALAPPDATA%\TokenScope,
never inside the OneDrive-synced source tree (SQLite WAL + cloud sync corrupts).
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from importlib.resources import as_file, files
from pathlib import Path

APP_NAME = "TokenScope"


def data_dir() -> Path:
    base = os.environ.get("TOKENSCOPE_DATA_DIR")
    if base:
        d = Path(base)
    else:
        local = os.environ.get("LOCALAPPDATA")
        d = Path(local) / APP_NAME if local else Path.home() / ".local" / "share" / APP_NAME.lower()
    d.mkdir(parents=True, exist_ok=True)
    return d


def db_path() -> Path:
    return data_dir() / "tokenscope.db"


def config_path() -> Path:
    return data_dir() / "config.json"


def pricing_path() -> Path:
    return data_dir() / "pricing.json"


_HOME = Path.home()

# Directories whose immediate children are projects. A session's cwd is folded
# to the first directory under whichever of these contains it, so
# `<project>/backend` counts as `<project>`. See projects.py.
DEFAULT_WORKSPACE_ROOTS = [
    _HOME / "Desktop",
    _HOME / "OneDrive" / "Desktop",
    _HOME / "Documents",
    _HOME / "OneDrive" / "Documents",
    _HOME / "projects",
    _HOME / "code",
    _HOME / "src",
    _HOME / "dev",
    _HOME / "repos",
    _HOME / "workspace",
]

DEFAULT_CONFIG = {
    "scan_roots": [str(_HOME / ".claude" / "projects")],
    "port": 8787,
    "sync_interval_seconds": 300,
    "workspace_roots": [str(p) for p in DEFAULT_WORKSPACE_ROOTS],
    # {old path: new path} for folders that were renamed or moved — their paths
    # share no prefix, so no rule can merge them automatically.
    "project_aliases": {},
    # "auto" reads the plan from ~/.claude.json; "manual" pins {plan, monthly_usd}.
    "subscription": {"mode": "auto"},
    # F26 dev-project tracker: which local git repos to watch and when to nag.
    # `extra` adds repos discovery would miss, `ignored` hides ones it finds,
    # `pinned` keeps favourites on top. Hours are the staleness thresholds.
    "dev_projects": {
        "extra": [],
        "ignored": [],
        "pinned": [],
        "active_days": 14,
        "unpushed_danger_hours": 24,
        "dirty_warn_hours": 24,
        "desktop_notify": True,
    },
}


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg if isinstance(cfg, dict) else {})
    return merged


def save_config(cfg: dict) -> None:
    p = config_path()
    fd, tmp = tempfile.mkstemp(dir=p.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        os.replace(tmp, p)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def ensure_pricing_file() -> Path:
    p = pricing_path()
    if not p.exists():
        with as_file(files("tokenscope") / "pricing.default.json") as default:
            if default.exists():
                shutil.copyfile(default, p)
    return p
