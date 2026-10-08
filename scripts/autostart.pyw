"""TokenScope boot supervisor: keeps the dashboard running in the background.

Started at logon by the HKCU Run entry that `install-autostart.ps1` writes,
under pythonw.exe so no console window appears. It starts
`tokenscope-web --port <port>` hidden and relaunches it whenever it exits
(crash, or killed to pick up new code). If something else already listens on
the port it just waits. Only one supervisor runs at a time (file lock).

Logs: %LOCALAPPDATA%\\TokenScope\\launch.log (supervisor), server.log (server).
"""
import msvcrt
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXE = os.path.join(ROOT, ".venv", "Scripts", "tokenscope-web.exe")
DATA = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "TokenScope")
POLL = 15          # seconds between port checks while another process owns the port
MAX_BACKOFF = 300  # cap for the restart delay after repeated quick crashes
MAX_LOG = 5_000_000


def log(msg: str) -> None:
    with open(os.path.join(DATA, "launch.log"), "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] autostart: {msg}\n")


def port() -> int:
    try:
        sys.path.insert(0, os.path.join(ROOT, "src"))
        from tokenscope.config import load_config
        return int(load_config().get("port", 8787))
    except Exception:  # noqa: BLE001 - a broken config must not stop the dashboard
        return 8787


def listening(p: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1)
        return s.connect_ex(("127.0.0.1", p)) == 0


def server_log():
    path = os.path.join(DATA, "server.log")
    if os.path.exists(path) and os.path.getsize(path) > MAX_LOG:
        os.replace(path, path + ".1")
    return open(path, "ab")


def main() -> None:
    os.makedirs(DATA, exist_ok=True)
    lock = open(os.path.join(DATA, "autostart.lock"), "a+")
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return  # another supervisor is already running
    p = port()
    log(f"started (pid={os.getpid()}, port={p})")
    backoff = 5
    while True:
        if listening(p):
            time.sleep(POLL)
            continue
        if not os.path.exists(EXE):
            log(f"missing {EXE}; run scripts\\start.ps1 once to create the venv")
            time.sleep(MAX_BACKOFF)
            continue
        started = time.monotonic()
        with server_log() as out:
            child = subprocess.Popen([EXE, "--port", str(p)], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT,
                                     stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
            log(f"server started (pid={child.pid})")
            code = child.wait()
        ran = time.monotonic() - started
        backoff = 5 if ran > 60 else min(backoff * 2, MAX_BACKOFF)
        log(f"server exited (code={code}, ran {ran:.0f}s); restarting in {backoff}s")
        time.sleep(backoff)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        log(f"crashed: {e!r}")
        raise
