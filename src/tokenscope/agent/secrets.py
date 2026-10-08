"""The DeepSeek API key: `DEEPSEEK_API_KEY` wins, else `secrets.json` in the
data dir (not config.json, which gets shared and pasted around).

On Windows the stored value is encrypted with DPAPI for the current user, so
the file is useless if copied to another account or machine. Elsewhere it is
stored as-is with 0600 permissions. The key never leaves this module except
to build the API client; everything user-facing gets `mask()`.
"""
from __future__ import annotations

import base64
import json
import os
import sys
from typing import Literal

from ..config import data_dir

ENV_VAR = "DEEPSEEK_API_KEY"
Source = Literal["env", "stored", "none"]


def _path():
    return data_dir() / "secrets.json"


# ------------------------------------------------------------------ DPAPI ----

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def _to_blob(data: bytes) -> _Blob:
        buf = ctypes.create_string_buffer(data, len(data))
        return _Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    def _from_blob(blob: _Blob) -> bytes:
        out = ctypes.string_at(blob.pbData, blob.cbData)
        ctypes.windll.kernel32.LocalFree(blob.pbData)
        return out

    def _protect(data: bytes) -> bytes:
        src, dst = _to_blob(data), _Blob()
        if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(src), "TokenScope", None, None, None,
                                                      0x01, ctypes.byref(dst)):  # CRYPTPROTECT_UI_FORBIDDEN
            raise OSError("CryptProtectData failed")
        return _from_blob(dst)

    def _unprotect(data: bytes) -> bytes:
        src, dst = _to_blob(data), _Blob()
        if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(src), None, None, None, None,
                                                        0x01, ctypes.byref(dst)):
            raise OSError("CryptUnprotectData failed")
        return _from_blob(dst)
else:
    _protect = _unprotect = None


# ----------------------------------------------------------------- public ----

def _read() -> dict:
    try:
        with open(_path(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _stored_key(name: str = "deepseek") -> str | None:
    entry = _read().get(name)
    if not isinstance(entry, dict) or not isinstance(entry.get("value"), str):
        return None
    try:
        if entry.get("enc") == "dpapi":
            if _unprotect is None:
                return None
            return _unprotect(base64.b64decode(entry["value"])).decode("utf-8")
        return entry["value"]
    except (OSError, ValueError):
        return None


def get_api_key() -> tuple[str | None, Source]:
    env = os.environ.get(ENV_VAR, "").strip()
    if env:
        return env, "env"
    stored = _stored_key()
    return (stored, "stored") if stored else (None, "none")


def set_api_key(key: str, name: str = "deepseek") -> None:
    """Store a key under `name` ("deepseek", or "trustmrr" for the
    inspiration board) — every entry gets the same DPAPI treatment."""
    key = key.strip()
    if not key or len(key) > 400 or any(c.isspace() for c in key):
        raise ValueError("invalid key")
    if _protect is not None:
        entry = {"enc": "dpapi", "value": base64.b64encode(_protect(key.encode("utf-8"))).decode("ascii")}
    else:
        entry = {"enc": "plain", "value": key}
    data = _read()
    data[name] = entry
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    if sys.platform != "win32":
        os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def clear_api_key(name: str = "deepseek") -> None:
    data = _read()
    if data.pop(name, None) is not None:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(data, f)


def mask(key: str | None) -> str | None:
    if not key:
        return None
    if len(key) <= 8:
        return "…" + key[-2:]
    return f"{key[:3]}…{key[-4:]}"


def key_status() -> dict:
    key, source = get_api_key()
    return {"configured": key is not None, "source": source, "masked": mask(key)}
