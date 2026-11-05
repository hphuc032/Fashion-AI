import io
import json
import os
import shutil
import subprocess
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.database.session import create_database
from app.services import storage_service as storage
from app.services.video_service import parse_metadata, probe_video
from app.utils.validators import SourceInfo, UserError, validate_filename, validate_source


def payload(audio=True):
    streams = [{"codec_type": "video", "codec_name": "h264", "width": 180,
                "height": 320, "avg_frame_rate": "30000/1001"}]
    if audio:
        streams.append({"codec_type": "audio", "codec_name": "aac"})
    return {"format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "2.0"}, "streams": streams}


@pytest.fixture
def setup(tmp_path):
    settings = Settings(storage_root=tmp_path / "media", max_upload_size_mb=1)
    url = f"sqlite:///{tmp_path / 'test.db'}"
    sessions = create_database(url)
    yield settings, sessions, url
    sessions.kw["bind"].dispose()


def test_metadata_and_no_audio():
    meta = parse_metadata(payload(), ".mp4")
    assert meta.fps == pytest.approx(29.97003)
    assert meta.aspect_ratio == "9:16"
    assert meta.audio_codec == "aac"
    assert parse_metadata(payload(False), ".mov").audio_codec is None


@pytest.mark.parametrize("data", [{}, {"streams": [], "format": {}}, {"format": {"format_name": "avi"}, "streams": []}])
def test_malformed_metadata(data):
    with pytest.raises(UserError):
        parse_metadata(data, ".mp4")


@pytest.mark.parametrize("field,value", [("width", 0), ("height", -1), ("avg_frame_rate", "0/0")])
def test_bad_video_values(field, value):
    data = payload()
    data["streams"][0][field] = value
    with pytest.raises(UserError):
        parse_metadata(data, ".mp4")


@pytest.mark.parametrize("name", ["bad.txt", "../x.mp4", "..\\x.mp4", "C:\\x.mp4", "C:x.mp4", "x:evil.mp4", "NUL.mp4", "x\x00.mp4", "x.mp4 "])
def test_unsafe_or_unsupported_name(name):
    with pytest.raises(UserError):
        validate_filename(name)


def test_unicode_filename():
    assert validate_filename("Áo sơ mi.MP4") == ".mp4"


def test_missing_probe(tmp_path):
    with pytest.raises(UserError, match="Không tìm thấy"):
        probe_video(tmp_path / "test.mp4", "nonexistent-ffprobe-m0", ".mp4")


def test_probe_failure_and_safe_arguments(monkeypatch, tmp_path):
    def fail(args, **kwargs):
        assert isinstance(args, list) and kwargs["shell"] is False
        assert kwargs["timeout"] == 30
        raise subprocess.CalledProcessError(1, args)
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(UserError, match="không đọc được"):
        probe_video(tmp_path / "broken.mp4", "ffprobe", ".mp4")


def test_import_persistence_unique_id_and_idempotency(setup, monkeypatch):
    settings, sessions, url = setup
    monkeypatch.setattr(storage, "probe_video", lambda *args: parse_metadata(payload(), ".mp4"))
    token = str(uuid4())
    data = b"synthetic video bytes"
    first = storage.import_video(io.BytesIO(data), "áo.mp4", SourceInfo(), settings, sessions, token)
    again = storage.import_video(io.BytesIO(data), "áo.mp4", SourceInfo(), settings, sessions, token)
    second = storage.import_video(io.BytesIO(data), "áo.mp4", SourceInfo(), settings, sessions, str(uuid4()))
    assert first.id == again.id and first.id != second.id
    assert (settings.storage_root / first.file_path).read_bytes() == data
    reopened = create_database(url)
    assert len(storage.list_projects(reopened)) == 2
    reopened.kw["bind"].dispose()


@pytest.mark.parametrize("data", [b"", b"x" * (1024 * 1024 + 1)])
def test_size_and_empty_rejection(setup, data):
    settings, sessions, _ = setup
    with pytest.raises(UserError):
        storage.import_video(io.BytesIO(data), "x.mp4", SourceInfo(), settings, sessions, str(uuid4()))
    assert not storage.list_projects(sessions)
    assert not list(settings.storage_root.rglob("*.mp4"))


def test_duration_cleanup(setup, monkeypatch):
    settings, sessions, _ = setup
    meta = parse_metadata(payload(), ".mp4").model_copy(update={"duration": 181})
    monkeypatch.setattr(storage, "probe_video", lambda *args: meta)
    with pytest.raises(UserError, match="giây"):
        storage.import_video(io.BytesIO(b"video"), "x.mp4", SourceInfo(), settings, sessions, str(uuid4()))
    assert not storage.list_projects(sessions)
    assert not list(settings.storage_root.rglob("*.mp4"))


def test_source_and_path_validation(tmp_path):
    with pytest.raises(UserError):
        validate_source(source_url="file:///secret", rights_status="owned")
    with pytest.raises(UserError):
        storage.resolve_media(tmp_path, "../secret.mp4")


def test_real_ffprobe_import_and_corruption(setup, tmp_path):
    ffmpeg = os.environ.get("FFMPEG_PATH", "ffmpeg")
    ffprobe = os.environ.get("FFPROBE_PATH", "ffprobe")
    if not shutil.which(ffmpeg) or not shutil.which(ffprobe):
        pytest.skip("FFmpeg/FFprobe not installed")
    settings, sessions, _ = setup
    settings.ffprobe_path = ffprobe
    video = tmp_path / "synthetic.mp4"
    subprocess.run([ffmpeg, "-y", "-v", "error", "-f", "lavfi", "-i",
                    "color=c=blue:s=180x320:r=25:d=1", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(video)], check=True, timeout=30)
    with video.open("rb") as stream:
        project = storage.import_video(stream, video.name, SourceInfo(rights_status="owned"),
                                       settings, sessions, str(uuid4()))
    assert (project.width, project.height, project.audio_codec) == (180, 320, None)
    assert (settings.storage_root / project.file_path).read_bytes() == video.read_bytes()
    with pytest.raises(UserError):
        storage.import_video(io.BytesIO(b"broken mp4"), "broken.mp4", SourceInfo(), settings, sessions, str(uuid4()))
    assert len(storage.list_projects(sessions)) == 1
