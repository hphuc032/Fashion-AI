import io
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.database.session import create_database
from app.services.storage_service import import_video
from app.services.video_service import VideoMetadata
from app.utils.validators import SourceInfo


@pytest.fixture
def m1(tmp_path, monkeypatch):
    settings = Settings(storage_root=tmp_path / "storage", database_url=f"sqlite:///{tmp_path / 'm1.db'}")
    sessions = create_database(settings.database_url)
    metadata = VideoMetadata(duration=6, width=540, height=960, fps=25, video_codec="h264", aspect_ratio="9:16")
    monkeypatch.setattr("app.services.storage_service.probe_video", lambda *args: metadata)
    project = import_video(io.BytesIO(b"unit-test-video"), "synthetic.mp4", SourceInfo(), settings, sessions, str(uuid4()))
    yield settings, sessions, project
    sessions.kw["bind"].dispose()
