#!/usr/bin/env python3
"""One-click launcher for order-agent (Windows local demo).

Double-click start_services.bat is enough: if backend (8000) or nginx (80)
is already running, this script stops the old process first, then restarts it.

Optional flags (not required for normal use):
    --check        only report status, do not start/stop anything
    --no-browser   do not open the default browser
    --foreground   run children in this console (for testing/CI)
"""
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
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def listener_pids(port: int) -> list:
    """Return PIDs listening on the given port (Windows netstat)."""
    pids = []
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=8,
        ).stdout
    except Exception:  # noqa: BLE001
        return pids
    for line in out.splitlines():
        if f":{port} " in line and "LISTENING" in line.upper():
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid not in pids:
                    pids.append(pid)
    return pids


def kill_pid(pid: str) -> None:
    subprocess.run(["taskkill", "/PID", pid, "/F"], capture_output=True, text=True)


def stop_port(port: int) -> None:
    """Kill every process listening on the port."""
    for pid in listener_pids(port):
        kill_pid(pid)


def nginx_stop() -> None:
    subprocess.run(
        [str(NGINX_EXE), "-p", ".", "-c", "conf/nginx.conf", "-s", "stop"],
        cwd=str(NGINX_DIR), capture_output=True, text=True,
    )


def wait_until(port: int, up: bool, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if probe(port) == up:
            return True
        time.sleep(0.8)
    return False


def spawn(cmd, cwd: Path, foreground: bool):
    kwargs = {"cwd": str(cwd)}
    if not foreground:
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    return subprocess.Popen(cmd, **kwargs)


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

    if check_only:
        print("[OK] backend already listening on 127.0.0.1:8000" if backend_up else "[--] backend is DOWN")
        print("[OK] nginx already listening on 127.0.0.1:80" if nginx_up else "[--] nginx is DOWN")
        print("check done.")
        return 0

    # ---- stop old processes if already running (restart semantics) ----
    if nginx_up:
        print("[..] stopping old nginx ...")
        nginx_stop()
        stop_port(80)
        if not wait_until(80, up=False, timeout=10):
            print("[ERR] cannot stop old nginx (port 80 still busy); close it manually and retry")
            return 2
    if backend_up:
        print("[..] stopping old backend ...")
        stop_port(8000)
        if not wait_until(8000, up=False, timeout=10):
            print("[ERR] cannot stop old backend (port 8000 still busy); close it manually and retry")
            return 2

    # ---- start ----
    print("[..] starting backend on 127.0.0.1:8000 ...")
    spawn([PYTHON, "-m", "uvicorn", "app.main:app",
           "--host", "127.0.0.1", "--port", "8000"], BACKEND_DIR, foreground)
    print("[..] starting nginx ...")
    spawn([str(NGINX_EXE), "-p", ".", "-c", "conf/nginx.conf"], NGINX_DIR, foreground)

    ok_backend = wait_until(8000, up=True, timeout=30)
    ok_nginx = wait_until(80, up=True, timeout=15)

    if not ok_backend:
        print("[ERR] backend did not come up in time; check its console window")
    if not ok_nginx:
        print("[ERR] nginx did not come up in time; check its console window")
    if ok_backend and ok_nginx:
        print("[OK] backend 127.0.0.1:8000 and nginx 127.0.0.1:80 are up")

    if ok_backend and ok_nginx and not no_browser:
        try:
            webbrowser.open("http://127.0.0.1/")
        except Exception:  # noqa: BLE001
            pass

    print("")
    print("order-agent is up at http://127.0.0.1")
    print("stop: close both service windows, or re-run this script to restart")
    return 0 if (ok_backend and ok_nginx) else 2


if __name__ == "__main__":
    sys.exit(main())
