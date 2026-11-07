"""Windows Web supervisor. Only runtime metadata is written; no engine imports."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import time
import traceback
import urllib.request
import uuid
import webbrowser

import psutil

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from fashion_api.core.config import WebConfig  # noqa: E402

HIDDEN = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class RuntimeFailure(Exception):
    """Only fixed, non-secret operator messages may be printed."""


@contextmanager
def profile_lock(directory):
    directory.mkdir(parents=True, exist_ok=True)
    file = (directory / "instance.lock").open("a+b")
    file.seek(0)
    if (directory / "instance.lock").stat().st_size == 0:
        file.write(b"0"); file.flush()
    file.seek(0)
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        file.close()
        raise RuntimeFailure("A Web instance or maintenance operation already owns this profile.") from None
    try:
        yield
    finally:
        file.close()


def read_status(directory):
    try:
        value = json.loads((directory / "status.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def atomic_json(target, value):
    partial = target.with_name(f"{target.stem}.{uuid.uuid4().hex}.tmp")
    partial.write_text(json.dumps(value), encoding="utf-8")
    # Windows readers can momentarily hold a handle without FILE_SHARE_DELETE.
    # Keep the previous complete JSON visible and retry the atomic rename only.
    for attempt in range(80):
        try:
            partial.replace(target)
            return
        except PermissionError:
            if attempt == 79:
                raise RuntimeFailure("Cannot update private runtime metadata; check its permissions.") from None
            time.sleep(.025)


def write_status(directory, state):
    atomic_json(directory / "status.json", state)


def identity(process):
    p = psutil.Process(process.pid if hasattr(process, "pid") else int(process))
    return {"pid": p.pid, "created": p.create_time(), "exe": str(Path(p.exe()).resolve()), "argv": p.cmdline()}


def owned(record):
    """Never authorize a kill using PID/port/name alone."""
    try:
        p = psutil.Process(record["pid"])
        if abs(p.create_time() - record["created"]) > .01:
            return None
        if str(Path(p.exe()).resolve()).casefold() != str(Path(record["exe"]).resolve()).casefold():
            return None
        if p.cmdline() != record["argv"] or not p.is_running():
            return None
        return p
    except (KeyError, TypeError, ValueError, psutil.Error):
        return None


def stop_record(record):
    process = owned(record)
    if process is None:
        return False
    # W1 starts direct Python and Node processes (no npm/shell parent trees).
    # Snapshot descendant identities and revalidate each before termination.
    try:
        descendants = [identity(p) for p in process.children(recursive=True)]
        for info in reversed(descendants):
            child = owned(info)
            if child:
                try:
                    child.terminate()
                except psutil.NoSuchProcess:
                    pass
        process = owned(record)
        if process:
            process.terminate()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired:
                again = owned(record)
                if again:
                    again.kill(); again.wait(timeout=3)
        for info in descendants:
            child = owned(info)
            if child:
                try:
                    child.wait(timeout=2)
                except psutil.TimeoutExpired:
                    again = owned(info)
                    if again:
                        again.kill(); again.wait(timeout=3)
        return True
    except psutil.Error:
        return False


def ports_available():
    for port in (8000, 3000):
        with socket.socket() as sock:
            if os.name == "nt":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                raise RuntimeFailure(f"Port {port} is occupied. Stop its owner; ports are never switched automatically.") from None


def preflight(config):
    if sys.version_info[:2] != (3, 11):
        raise RuntimeFailure("Use the isolated Python 3.11 Web environment.")
    node = shutil.which("node")
    if not node:
        raise RuntimeFailure("Node.js 24 is required; startup never installs it.")
    try:
        version = subprocess.check_output([node, "--version"], timeout=5, text=True, creationflags=HIDDEN).strip()
    except (OSError, subprocess.SubprocessError):
        raise RuntimeFailure("Cannot check Node.js.") from None
    if version.split(".")[0] != "v24":
        raise RuntimeFailure("This frozen frontend requires Node.js 24.x.")
    web = ROOT / "apps/web"
    if not (web / "node_modules/next/dist/bin/next").is_file() or not (web / ".next/BUILD_ID").is_file():
        raise RuntimeFailure("Frontend install/build is missing. Run documented frozen installation and build first.")
    ports_available()
    return node


def http_json(url):
    # Do not send loopback bootstrap/readiness through proxy environment settings.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=1) as response:
        return json.loads(response.read(16384))


def wait_ready(check, process, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeFailure("A Web service exited before readiness. See its private runtime log.")
        try:
            if check():
                return
        except (OSError, ValueError):
            pass
        time.sleep(.15)
    raise RuntimeFailure("Web service readiness timed out; owned children will be stopped.")


def frontend_ready(record):
    process = owned(record)
    if not process:
        return False
    try:
        # A successful HTTP response alone could belong to a process that won
        # the bind race. Require this exact owned tree to hold the loopback port.
        listeners = [c for p in [process, *process.children(recursive=True)]
                     for c in p.net_connections(kind="tcp") if c.status == psutil.CONN_LISTEN]
        if not any(c.laddr.ip == "127.0.0.1" and c.laddr.port == 3000 for c in listeners):
            return False
        if any(c.laddr.port == 3000 and c.laddr.ip != "127.0.0.1" for c in listeners):
            return False
    except psutil.Error:
        return False
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open("http://127.0.0.1:3000/dashboard", timeout=1) as response:
        return response.status == 200


def supervise(config, *, no_browser=False, timeout=45, backend_command=None, frontend_command=None, launch_id=None):
    # Commands are injectable only in Python tests, never HTTP/env/CLI arguments.
    config = WebConfig.model_validate(config)
    directory = config.runtime_dir.resolve()
    children = []
    state = {}
    try:
        with profile_lock(directory):
            # Guard release during startup/shutdown with the same profile lock.
            node = preflight(config)
            run_id, instance_id = launch_id or str(uuid.uuid4()), str(uuid.uuid4())
            state = {"state": "starting", "run_id": run_id, "supervisor": identity(os.getpid()), "children": [], "instance_id": instance_id}
            write_status(directory, state)
            secret = secrets.token_urlsafe(32)
            env = os.environ.copy()
            env.update(PYTHONPATH=str(ROOT / "apps/api"), PYTHONNOUSERSITE="1", PYTHONUTF8="1", NEXT_TELEMETRY_DISABLED="1")
            env.pop("PYTHONHOME", None)
            with (directory / "api.log").open("ab") as log:
                backend = subprocess.Popen(backend_command or [sys.executable, "-m", "fashion_api.serve"],
                    cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log, creationflags=HIDDEN)
            record = identity(backend); children.append(record); state["children"] = children.copy(); write_status(directory, state)
            try:
                backend.stdin.write((json.dumps({"config": config.model_dump(mode="json"), "secret": secret, "instance_id": instance_id}) + "\n").encode())
                backend.stdin.close()
            except OSError:
                raise RuntimeFailure("API private handoff failed.") from None
            wait_ready(lambda: http_json("http://127.0.0.1:8000/api/v1/health").get("instance_id") == instance_id, backend, timeout)
            with (directory / "web.log").open("ab") as log:
                frontend = subprocess.Popen(frontend_command or [node, str(ROOT / "apps/web/node_modules/next/dist/bin/next"), "start", "--hostname", "127.0.0.1", "--port", "3000"],
                    cwd=ROOT / "apps/web", env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=HIDDEN)
            record = identity(frontend); children.append(record); state["children"] = children.copy(); write_status(directory, state)
            wait_ready(lambda: frontend_ready(record), frontend, timeout)
            state["state"] = "running"; write_status(directory, state)
            if not no_browser:
                if not webbrowser.open("http://127.0.0.1:3000/dashboard#bootstrap=" + secret):
                    raise RuntimeFailure("Cannot open the default browser; owned Web services will be stopped.")
            del secret
            while backend.poll() is None and frontend.poll() is None:
                stop = directory / "stop.json"
                if stop.is_file():
                    try:
                        request = json.loads(stop.read_text())
                    except (ValueError, OSError):
                        request = {}
                    if request.get("run_id") == run_id:
                        break
                time.sleep(.2)
            else:
                raise RuntimeFailure("A Web service stopped unexpectedly.")
            state["state"] = "stopping"; write_status(directory, state)
            for record in reversed(children):
                if not stop_record(record):
                    raise RuntimeFailure("Cannot verify or stop an owned service; inspect runtime status.")
            children.clear()
            state["children"] = []; state["state"] = "stopped"; write_status(directory, state)
        return 0
    except (RuntimeFailure, OSError, ValueError) as exc:
        for record in reversed(children):
            stop_record(record)
        if state:
            frames = [f"{Path(f.filename).name}:{f.lineno}:{f.name}" for f in traceback.extract_tb(exc.__traceback__)]
            state.update(state="failed", error_type=type(exc).__name__, failure_at=frames,
                         message=str(exc) if isinstance(exc, RuntimeFailure) else "Web startup or runtime failed. Inspect private logs and occupied ports.")
            write_status(directory, state)
        return 1


def start(config, no_browser=False, timeout=45):
    directory = config.runtime_dir.resolve()
    old = read_status(directory)
    if old.get("state") in {"starting", "running", "stopping"} and owned(old.get("supervisor", {})):
        print("Web runtime already owns this profile; no duplicate was started.")
        return 2
    preflight(config)
    # Explicitly authorized runtime metadata only; database/profile content untouched.
    directory.mkdir(parents=True, exist_ok=True)
    with profile_lock(directory):
        pass
    launch_id = str(uuid.uuid4())
    command = [sys.executable, str(Path(__file__).resolve()), "supervise", "--profile", str(config.profile), "--timeout", str(timeout), "--launch-id", launch_id]
    if no_browser:
        command.append("--no-browser")
    with (directory / "supervisor.log").open("ab") as log:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=HIDDEN)
    deadline = time.monotonic() + timeout * 2 + 10
    while time.monotonic() < deadline:
        status = read_status(directory)
        if status.get("state") == "running" and status.get("run_id") == launch_id and owned(status.get("supervisor", {})):
            print("READY: http://127.0.0.1:3000/dashboard — W1 health foundation only.")
            return 0
        if process.poll() is not None:
            raise RuntimeFailure("Web startup failed. Only private runtime logs were written; no database was opened.")
        time.sleep(.2)
    raise RuntimeFailure("Supervisor readiness timed out. Use stop_web.ps1 before retrying.")


def stop(config, timeout=15):
    directory = config.runtime_dir.resolve()
    state = read_status(directory)
    record = state.get("supervisor", {})
    if not owned(record):
        print("No verified Web supervisor; no process was terminated.")
        return 2
    # Cooperative stop retains the lock until all owned children are gone.
    atomic_json(directory / "stop.json", {"run_id": state.get("run_id")})
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = read_status(directory)
        if current.get("run_id") == state.get("run_id") and current.get("state") == "stopped" and not owned(record):
            with profile_lock(directory):
                pass
            print("STOPPED: owned Web services only; profile data preserved.")
            return 0
        if not owned(record):
            # Process exit can race a previous read of the status file. Re-read
            # the terminal marker and acquire the released lock before failing.
            final = read_status(directory)
            if final.get("run_id") == state.get("run_id") and final.get("state") == "stopped":
                with profile_lock(directory):
                    pass
                print("STOPPED: owned Web services only; profile data preserved.")
                return 0
            raise RuntimeFailure("Supervisor exited without confirmed cleanup; inspect status before retrying.")
        time.sleep(.1)
    raise RuntimeFailure("Cooperative stop timed out; no unverified process was killed.")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "stop", "supervise"])
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--launch-id", type=lambda v: str(uuid.UUID(v)))
    parser.add_argument("--timeout", type=int, default=45, choices=range(1, 121))
    args = parser.parse_args(argv)
    if args.profile:
        os.environ["FASHION_WEB_PROFILE"] = str(args.profile)
    try:
        config = WebConfig.from_env()
        if args.command == "start":
            return start(config, args.no_browser, args.timeout)
        if args.command == "stop":
            return stop(config)
        return supervise(config, no_browser=args.no_browser, timeout=args.timeout, launch_id=args.launch_id)
    except RuntimeFailure as exc:
        print(str(exc))
        return 1
    except (ValueError, OSError):
        print("Web runtime check failed. Verify Python/Node, profile paths, built frontend and fixed ports; no database is initialized.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
