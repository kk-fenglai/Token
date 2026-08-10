r"""Runtime paths and user config.

All mutable data (DB, config.json, pricing.json) lives in %LOCALAPPDATA%\TokenScope,
never inside the OneDrive-synced source tree (SQLite WAL + cloud sync corrupts).
"""
from __future__ import annotations

import json
import os
import shutil
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


DEFAULT_CONFIG = {
    "scan_roots": [str(Path.home() / ".claude" / "projects")],
    "port": 8787,
    "sync_interval_seconds": 300,
}


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        p.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    try:
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(cfg if isinstance(cfg, dict) else {})
    return merged


def ensure_pricing_file() -> Path:
    p = pricing_path()
    if not p.exists():
        with as_file(files("tokenscope") / "pricing.default.json") as default:
            if default.exists():
                shutil.copyfile(default, p)
    return p
