import pytest
from conftest import authenticate

ORIGIN = "http://127.0.0.1:3000"


@pytest.mark.parametrize("headers", [
    {"Host": "evil.example:8000"}, {"Host": "127.0.0.1:9000"}, {"Host": "localhost:8000"},
    {"Host": "127.0.0.1:8000,evil.example"}, {"Host": "127.0.0.1:8000@evil.example"},
    {"X-Forwarded-Host": "127.0.0.1:8000"}, {"Forwarded": "host=evil.example"},
    {"X-Forwarded-Port": "8000"}, {"X-Forwarded-Proto": "https"},
])
def test_host_authority(client, headers):
    assert client.get("/api/v1/health", headers=headers).status_code == 400


def test_duplicate_host(client):
    assert client.get("/api/v1/health", headers=[("Host", "127.0.0.1:8000"), ("Host", "evil.example")]).status_code == 400


@pytest.mark.parametrize("origin", ["null", "file://", "http://evil.example", "https://127.0.0.1:3000", "http://127.0.0.1:3001", "http://localhost:3000"])
def test_wrong_origin_even_on_public_health(client, origin):
    assert client.get("/api/v1/health", headers={"Origin": origin}).status_code == 403


def test_duplicate_origin(client):
    assert client.get("/api/v1/health", headers=[("Origin", ORIGIN), ("Origin", ORIGIN)]).status_code == 403


def test_missing_session_and_valid_authenticated_health(client):
    assert client.get("/api/v1/system/status").status_code == 401
    authenticate(client)
    assert client.get("/api/v1/health", headers={"Origin": ORIGIN}).status_code == 200
    assert client.get("/api/v1/system/status", headers={"Origin": ORIGIN}).status_code == 200


def test_bootstrap_replay_and_cookie_attributes(client):
    response = client.post("/api/v1/session/bootstrap", headers={"Origin": ORIGIN}, json={"bootstrap_secret": client.secret})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/api" in cookie
    assert "domain=" not in cookie and "secure" not in cookie
    assert client.secret not in response.text
    replay = client.post("/api/v1/session/bootstrap", headers={"Origin": ORIGIN}, json={"bootstrap_secret": client.secret})
    assert replay.status_code == 401


def test_bootstrap_expiration(client, clock):
    clock[0] += 91
    assert client.post("/api/v1/session/bootstrap", headers={"Origin": ORIGIN}, json={"bootstrap_secret": client.secret}).status_code == 401


def test_bootstrap_requires_origin_and_json(client):
    assert client.post("/api/v1/session/bootstrap", json={"bootstrap_secret": client.secret}).status_code == 403
    assert client.post("/api/v1/session/bootstrap", headers={"Origin": ORIGIN}, content="bad").status_code == 415


def test_invalid_csrf_and_revocation(client):
    csrf = authenticate(client)
    for headers in [{"Origin": ORIGIN}, {"Origin": ORIGIN, "X-CSRF-Token": "wrong"}]:
        assert client.delete("/api/v1/session", headers=headers).status_code == 403
    assert client.delete("/api/v1/session", headers={"X-CSRF-Token": csrf}).status_code == 403
    assert client.delete("/api/v1/session", headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/session").status_code == 401


def test_session_expiration(client, clock):
    authenticate(client)
    clock[0] += 3601
    assert client.get("/api/v1/system/status").status_code == 401


def test_cors_preflight(client):
    headers = {"Origin": ORIGIN, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-csrf-token"}
    r = client.options("/api/v1/session/bootstrap", headers=headers)
    assert r.status_code == 204
    assert r.headers["access-control-allow-origin"] == ORIGIN
    assert r.headers["access-control-allow-credentials"] == "true"
    assert client.options("/api/v1/session/bootstrap", headers=headers | {"Origin": "null"}).status_code == 403
    assert client.options("/api/v1/session/bootstrap", headers=headers | {"Access-Control-Request-Headers": "x-arbitrary"}).status_code == 403
    assert client.options("/api/v1/session/bootstrap", headers=headers | {"Access-Control-Request-Method": "PUT"}).status_code == 403


def test_security_headers_and_no_query_secrets(client):
    response = client.get("/api/v1/health")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert client.get("/api/v1/health?bootstrap=not-allowed").status_code == 400


def test_bounded_body_and_invalid_secret(client):
    r = client.post("/api/v1/session/bootstrap", headers={"Origin": ORIGIN, "Content-Type": "application/json"}, content=b"x" * 2049)
    assert r.status_code == 413
    r = client.post("/api/v1/session/bootstrap", headers={"Origin": ORIGIN}, json={"bootstrap_secret": "x" * 43})
    assert r.status_code == 401


def test_cookie_duplicate_rejected(client):
    authenticate(client)
    token = client.cookies.get("fashion_web_session")
    assert client.get("/api/v1/system/status", headers={"Cookie": f"fashion_web_session={token}; fashion_web_session={token}"}).status_code == 401


def test_non_ascii_csrf_rejected_without_internal_error(client):
    authenticate(client)
    response = client.delete("/api/v1/session", headers=[(b"origin", ORIGIN.encode()), (b"x-csrf-token", b"\xff")])
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_REJECTED"
    assert client.get("/api/v1/session").status_code == 200
