#!/usr/bin/env python3
"""One-click launcher for order-agent (Windows local demo).

Starts backend (uvicorn on 127.0.0.1:8000) and nginx (127.0.0.1:80).
Skips components that are already listening.

Flags:
    --check        only report status, do not start anything
    --no-browser   do not open the default browser
    --foreground   run children in this console (for testing/CI)
"""
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
NGINX_DIR = ROOT / "nginx-1.30.4"
NGINX_EXE = NGINX_DIR / "nginx.exe"

ANACONDA_PY = Path(r"D:\tool\anaconda\python.exe")
PYTHON = str(ANACONDA_PY) if ANACONDA_PY.exists() else sys.executable


def probe(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.5):
            return True
    except OSError:
        return False


def spawn(cmd, cwd: Path, foreground: bool):
    kwargs = {"cwd": str(cwd)}
    if not foreground:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    try:
        return subprocess.Popen(cmd, **kwargs)
    except OSError as exc:
        print(f"[ERR] failed to open a new console window ({exc}); try running with --foreground")
        raise


def main() -> int:
    args = set(sys.argv[1:])
    check_only = "--check" in args
    no_browser = "--no-browser" in args
    foreground = "--foreground" in args

    if not (BACKEND_DIR / ".env").exists():
        print("[ERR] backend/.env not found. Copy backend/.env.example to backend/.env first.")
        return 1
    if not NGINX_EXE.exists():
        print(f"[ERR] nginx not found: {NGINX_EXE}")
        return 1

    backend_up = probe(8000)
    nginx_up = probe(80)

    if backend_up:
        print("[OK] backend already listening on 127.0.0.1:8000")
    elif not check_only:
        print("[..] starting backend on 127.0.0.1:8000 ...")
        spawn([PYTHON, "-m", "uvicorn", "app.main:app",
               "--host", "127.0.0.1", "--port", "8000"], BACKEND_DIR, foreground)
    else:
        print("[--] backend is DOWN (check mode, not started)")

    if nginx_up:
        print("[OK] nginx already listening on 127.0.0.1:80")
    elif not check_only:
        print("[..] starting nginx ...")
        spawn([str(NGINX_EXE), "-p", ".", "-c", "conf/nginx.conf"], NGINX_DIR, foreground)
    else:
        print("[--] nginx is DOWN (check mode, not started)")

    if check_only:
        print("check done.")
        return 0

    time.sleep(3)
    if not no_browser:
        try:
            webbrowser.open("http://127.0.0.1/")
        except Exception:  # noqa: BLE001
            pass

    print("")
    print("order-agent is up at http://127.0.0.1")
    print("backend console: window 'order-agent backend (8000)' (if started here)")
    print("nginx console  : window 'order-agent nginx (80)' (if started here)")
    print("stop: close those windows; or run: nginx -s stop inside nginx-1.30.4")
    return 0


if __name__ == "__main__":
    sys.exit(main())
