"""W2 real SQLite/media integration in disposable profiles; no AI imports."""

import hashlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fashion_api.main import create_app
from fashion_api.services import projects
from conftest import authenticate


@pytest.fixture
def media(tmp_path):
    executable = os.environ.get("FASHION_WEB_FFMPEG", "ffmpeg")
    path = tmp_path / "fixture.mp4"
    subprocess.run(
        [
            executable,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x120:r=24",
            "-t",
            "3",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(path),
        ],
        check=True,
        timeout=30,
    )
    return path.read_bytes()


@pytest.fixture
def project_client(config, tmp_path):
    root = tmp_path / "managed"
    root.mkdir()
    db = tmp_path / "projects.db"
    # Explicit test provisioning only, never production startup/migration.
    import sys

    sys.path.insert(0, str(config.repository))
    from sqlalchemy import create_engine
    from app.database.models import Project

    engine = create_engine("sqlite:///" + str(db))
    Project.__table__.create(engine)
    engine.dispose()
    config = config.model_copy(
        update={
            "database_path": db,
            "storage_root": root,
            "ffprobe": os.environ.get("FASHION_WEB_FFPROBE", "ffprobe"),
        }
    )
    secret = secrets.token_urlsafe(32)
    with TestClient(
        create_app(config, bootstrap_secret=secret), base_url="http://127.0.0.1:8000"
    ) as c:
        c.secret = secret
        c.csrf = authenticate(c)
        c.config = config
        yield c


def submit(c, media, token=None, metadata=None, name="original.mp4", **kwargs):
    return c.post(
        "/api/v1/projects",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "X-CSRF-Token": c.csrf,
            "Idempotency-Key": token or str(uuid4()),
        },
        files={"video": (name, media, "video/mp4")},
        data={"metadata": json.dumps(metadata or {"rights_status": "owned"})},
        **kwargs,
    )


def test_real_import_persist_detail_ranges_and_idempotency(project_client, media):
    c = project_client
    token = str(uuid4())
    result = submit(c, media, token)
    assert result.status_code == 201, result.text
    row = result.json()
    pid = row["id"]
    assert row["duration"] == 3 and row["width"] == 160
    assert not any(
        key in row for key in ["file_path", "stored_filename", "upload_token"]
    )
    assert submit(c, media, token).status_code == 200
    assert submit(c, media + b"changed", token).status_code == 409
    assert submit(c, media, token, {"rights_status": "licensed"}).status_code == 409
    assert c.get("/api/v1/projects").json()["total"] == 1
    assert c.get(f"/api/v1/projects/{pid}").json() == row
    source = f"/api/v1/projects/{pid}/source"
    assert c.get(source).content == media
    for header, expected in [
        ("bytes=10-49", media[10:50]),
        ("bytes=-20", media[-20:]),
        ("bytes=20-", media[20:]),
    ]:
        r = c.get(source, headers={"Range": header})
        assert r.status_code == 206 and r.content == expected
        assert int(r.headers["content-length"]) == len(expected)
        assert r.headers["x-content-type-options"] == "nosniff"
    for header in ["bytes=99999999-", "bytes=5-2", "bytes=-0", "bytes=0-2,4-6", "bad"]:
        r = c.get(source, headers={"Range": header})
        assert (
            r.status_code == 416
            and r.headers["content-range"] == f"bytes */{len(media)}"
        )
    # New app/session against same explicit profile, durable rows and bytes.
    secret = secrets.token_urlsafe(32)
    with TestClient(
        create_app(c.config, bootstrap_secret=secret), base_url="http://127.0.0.1:8000"
    ) as second:
        second.secret = secret
        authenticate(second)
        assert second.get("/api/v1/projects").json()["total"] == 1
        assert second.get(source).content == media


def test_database_pagination_search_and_metadata_concurrency(project_client, media):
    c = project_client
    for n in range(3):
        assert submit(c, media, name=f"clip-{n}.mp4").status_code == 201
    first = c.get("/api/v1/projects?limit=2").json()
    assert len(first["items"]) == 2 and first["next_cursor"]
    second = c.get(
        "/api/v1/projects", params={"limit": 2, "cursor": first["next_cursor"]}
    ).json()
    assert len(second["items"]) == 1
    assert {r["id"] for r in first["items"]}.isdisjoint(
        {r["id"] for r in second["items"]}
    )
    assert c.get("/api/v1/projects?search=clip-1").json()["total"] == 1
    assert c.get("/api/v1/projects?search=%25").json()["total"] == 0
    for query in ["limit=101", "cursor=garbage", "extra=secret"]:
        assert c.get("/api/v1/projects?" + query).status_code in {400, 422}
    row = first["items"][0]
    url = "/api/v1/projects/" + row["id"]
    headers = {
        "Origin": "http://127.0.0.1:3000",
        "X-CSRF-Token": c.csrf,
        "If-Match": row["revision"],
    }
    changed = c.patch(url, headers=headers, json={"creator_name": "Creator"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["rights_status"] == "owned"
    assert (
        c.patch(url, headers=headers, json={"creator_name": "Overwritten"}).status_code
        == 409
    )
    assert (
        c.patch(url, headers=headers, json={"file_path": "outside"}).status_code == 422
    )


@pytest.mark.parametrize(
    "name", ["../escape.mp4", "%2e%2e.mp4", "C:\\private.mp4", "CON.mp4", "clip.exe"]
)
def test_upload_filename_rejection(project_client, media, name):
    c = project_client
    r = submit(c, media, name=name)
    # Encoded-looking literal name is never decoded into a storage path.
    assert r.status_code == (201 if name in {"%2e%2e.mp4", "C:\\private.mp4"} else 415)
    if r.status_code == 201:
        assert (
            "/" not in r.json()["original_filename"]
            and "\\" not in r.json()["original_filename"]
        )


def test_invalid_media_partial_cleanup_and_no_original_deletion(
    project_client, media, monkeypatch
):
    c = project_client
    assert submit(c, media).status_code == 201
    before = {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in c.config.storage_root.rglob("*")
        if p.is_file()
    }
    assert submit(c, b"not a video").status_code == 422
    assert submit(c, b"").status_code == 422
    assert submit(c, media, name="mismatch.mkv").status_code == 422
    assert {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in c.config.storage_root.rglob("*")
        if p.is_file()
    } == before
    assert c.get("/api/v1/projects").json()["total"] == 1
    monkeypatch.setattr(
        shutil, "disk_usage", lambda _: shutil._ntuple_diskusage(1, 1, 0)
    )
    assert submit(c, media).status_code == 507


def test_auth_csrf_and_profile_fail_closed(client, project_client, media):
    authenticate(client)
    assert client.get("/api/v1/projects").status_code == 503
    assert client.get("/api/v1/system/diagnostics").json()["ready"] is False
    c = project_client
    for headers, code in [
        ({"Origin": "http://evil.invalid"}, 403),
        ({"Origin": "http://127.0.0.1:3000"}, 403),
        ({"Host": "evil.invalid"}, 400),
    ]:
        assert (
            c.post(
                "/api/v1/projects", headers=headers, files={"video": ("x.mp4", media)}
            ).status_code
            == code
        )
    c.cookies.clear()
    assert c.get("/api/v1/projects").status_code == 401


def test_cross_project_identity_and_symlink_escape(project_client, media, tmp_path):
    c = project_client
    first = submit(c, media).json()
    second = submit(c, media).json()
    with sqlite3.connect(c.config.database_path) as db:
        path = db.execute(
            "select file_path from projects where id=?", (second["id"],)
        ).fetchone()[0]
        db.execute("update projects set file_path=? where id=?", (path, first["id"]))
    assert c.get("/api/v1/projects/" + first["id"] + "/source").status_code == 404
    assert c.get("/api/v1/projects/" + str(uuid4()) + "/source").status_code == 404
    source = c.config.storage_root / path
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(media)
    source.unlink()
    try:
        source.symlink_to(outside)
    except OSError:
        if os.name != "nt":
            pytest.fail("Cannot exercise filesystem link containment")
        external = tmp_path / "outside-directory"
        external.mkdir()
        (external / source.name).write_bytes(media)
        source.parent.rmdir()
        result = subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(source.parent), str(external)],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, "QA junction setup failed"
    assert c.get("/api/v1/projects/" + second["id"] + "/source").status_code == 409


def test_missing_database_never_created(config, tmp_path):
    config = config.model_copy(
        update={
            "database_path": tmp_path / "missing.db",
            "storage_root": tmp_path / "missing-root",
        }
    )
    with pytest.raises(projects.ProjectError):
        projects.profile(config)
    assert not config.database_path.exists() and not config.storage_root.exists()


def test_oversized_stream_duration_and_disk_full(project_client, media, monkeypatch):
    c = project_client
    object.__setattr__(c.app.state.config, "max_upload_size_mb", 1)
    assert submit(c, b"x" * (1024 * 1024 + 100000)).status_code == 413
    assert list((c.config.storage_root / ".web-uploads").iterdir()) == []
    object.__setattr__(c.app.state.config, "max_video_seconds", 1)
    assert submit(c, media).status_code == 422
    object.__setattr__(c.app.state.config, "max_video_seconds", 180)
    from app.services import storage_service

    def full(*args):
        raise OSError(28, "Synthetic full disk")

    monkeypatch.setattr(storage_service.os, "link", full)
    assert submit(c, media).status_code == 507
    assert c.get("/api/v1/projects").json()["total"] == 0
    assert not list(c.config.storage_root.rglob("*.part"))


def test_publication_collision_never_removes_other_file(
    project_client, media, monkeypatch
):
    c = project_client
    from app.services import storage_service

    original = storage_service.os.link
    foreign = []

    def collision(source, target):
        target.write_bytes(b"foreign source sentinel")
        foreign.append(target)
        return original(source, target)

    monkeypatch.setattr(storage_service.os, "link", collision)
    assert submit(c, media).status_code == 503
    assert foreign[0].read_bytes() == b"foreign source sentinel"
    assert c.get("/api/v1/projects").json()["total"] == 0


def test_unknown_schema_and_duplicate_fields_rejected_without_migration(
    project_client, media
):
    c = project_client
    duplicate = c.post(
        "/api/v1/projects",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "X-CSRF-Token": c.csrf,
            "Idempotency-Key": str(uuid4()),
        },
        files=[("video", ("one.mp4", media)), ("video", ("two.mp4", media))],
        data={"metadata": '{"rights_status":"owned"}'},
    )
    assert duplicate.status_code == 422
    with sqlite3.connect(c.config.database_path) as db:
        db.execute("create table schema_migrations(version integer primary key)")
        db.execute("insert into schema_migrations values(999)")
    before = c.config.database_path.read_bytes()
    assert c.get("/api/v1/projects").status_code == 409
    assert c.config.database_path.read_bytes() == before


def test_concurrent_admission_rejects_before_spooling(project_client, media):
    c = project_client
    gate = c.app.state.upload_gate
    gate.acquire()
    try:
        assert submit(c, media).status_code == 409
    finally:
        gate.release()
    assert not (c.config.storage_root / ".web-uploads").exists()


def test_commit_failure_cleans_new_source_and_preserves_existing(
    project_client, media, monkeypatch
):
    from app.services import storage_service
    from sqlalchemy import event

    c = project_client
    assert submit(c, media).status_code == 201
    before = {
        str(p): p.read_bytes() for p in c.config.storage_root.rglob("*") if p.is_file()
    }
    # Fail the real SQLite INSERT after filesystem publication.
    from sqlalchemy.engine import Engine

    def fail_insert(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO projects"):
            raise sqlite3.OperationalError("Synthetic commit failure")

    event.listen(Engine, "before_cursor_execute", fail_insert)
    try:
        with pytest.raises(sqlite3.OperationalError):
            with projects.sessions(c.config) as (factory, root):
                from app.core.config import Settings
                from app.utils.validators import SourceInfo

                storage_service.import_video(
                    io.BytesIO(media),
                    "other.mp4",
                    SourceInfo(rights_status="owned"),
                    Settings(storage_root=root, ffprobe_path=c.config.ffprobe),
                    factory,
                    str(uuid4()),
                )
    finally:
        event.remove(Engine, "before_cursor_execute", fail_insert)
    assert c.get("/api/v1/projects").json()["total"] == 1
    assert {
        str(p): p.read_bytes() for p in c.config.storage_root.rglob("*") if p.is_file()
    } == before


def test_expired_session_and_read_source_protected(project_client, media):
    c = project_client
    row = submit(c, media).json()
    for state in c.app.state.access.sessions.values():
        state.expires = 0
    assert c.get("/api/v1/projects/" + row["id"] + "/source").status_code == 401


def test_leftover_staging_fails_without_deleting_anything(project_client, media):
    c = project_client
    staging = c.config.storage_root / ".web-uploads"
    staging.mkdir()
    sentinel = staging / "unreviewed"
    sentinel.write_bytes(b"preserve")
    assert submit(c, media).status_code == 409
    assert sentinel.read_bytes() == b"preserve"


def test_partial_parser_disconnect_cleans_managed_spool(tmp_path):
    import asyncio
    from starlette.datastructures import Headers
    from fashion_api.services.multipart import ManagedMultipart

    async def interrupted():
        yield (
            b'--bound\r\nContent-Disposition: form-data; name="video"; filename="clip.mp4"\r\n\r\n'
            + b"x" * (2 * 1024 * 1024)
        )
        raise ConnectionError("Synthetic client disconnect")

    async def run():
        parser = ManagedMultipart(
            Headers({"content-type": "multipart/form-data; boundary=bound"}),
            interrupted(),
            directory=tmp_path,
            max_files=1,
            max_fields=1,
        )
        with pytest.raises(ConnectionError):
            await parser.parse()
        assert all(f.closed for f in parser._files_to_close_on_error)

    asyncio.run(run())
    assert not list(tmp_path.iterdir())


def test_unsupported_detected_codec_rolls_back_source(
    project_client, media, monkeypatch
):
    from app.services import storage_service

    probe = storage_service.probe_video
    monkeypatch.setattr(
        storage_service,
        "probe_video",
        lambda *a: probe(*a).model_copy(update={"video_codec": "unsupported-fixture"}),
    )
    assert submit(project_client, media).status_code == 415
    assert project_client.get("/api/v1/projects").json()["total"] == 0
    assert not [p for p in project_client.config.storage_root.rglob("*") if p.is_file()]
