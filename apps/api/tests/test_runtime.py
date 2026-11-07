"""Real ownership and isolated two-process lifecycle tests; no user profiles."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

import psutil
import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("web_runtime", ROOT / "scripts/web_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)


def command(action, profile, shell_name=None):
    shell = shutil.which(shell_name) if shell_name else (shutil.which("pwsh") or shutil.which("powershell"))
    if not shell:
        pytest.skip("Requested Windows PowerShell host is not installed")
    return [shell, "-NoProfile", "-File", str(ROOT / f"scripts/{action}_web.ps1"),
            "-PythonPath", sys.executable, "-Profile", str(profile)]


def test_lock_exclusive_then_release(tmp_path):
    directory = tmp_path / "runtime"
    with runtime.profile_lock(directory):
        with pytest.raises(runtime.RuntimeFailure):
            with runtime.profile_lock(directory):
                pass
    with runtime.profile_lock(directory):
        pass


def test_atomic_status_retries_windows_reader_sharing(tmp_path, monkeypatch):
    target = tmp_path / "status.json"
    target.write_text('{"state":"starting"}')
    replace = Path.replace
    calls = []
    def sharing(source, destination):
        calls.append(1)
        if len(calls) <= 3:
            assert json.loads(target.read_text())["state"] == "starting"
            raise PermissionError("Synthetic Windows reader sharing violation")
        return replace(source, destination)
    monkeypatch.setattr(Path, "replace", sharing)
    runtime.write_status(tmp_path, {"state": "running"})
    assert len(calls) == 4
    assert json.loads(target.read_text()) == {"state": "running"}


def test_identity_pid_reuse_and_stale_status():
    info = runtime.identity(os.getpid())
    assert runtime.owned(info)
    assert runtime.owned(info | {"created": info["created"] - 30}) is None
    assert runtime.owned(info | {"exe": str(ROOT / "unrelated.exe")}) is None
    assert runtime.owned(info | {"argv": ["unrelated"]}) is None
    assert runtime.owned({}) is None
    assert not runtime.stop_record(info | {"created": 0})


@pytest.mark.parametrize("port", [3000, 8000])
def test_occupied_port_no_kill(tmp_path, port):
    with socket.socket() as sock:
        if os.name == "nt":
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind(("127.0.0.1", port)); sock.listen(1)
        result = subprocess.run(command("start", tmp_path / "profile") + ["-NoBrowser"], capture_output=True, timeout=15)
        assert result.returncode == 1
        assert sock.getsockname()[1] == port
        assert not (tmp_path / "profile").exists()


def test_stale_status_never_kills_unrelated(tmp_path, config):
    config.runtime_dir.mkdir(parents=True)
    info = runtime.identity(os.getpid())
    runtime.write_status(config.runtime_dir, {"state": "running", "supervisor": info | {"created": 0}, "run_id": "stale"})
    assert runtime.stop(config) == 2
    assert psutil.pid_exists(os.getpid())


@pytest.mark.parametrize("shell_name", ["pwsh", "powershell"])
def test_real_scripts_start_duplicate_stop_restart_spaces(tmp_path, shell_name):
    profile = tmp_path / "profile with spaces"
    profile.mkdir()
    sentinel = profile / "do-not-open.db"
    sentinel.write_bytes(b"preserved private data")
    env = os.environ.copy()
    env["FASHION_WEB_DATABASE"] = str(sentinel)
    baseline = sentinel.read_bytes()
    records = []
    try:
        for _ in range(2):
            started = subprocess.run(command("start", profile, shell_name) + ["-NoBrowser"], env=env, capture_output=True, timeout=90)
            assert started.returncode == 0, started.stdout.decode(errors="replace")
            status = runtime.read_status(profile / "web-runtime")
            records += status["children"]
            assert status["state"] == "running"
            api = runtime.http_json("http://127.0.0.1:8000/api/v1/health")
            assert api["instance_id"] == status["instance_id"]
            duplicate = subprocess.run(command("start", profile, shell_name) + ["-NoBrowser"], env=env, capture_output=True, timeout=15)
            assert duplicate.returncode == 2
            assert runtime.read_status(profile / "web-runtime")["run_id"] == status["run_id"]
            # Verify actual socket bindings of application-owned listening PIDs.
            pids = {v["pid"] for v in status["children"]}
            for v in status["children"]:
                parent = runtime.owned(v)
                if parent:
                    pids.update(p.pid for p in parent.children(recursive=True))
            listeners = [c for c in psutil.net_connections(kind="tcp") if c.pid in pids and c.status == psutil.CONN_LISTEN]
            assert {(c.laddr.ip, c.laddr.port) for c in listeners} == {("127.0.0.1", 3000), ("127.0.0.1", 8000)}
            stopped = subprocess.run(command("stop", profile, shell_name), env=env, capture_output=True, timeout=30)
            assert stopped.returncode == 0, stopped.stdout.decode(errors="replace")
            assert all(runtime.owned(v) is None for v in status["children"])
            assert sentinel.read_bytes() == baseline
            runtime.ports_available()
    finally:
        current = runtime.read_status(profile / "web-runtime")
        if runtime.owned(current.get("supervisor", {})):
            runtime.stop(runtime.WebConfig(profile=profile, runtime_dir=profile / "web-runtime", repository=ROOT))
    # No bootstrap or session secret is stored in runtime status/logs.
    for record in records:
        assert "bootstrap=" not in " ".join(record["argv"])
    assert sentinel.read_bytes() == baseline
    assert {p.name for p in profile.iterdir()} == {"web-runtime", "do-not-open.db"}


@pytest.mark.parametrize("scenario", ["backend-exit", "backend-timeout", "frontend-exit", "frontend-timeout"])
def test_partial_failure_cleanup(config, scenario):
    kwargs = {"no_browser": True, "timeout": 1}
    fail = [sys.executable, "-c", "raise SystemExit(7)"]
    hang = [sys.executable, "-c", "import time; time.sleep(60)"]
    if scenario.startswith("backend"):
        kwargs["backend_command"] = fail if scenario.endswith("exit") else hang
    else:
        kwargs["frontend_command"] = fail if scenario.endswith("exit") else hang
    assert runtime.supervise(config, **kwargs) == 1
    status = runtime.read_status(config.runtime_dir)
    assert status["state"] == "failed"
    assert all(runtime.owned(v) is None for v in status["children"])
    runtime.ports_available()
    assert not list(config.profile.rglob("*.db"))


def test_readiness_timeout_is_bounded():
    class Running:
        @staticmethod
        def poll(): return None
    started = time.monotonic()
    with pytest.raises(runtime.RuntimeFailure):
        runtime.wait_ready(lambda: False, Running(), .2)
    assert time.monotonic() - started < 1
