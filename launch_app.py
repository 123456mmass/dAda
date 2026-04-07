"""One-click launcher for the Differential Relay app on Windows.

Starts backend and frontend together, waits for both to become ready,
then opens the browser to the frontend.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path


BACKEND_PORT = 8000
FRONTEND_PORT = 3000
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}/api/relay/config"
FRONTEND_URL = f"http://127.0.0.1:{FRONTEND_PORT}"

_children: list[subprocess.Popen[bytes] | subprocess.Popen[str]] = []


def _log(message: str) -> None:
    print(f"[launcher] {message}", flush=True)


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates = [exe_dir, exe_dir.parent]
    else:
        script_dir = Path(__file__).resolve().parent
        candidates = [script_dir]

    for candidate in candidates:
        if (candidate / "backend").is_dir() and (candidate / "frontend").is_dir():
            return candidate

    raise RuntimeError("หาโฟลเดอร์โปรเจกต์ไม่เจอ (ต้องมี backend และ frontend)")


def _find_pids_listening_on_port(port: int) -> list[int]:
    try:
        result = subprocess.run(
            ["netstat", "-ano", "-p", "tcp"],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.SubprocessError:
        return []

    pids: set[int] = set()
    suffix = f":{port}"
    current_pid = os.getpid()
    for line in result.stdout.splitlines():
        line = line.strip()
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        if not parts[1].endswith(suffix):
            continue
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        if pid != current_pid:
            pids.add(pid)
    return sorted(pids)


def _kill_process_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
    )


def _clear_port(port: int) -> None:
    pids = _find_pids_listening_on_port(port)
    for pid in pids:
        _log(f"กำลังปิดโปรเซสเก่าที่ใช้พอร์ต {port} (PID {pid})")
        _kill_process_tree(pid)


def _wait_for_port_to_close(port: int, timeout_sec: float = 5.0) -> None:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not _find_pids_listening_on_port(port):
            return
        time.sleep(0.2)


def _wait_for_http(url: str, timeout_sec: float = 60.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _resolve_python_command() -> list[str]:
    python_path = shutil.which("python")
    if python_path:
        return [python_path]

    py_launcher = shutil.which("py")
    if py_launcher:
        return [py_launcher, "-3"]

    raise RuntimeError("หา Python ไม่เจอใน PATH")


def _resolve_npm_command() -> list[str]:
    npm_cmd = shutil.which("npm.cmd") or shutil.which("npm")
    if npm_cmd:
        return [npm_cmd]
    raise RuntimeError("หา npm ไม่เจอใน PATH")


def _spawn(command: list[str], workdir: Path) -> subprocess.Popen[str]:
    _log(f"เริ่ม: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        cwd=str(workdir),
        text=True,
    )
    _children.append(process)
    return process


def _ensure_frontend_build(frontend_dir: Path) -> None:
    build_id = frontend_dir / ".next" / "BUILD_ID"
    if build_id.exists():
        return

    _log("ยังไม่พบ frontend build กำลัง build ให้ก่อน")
    npm = _resolve_npm_command()
    result = subprocess.run(
        [*npm, "run", "build"],
        cwd=str(frontend_dir),
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("frontend build ไม่สำเร็จ")


def _cleanup(*_args: object) -> None:
    for process in reversed(_children):
        if process.poll() is None:
            _log(f"กำลังปิดโปรเซส PID {process.pid}")
            _kill_process_tree(process.pid)


def main() -> int:
    project_root = _project_root()
    backend_root = project_root
    frontend_dir = project_root / "frontend"

    atexit.register(_cleanup)
    signal.signal(signal.SIGINT, _cleanup)
    signal.signal(signal.SIGTERM, _cleanup)

    _clear_port(BACKEND_PORT)
    _clear_port(FRONTEND_PORT)
    _wait_for_port_to_close(BACKEND_PORT)
    _wait_for_port_to_close(FRONTEND_PORT)

    _ensure_frontend_build(frontend_dir)

    python_cmd = _resolve_python_command()
    npm_cmd = _resolve_npm_command()

    _spawn([*python_cmd, "run_backend.py"], backend_root)
    if not _wait_for_http(BACKEND_URL, timeout_sec=45):
        raise RuntimeError("backend ไม่พร้อมบนพอร์ต 8000")

    _spawn(
        [*npm_cmd, "run", "start", "--", "--hostname", "0.0.0.0", "--port", str(FRONTEND_PORT)],
        frontend_dir,
    )
    if not _wait_for_http(FRONTEND_URL, timeout_sec=60):
        raise RuntimeError("frontend ไม่พร้อมบนพอร์ต 3000")

    _log("frontend และ backend พร้อมแล้ว กำลังเปิดหน้าเว็บ")
    webbrowser.open("http://localhost:3000")
    _log("ระบบกำลังทำงานอยู่ ปิดหน้าต่างนี้หรือกด Ctrl+C เพื่อหยุดทั้งสองฝั่ง")

    while True:
        for process in list(_children):
            code = process.poll()
            if code is not None:
                raise RuntimeError(f"มีโปรเซสจบก่อนเวลาอันควร (PID {process.pid}, exit code {code})")
        time.sleep(1)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        _log(str(exc))
        sys.exit(1)
