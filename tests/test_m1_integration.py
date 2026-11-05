import time
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.database.models import Project
from app.database.m1_models import OCRJob, TextSegment
from app.database.session import create_database
from app.services.frame_extractor import SampledFrame
from app.services.job_manager import reconcile_jobs
from app.services.ocr_repository import list_detections, list_segments, save_reviews
from app.services.ocr_service import latest_job, queue_job, request_cancel, run_job
from app.services.text_tracker import Detection
from app.services.translation_service import TranslationService
from app.utils.validators import UserError


class FakeOCR:
    def __init__(self, _settings):
        pass
    def detect(self, frame):
        return [Detection("男生穿搭", .98, [20, 100, 200, 50], [[20, 100], [220, 100], [220, 150], [20, 150]],
                          frame.timestamp, frame.index, 540, 960),
                Detection("ABC 123", .9, [20, 200, 200, 40], [[20, 200], [220, 200], [220, 240], [20, 240]],
                          frame.timestamp, frame.index, 540, 960)]


def fake_frames(path, project_id, duration, settings, check_cancel):
    for i in range(6):
        check_cancel()
        yield SampledFrame(i, float(i), path, 540, 960, 540, 960)


def detect_fixture(m1):
    settings, sessions, project = m1
    job = queue_job(sessions, settings, project.id)
    run_job(sessions, job.id, provider_factory=FakeOCR, extractor=fake_frames)
    assert latest_job(sessions, project.id).status == "COMPLETED"
    return list_segments(sessions, project.id)[0]


def test_pipeline_raw_results_review_and_restart(m1):
    settings, sessions, project = m1
    segment = detect_fixture(m1)
    assert len(list_detections(sessions, project.id)) == 12
    assert len(list_segments(sessions, project.id)) == 1
    assert segment.start_time == 0 and segment.end_time == 6
    save_reviews(sessions, project.id, [{"id": segment.id, "revision": 0,
                                      "translated_text": "Phối đồ nam có dấu Việt", "review_status": "approved"}])
    reopened = create_database(settings.database_url)
    stored = list_segments(reopened, project.id)[0]
    assert stored.translated_text == "Phối đồ nam có dấu Việt"
    assert stored.review_status == "approved" and stored.revision == 1 and stored.translation_provider == "manual"
    assert (settings.storage_root / project.file_path).read_bytes() == b"unit-test-video"
    reopened.kw["bind"].dispose()


def test_translation_job_and_cache(m1):
    settings, sessions, project = m1
    segment = detect_fixture(m1)
    settings.translation_provider = "argos"
    class Provider:
        identity = "fake-neural-v1"
        def translate(self, text, context):
            return "Phối đồ nam"
    factory = lambda s, db: TranslationService(s, db, provider=Provider())
    job = queue_job(sessions, settings, project.id, kind="translate", selected_ids=[segment.id])
    run_job(sessions, job.id, translator_factory=factory)
    assert latest_job(sessions, project.id).status == "COMPLETED"
    stored = list_segments(sessions, project.id)[0]
    assert stored.translated_text == "Phối đồ nam" and stored.review_status == "pending"


def test_single_active_job_and_safe_rerun(m1):
    settings, sessions, project = m1
    job = queue_job(sessions, settings, project.id)
    with pytest.raises(UserError, match="tác vụ"):
        queue_job(sessions, settings, project.id)
    run_job(sessions, job.id, provider_factory=FakeOCR, extractor=fake_frames)
    original = list_segments(sessions, project.id)[0].id
    run_job(sessions, job.id, provider_factory=FakeOCR, extractor=fake_frames)
    assert list_segments(sessions, project.id)[0].id == original
    with pytest.raises(UserError, match="Xác nhận"):
        queue_job(sessions, settings, project.id)


def test_cancellation_and_failed_retry_preserve_old_results(m1):
    settings, sessions, project = m1
    segment = detect_fixture(m1)
    cancelled = queue_job(sessions, settings, project.id, replace_existing=True)
    request_cancel(sessions, cancelled.id)
    run_job(sessions, cancelled.id, provider_factory=FakeOCR, extractor=fake_frames)
    assert latest_job(sessions, project.id).status == "CANCELLED"
    assert list_segments(sessions, project.id)[0].id == segment.id
    failed = queue_job(sessions, settings, project.id, replace_existing=True)
    class BrokenOCR(FakeOCR):
        def detect(self, frame):
            raise RuntimeError("not user-visible private diagnostic")
    run_job(sessions, failed.id, provider_factory=BrokenOCR, extractor=fake_frames)
    stored_job = latest_job(sessions, project.id)
    assert stored_job.status == "FAILED" and "private" not in stored_job.error_message
    assert list_segments(sessions, project.id)[0].id == segment.id
    retry = queue_job(sessions, settings, project.id, replace_existing=True)
    run_job(sessions, retry.id, provider_factory=FakeOCR, extractor=fake_frames)
    assert latest_job(sessions, project.id).status == "COMPLETED"


def test_stale_translation_cannot_overwrite_human_edit(m1):
    settings, sessions, project = m1
    segment = detect_fixture(m1)
    settings.translation_provider = "argos"
    class ConcurrentEditor:
        def translate(self, text, check_cancel):
            save_reviews(sessions, project.id, [{"id": segment.id, "revision": 0, "translated_text": "Bản sửa tay", "review_status": "approved"}])
            return "Machine output", "fake"
    job = queue_job(sessions, settings, project.id, kind="translate", selected_ids=[segment.id])
    run_job(sessions, job.id, translator_factory=lambda *args: ConcurrentEditor())
    assert latest_job(sessions, project.id).status == "FAILED"
    assert list_segments(sessions, project.id)[0].translated_text == "Bản sửa tay"


@pytest.mark.parametrize("edit", [{"review_status": "approved"}, {"end_time": 99}, {"start_time": -1},
                                  {"bounding_box": [0, 0, 999, 40]}, {"review_status": "invalid"}, {"revision": 99}])
def test_bad_reviews_are_atomic(m1, edit):
    _, sessions, project = m1
    segment = detect_fixture(m1)
    with pytest.raises(UserError):
        save_reviews(sessions, project.id, [{"id": segment.id, "revision": 0, **edit}])
    assert list_segments(sessions, project.id)[0].revision == 0


def test_foreign_key_integrity(m1):
    _, sessions, _ = m1
    with pytest.raises(IntegrityError), sessions.begin() as session:
        session.add(OCRJob(id=str(uuid4()), project_id=str(uuid4()), config={}))


def test_expired_and_dead_jobs_recovered(m1):
    settings, sessions, project = m1
    job = queue_job(sessions, settings, project.id)
    reconcile_jobs(sessions, now=job.lease_expires + 1)
    assert latest_job(sessions, project.id).status == "FAILED"
    retry = queue_job(sessions, settings, project.id)
    with sessions.begin() as session:
        row = session.get(OCRJob, retry.id)
        row.status, row.pid = "PROCESSING", 999999999
    reconcile_jobs(sessions)
    assert latest_job(sessions, project.id).status == "FAILED"


def test_approved_rows_and_foreign_project_rejected(m1):
    settings, sessions, project = m1
    segment = detect_fixture(m1)
    save_reviews(sessions, project.id, [{"id": segment.id, "revision": 0, "translated_text": "Đã duyệt", "review_status": "approved"}])
    settings.translation_provider = "argos"
    with pytest.raises(UserError):
        queue_job(sessions, settings, project.id, kind="translate", selected_ids=[segment.id])
    with pytest.raises(UserError):
        queue_job(sessions, settings, "../invalid")


def test_additive_migration_preserves_old_m0_database(tmp_path):
    path = tmp_path / "legacy.db"
    url = f"sqlite:///{path}"
    old_engine = create_engine(url)
    Project.__table__.create(old_engine)
    old_columns = [c["name"] for c in inspect(old_engine).get_columns("projects")]
    legacy = Project(id=str(uuid4()), upload_token=str(uuid4()), original_filename="Áo.mp4", stored_filename="safe.mp4",
                     file_path="projects/test/source/safe.mp4", file_size=123, duration=1, width=9, height=16,
                     fps=25, video_codec="h264", aspect_ratio="9:16", rights_status="owned", status="imported")
    with sessionmaker(old_engine, expire_on_commit=False).begin() as session:
        session.add(legacy)
    old_engine.dispose()
    sessions = create_database(url)
    with sessions() as session:
        row = session.get(Project, legacy.id)
        assert row.original_filename == "Áo.mp4" and row.rights_status == "owned" and row.file_size == 123
    assert [c["name"] for c in inspect(sessions.kw["bind"]).get_columns("projects")] == old_columns
    backups = list(tmp_path.glob("legacy.pre-m1-*.db"))
    assert len(backups) == 1
    reopened = create_database(url)
    assert len(list(tmp_path.glob("legacy.pre-m1-*.db"))) == 1
    reopened.kw["bind"].dispose()
    sessions.kw["bind"].dispose()
