"""Opt-in actual models; never infer OCR accuracy from the mocked tests."""
import os
import time
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import load_settings
from app.database.session import create_database
from app.providers.translation.argos_provider import ArgosProvider
from app.services.ocr_repository import list_detections, list_segments, save_reviews
from app.services.ocr_service import latest_job, queue_job, request_cancel
from app.services.job_manager import JobManager
from app.services.storage_service import import_video
from app.utils.validators import SourceInfo
from scripts.generate_m1_fixture import generate_fixture


@pytest.mark.skipif(os.getenv("M1_RUN_REAL") != "1", reason="opt-in real PaddleOCR and Argos models: M1_RUN_REAL=1")
def test_real_chinese_video_ocr_translation_edit_reopen(tmp_path):
    settings = load_settings()
    settings.storage_root = tmp_path / "storage"
    settings.database_url = f"sqlite:///{tmp_path / 'real.db'}"
    settings.translation_provider = "argos"
    settings.ocr_sample_interval_seconds = 1
    font = Path(os.getenv("M1_CHINESE_FONT", str(Path(os.getenv("WINDIR", "")) / "Fonts" / "msyh.ttc")))
    assert font.is_file(), "Set M1_CHINESE_FONT to a font supporting Chinese"
    fixture = tmp_path / "chinese.mp4"
    generate_fixture(fixture, settings.ffmpeg_path, font)
    original = fixture.read_bytes()
    sessions = create_database(settings.database_url)
    manager = JobManager(settings, sessions)

    def execute(job):
        manager.launch(job)
        deadline = time.time() + 180
        while time.time() < deadline:
            state = latest_job(sessions, project.id)
            if state.status not in {"QUEUED", "PROCESSING"}:
                assert state.status == "COMPLETED", state.error_message
                return
            time.sleep(.2)
        pytest.fail("Real model worker timed out")
    started = time.perf_counter()
    with fixture.open("rb") as video:
        project = import_video(video, "chinese.mp4", SourceInfo(rights_status="owned"), settings, sessions, str(uuid4()))
    job = queue_job(sessions, settings, project.id)
    execute(job)
    assert latest_job(sessions, project.id).status == "COMPLETED", latest_job(sessions, project.id).error_message
    raw = list_detections(sessions, project.id)
    segments = list_segments(sessions, project.id)
    assert any("男生穿搭" == s.source_text for s in segments)
    assert any(d.source_text == "ABC 123" and d.segment_id is None for d in raw)
    first = next(s for s in segments if s.source_text == "男生穿搭")
    assert first.start_time == 0 and first.end_time >= 2
    assert all(0 <= d.timestamp < 6 and d.bounding_box[2] > 0 and d.frame_width == 540 and d.frame_height == 960 for d in raw)
    translation_job = queue_job(sessions, settings, project.id, kind="translate", selected_ids=[s.id for s in segments])
    execute(translation_job)
    assert latest_job(sessions, project.id).status == "COMPLETED", latest_job(sessions, project.id).error_message
    translated = list_segments(sessions, project.id)
    assert all(s.translated_text and s.review_status == "pending" for s in translated)
    assert next(s for s in translated if s.id == first.id).translated_text == "Phối đồ nam"
    # Bypass the phrase dictionary to prove an actual neural model was executed.
    neural = ArgosProvider(settings.argos_models_dir, use_glossary=False).translate("我喜欢这件衬衫", "fashion")
    assert "thích" in neural.lower() and "áo" in neural.lower()
    reviewed = next(s for s in translated if s.id == first.id)
    save_reviews(sessions, project.id, [{"id": reviewed.id, "revision": reviewed.revision,
                                      "translated_text": "Phối đồ nam — đã kiểm tra", "review_status": "approved"}])
    # Exercise real process cancellation during a rerun, preserving reviewed rows.
    cancelled = queue_job(sessions, settings, project.id, replace_existing=True)
    manager.launch(cancelled)
    deadline = time.time() + 10
    while latest_job(sessions, project.id).status == "QUEUED" and time.time() < deadline:
        time.sleep(.02)
    request_cancel(sessions, cancelled.id)
    deadline = time.time() + 10
    while latest_job(sessions, project.id).status in {"QUEUED", "PROCESSING"} and time.time() < deadline:
        time.sleep(.05)
    assert latest_job(sessions, project.id).status == "CANCELLED"
    manager.close()
    sessions.kw["bind"].dispose()
    reopened = create_database(settings.database_url)
    saved = next(s for s in list_segments(reopened, project.id) if s.id == first.id)
    assert saved.translated_text == "Phối đồ nam — đã kiểm tra" and saved.review_status == "approved"
    assert (settings.storage_root / project.file_path).read_bytes() == original
    print({"real_detections": len(raw), "real_segments": len(segments), "neural_translation": neural,
           "elapsed_seconds": round(time.perf_counter() - started, 2)})
    reopened.kw["bind"].dispose()
