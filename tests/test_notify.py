"""Desktop toast transport: no shell quoting, Unicode-safe, never raises."""
import base64
import subprocess
import sys

from tokenscope import notify


def test_non_windows_is_a_noop(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: calls.append(1))
    assert notify.toast("t", "b") is False and not calls


def test_windows_passes_text_via_env_and_encoded_command(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    seen = []

    class R:
        returncode = 0

    def fake_run(args, **kwargs):
        seen.append((args, kwargs))
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert notify.toast("TokenScope · 3 个项目待推送", "Token消耗量: 2 个提交未推送", "http://127.0.0.1:8787/#/dev-projects")
    assert len(seen) == 1
    args, kw = seen[0]
    assert args[0] == "powershell" and "-EncodedCommand" in args and "-NonInteractive" in args
    script = base64.b64decode(args[-1]).decode("utf-16-le")
    assert "ToastNotificationManager" in script and "$env:TS_TOAST_TITLE" in script
    assert "Token消耗量" not in script  # text never interpolated into the script
    assert kw["env"]["TS_TOAST_TITLE"] == "TokenScope · 3 个项目待推送"
    assert kw["env"]["TS_TOAST_BODY"] == "Token消耗量: 2 个提交未推送"
    assert kw["env"]["TS_TOAST_URL"].endswith("/#/dev-projects")
    assert kw["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0)
    assert kw["timeout"] == 10.0


def test_windows_falls_back_to_balloon_then_false(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    codes = iter([1, 1])
    scripts = []

    def fake_run(args, **kwargs):
        scripts.append(base64.b64decode(args[-1]).decode("utf-16-le"))

        class R:
            returncode = next(codes)
        return R()
    monkeypatch.setattr(subprocess, "run", fake_run)
    assert notify.toast("t", "b") is False
    assert len(scripts) == 2 and "NotifyIcon" in scripts[1]


def test_exceptions_are_swallowed(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")

    def boom(*a, **k):
        raise subprocess.TimeoutExpired("powershell", 10)
    monkeypatch.setattr(subprocess, "run", boom)
    assert notify.toast("t", "b") is False
