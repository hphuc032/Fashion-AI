import builtins
import json
from pathlib import Path
import secrets
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient
from fashion_api.main import create_app, diagnostics
from fashion_api.core.config import WebConfig
from conftest import authenticate


def test_health_and_status(client):
    health = client.get("/api/v1/health")
    assert health.status_code == 200
    assert set(health.json()) == {"status", "api_version", "instance_id"}
    assert health.json()["api_version"] == "v1"
    assert client.get("/api/v1/system/status").status_code == 401
    authenticate(client)
    status = client.get("/api/v1/system/status")
    assert status.json() == {"api_version": "v1", "local_only": True, "readiness": "degraded",
        "tools": {"ffmpeg": False, "ffprobe": False, "subtitles": "unavailable"},
        "database": {"configured": False, "schema_status": "not_inspected"}, "models": "not_inspected"}


def test_bootstrap_lifespan_has_no_engine_or_database_effects(config, monkeypatch):
    config.profile.mkdir()
    sentinel = config.profile / "private.db"
    sentinel.write_bytes(b"never open this existing file")
    config = config.model_copy(update={"database_path": sentinel})
    before = {p.relative_to(config.profile): p.read_bytes() for p in config.profile.rglob("*") if p.is_file()}
    original_import = builtins.__import__

    def guard(name, *args, **kwargs):
        if name.split(".")[0] in {"app", "streamlit", "paddle", "paddleocr", "sherpa_onnx", "faster_whisper"}:
            raise AssertionError("Forbidden engine import")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guard)
    monkeypatch.setattr(sqlite3, "connect", lambda *a, **kw: pytest.fail("SQLite opened"))
    with TestClient(create_app(config), base_url="http://127.0.0.1:8000") as c:
        assert c.get("/api/v1/health").status_code == 200
        assert c.app.state.diagnostics.database.configured
    after = {p.relative_to(config.profile): p.read_bytes() for p in config.profile.rglob("*") if p.is_file()}
    assert before == after
    assert not config.runtime_dir.exists()


def test_openapi_is_protected_and_schema_matches_committed(client):
    assert client.get("/api/v1/openapi.json").status_code == 401
    authenticate(client)
    # Session cookie is intentionally Path=/api; explicitly attach it to verify
    # the disabled docs route, rather than confusing cookie scoping with routing.
    assert client.get("/docs", headers={"Cookie": "fashion_web_session=" + client.cookies.get("fashion_web_session")}).status_code == 404
    actual = client.get("/api/v1/openapi.json").json()
    expected = json.loads(Path(__file__).resolve().parents[1].joinpath("openapi.json").read_text(encoding="utf-8"))
    assert actual == expected
    assert '/api/v1/projects' in actual['paths']
    assert '/api/v1/jobs' not in actual['paths']


def test_redacted_validation_does_not_echo_secret_path(client):
    malicious = "synthetic-secret-do-not-echo"
    result = client.post("/api/v1/session/bootstrap", headers={"Origin": "http://127.0.0.1:3000"},
                         json={"bootstrap_secret": client.secret, "private": malicious})
    assert result.status_code == 422
    assert malicious not in result.text and client.secret not in result.text
    assert "traceback" not in result.text.lower()


@pytest.mark.parametrize("field,value", [
    ("profile", Path("relative")), ("runtime_dir", Path("relative")),
    ("database_path", Path("relative.db")), ("frontend_origin", "http://localhost:3000"),
    ("backend_host", "0.0.0.0:8000"), ("ffmpeg", "relative/tools/ffmpeg"),
    ("ffprobe", "bad\ncommand"), ("profile", Path(Path.cwd().anchor)),
])
def test_invalid_profile(config, field, value):
    with pytest.raises(ValueError):
        WebConfig.model_validate(config.model_dump() | {field: value})


def test_overlap_and_no_automatic_adoption(config):
    for overrides in [{"profile": config.repository / "storage"}, {"runtime_dir": config.profile},
                      {"database_path": config.runtime_dir / "anything.db"}]:
        with pytest.raises(ValueError):
            WebConfig.model_validate(config.model_dump() | overrides)
    assert config.database_path is None
    assert not config.profile.exists()


def test_restart_invalidates_sessions(config):
    secret = secrets.token_urlsafe(32)
    first = create_app(config, bootstrap_secret=secret)
    with TestClient(first, base_url="http://127.0.0.1:8000") as c:
        c.secret = secret
        authenticate(c)
        cookie = c.cookies.get("fashion_web_session")
    second = create_app(config)
    with TestClient(second, base_url="http://127.0.0.1:8000") as c:
        result = c.get("/api/v1/system/status", headers={"Cookie": "fashion_web_session=" + cookie})
        assert result.status_code == 401
