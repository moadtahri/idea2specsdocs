"""Restart only this workspace's WSL uvicorn supervisor with mount-safe polling."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    supervisors = []
    listening_sockets = set()
    for table in (Path("/proc/net/tcp"), Path("/proc/net/tcp6")):
        for line in table.read_text().splitlines()[1:]:
            fields = line.split()
            if fields[1].split(":")[-1] == "1F40" and fields[3] == "0A":
                listening_sockets.add(f"socket:[{fields[9]}]")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
            cwd = (entry / "cwd").resolve()
        except (OSError, PermissionError):
            continue
        if cwd != root:
            continue
        supervisor = (
            b"app.main:app" in args
            and b"--reload" in args
            and any(
                value.endswith(b"/uvicorn") or value == b"uvicorn" for value in args
            )
        )
        try:
            owns_listener = any(
                os.readlink(fd) in listening_sockets for fd in (entry / "fd").iterdir()
            )
        except (OSError, PermissionError):
            owns_listener = False
        worker = any(b"spawn_main" in value for value in args) and owns_listener
        if not supervisor and not worker:
            continue
        supervisors.append(int(entry.name))
    for process_id in supervisors:
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            continue
        print("Restarting workspace uvicorn supervisor:", process_id, flush=True)
        children = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            try:
                parent = next(
                    line.split()[1]
                    for line in (entry / "status").read_text().splitlines()
                    if line.startswith("PPid:")
                )
                if int(parent) == process_id:
                    children.append(int(entry.name))
            except (OSError, StopIteration):
                continue
        os.kill(process_id, signal.SIGTERM)
        time.sleep(5)
        for stale_pid in [*children, process_id]:
            try:
                os.kill(stale_pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    environment = os.environ.copy()
    environment["WATCHFILES_FORCE_POLLING"] = "true"
    environment["WATCHFILES_IGNORE_PERMISSION_DENIED"] = "true"
    logs = root / "data" / "dev-server.log"
    logs.parent.mkdir(parents=True, exist_ok=True)
    with logs.open("ab") as output:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--reload-dir",
                str(root / "app"),
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
            cwd=root,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    print(
        "Started backend:",
        process.pid,
        "with WATCHFILES_FORCE_POLLING=true",
        flush=True,
    )
