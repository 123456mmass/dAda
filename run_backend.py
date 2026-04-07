"""Root launcher - run backend from project root."""
import os
import subprocess
import sys


BACKEND_PORT = 8000


def _find_pids_listening_on_port(port: int) -> list[int]:
    """Return Windows PIDs listening on the given TCP port."""
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
    for line in result.stdout.splitlines():
        line = line.strip()
        if "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        pid_text = parts[-1]
        if not local_address.endswith(suffix):
            continue
        try:
            pid = int(pid_text)
        except ValueError:
            continue
        if pid != os.getpid():
            pids.add(pid)
    return sorted(pids)


def _kill_processes_on_port(port: int) -> None:
    """Force-kill any processes already listening on the backend port."""
    for pid in _find_pids_listening_on_port(port):
        print(f"[run_backend] Killing process {pid} on port {port}...")
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
        )


_kill_processes_on_port(BACKEND_PORT)

os.chdir(os.path.join(os.path.dirname(__file__), "backend"))

command = [
    sys.executable,
    "-m",
    "uvicorn",
    "main:app",
    "--host",
    "0.0.0.0",
    "--port",
    str(BACKEND_PORT),
]

if os.environ.get("CODE2_BACKEND_RELOAD") == "1":
    command.append("--reload")

sys.exit(subprocess.call(command))
