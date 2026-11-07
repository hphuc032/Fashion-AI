import secrets
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from fashion_api.core.config import WebConfig
from fashion_api.main import create_app


@pytest.fixture
def config(tmp_path):
    return WebConfig(profile=tmp_path / "profile", runtime_dir=tmp_path / "profile/web-runtime",
                     repository=Path(__file__).resolve().parents[3], ffmpeg="missing-w1-ffmpeg", ffprobe="missing-w1-ffprobe")


@pytest.fixture
def clock():
    return [1000000000.0]


@pytest.fixture
def client(config, clock):
    secret = secrets.token_urlsafe(32)
    app = create_app(config, bootstrap_secret=secret, clock=lambda: clock[0])
    with TestClient(app, base_url="http://127.0.0.1:8000") as client:
        client.secret = secret
        yield client


def authenticate(client):
    response = client.post("/api/v1/session/bootstrap", headers={"Origin": "http://127.0.0.1:3000"},
                           json={"bootstrap_secret": client.secret})
    assert response.status_code == 200
    return response.json()["csrf_token"]
