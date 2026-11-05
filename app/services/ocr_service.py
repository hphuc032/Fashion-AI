"""Persisted OCR/translation orchestration, independent from Streamlit."""
import logging
import os
import time
from dataclasses import asdict
from uuid import uuid4

from sqlalchemy import delete, select, update, inspect, text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.database.m1_models import OCRDetection, OCRJob, TextSegment
from app.providers.ocr.paddle_provider import PaddleProvider
from app.services.frame_extractor import Cancelled, extract_frames, sample_times, source_hash
from app.services.ocr_repository import list_segments, project_source, validate_id
from app.services.text_tracker import group_detections
from app.services.translation_service import TranslationService
from app.utils.validators import UserError

log = logging.getLogger("fashion_ai.ocr")
ACTIVE = ("QUEUED", "PROCESSING")


def latest_job(sessions, project_id):
    validate_id(project_id)
    with sessions() as session:
        return session.scalar(select(OCRJob).where(OCRJob.project_id == project_id).order_by(OCRJob.created_at.desc()))


def queue_job(sessions, settings: Settings, project_id: str, kind="ocr", selected_ids=None, replace_existing=False):
    project, _ = project_source(sessions, project_id, settings)
    if settings.translation_provider not in {"manual", "argos"} or kind not in {"ocr", "translate"}:
        raise UserError("Cấu hình tác vụ hoặc nhà cung cấp không được hỗ trợ.")
    segments = list_segments(sessions, project_id)
    ids = list(dict.fromkeys(selected_ids or []))
    if kind == "ocr" and segments and not replace_existing:
        raise UserError("Dự án đã có bản dịch. Xác nhận thay kết quả trước khi chạy lại OCR.")
    if kind == "translate":
        selected = [s for s in segments if s.id in ids]
        if not ids or len(selected) != len(ids) or any(s.review_status == "approved" for s in selected):
            raise UserError("Chỉ chọn các đoạn thuộc dự án chưa được duyệt; chuyển về chờ duyệt nếu cần dịch lại.")
        if settings.translation_provider == "manual":
            raise UserError("Chọn Argos để dịch tự động hoặc nhập bản dịch thủ công.")
        if sum(len(s.source_text) for s in selected) > settings.translation_max_characters:
            raise UserError("Vượt giới hạn ký tự một lượt dịch. Chọn ít đoạn hơn.")
    total = len(sample_times(project.duration, settings.ocr_sample_interval_seconds, settings.ocr_max_frames)) if kind == "ocr" else len(ids)
    job = OCRJob(id=str(uuid4()), project_id=project_id, kind=kind, status="QUEUED", total_frames=total,
                 config={"settings": settings.model_dump(mode="json"), "selected_ids": ids,
                         "replace_existing": replace_existing}, lease_expires=time.time() + settings.job_timeout_seconds)
    try:
        with sessions() as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            # Optional M2 schema: serialize both queues without coupling M1 to M2.
            if inspect(session.bind).has_table('render_jobs') and session.execute(
                    text("SELECT id FROM render_jobs WHERE status IN ('QUEUED','PROCESSING') LIMIT 1")).first():
                raise UserError('Chờ render hoàn tất hoặc hủy trước khi chạy OCR/dịch.')
            session.add(job)
            session.commit()
    except IntegrityError as exc:
        raise UserError("Đang có một tác vụ OCR/dịch khác. Chờ hoàn tất hoặc hủy trước khi chạy tiếp.") from exc
    return job


def request_cancel(sessions, job_id):
    validate_id(job_id)
    with sessions.begin() as session:
        job = session.get(OCRJob, job_id)
        if job and job.status in ACTIVE:
            job.cancel_requested = True


def run_job(sessions, job_id: str, provider_factory=PaddleProvider, extractor=extract_frames,
            translator_factory=TranslationService):
    """Exactly one process wins QUEUED→PROCESSING. Commit outputs all-or-nothing."""
    validate_id(job_id)
    with sessions.begin() as session:
        claimed = session.execute(update(OCRJob).where(OCRJob.id == job_id, OCRJob.status == "QUEUED")
                                  .values(status="PROCESSING", pid=os.getpid(), stage="loading"))
        if not claimed.rowcount:
            return
    with sessions() as session:
        job = session.get(OCRJob, job_id)
    settings = Settings.model_validate(job.config["settings"])

    def check_cancel():
        with sessions() as session:
            current = session.get(OCRJob, job_id)
            if current is None or current.status != "PROCESSING" or current.cancel_requested:
                raise Cancelled("Tác vụ đã được hủy. Kết quả trước đó được giữ nguyên.")
            if time.time() > current.lease_expires:
                raise UserError("Tác vụ quá giới hạn thời gian. Hãy giảm số khung hình rồi thử lại.")

    def progress(done, stage):
        check_cancel()
        with sessions.begin() as session:
            session.execute(update(OCRJob).where(OCRJob.id == job_id, OCRJob.status == "PROCESSING")
                            .values(completed_frames=done, stage=stage))

    try:
        check_cancel()
        project, path = project_source(sessions, job.project_id, settings)
        if job.kind == "ocr":
            initial_hash = source_hash(path)
            provider = provider_factory(settings)
            detections = []
            for frame in extractor(path, project.id, project.duration, settings, check_cancel):
                found = provider.detect(frame)
                if len(found) > 200 or len(detections) + len(found) > 20000:
                    raise UserError("Quá nhiều vùng chữ. Giảm số khung hình rồi thử lại.")
                detections.extend(found)
                progress(frame.index + 1, "ocr")
            segments = group_detections(detections, settings.ocr_sample_interval_seconds, project.duration,
                                        settings.ocr_min_confidence, settings.ocr_similarity_threshold, settings.ocr_iou_threshold)
            if source_hash(path) != initial_hash:
                raise UserError("Video gốc đã thay đổi trong khi OCR. Kết quả chưa được lưu.")
            check_cancel()
            # Commit complete OCR output. Translation is a separate explicit job,
            # so a missing translation model never loses valid OCR or human edits.
            with sessions.begin() as session:
                current = session.get(OCRJob, job_id)
                if current.status != "PROCESSING" or current.cancel_requested:
                    raise Cancelled("Tác vụ đã hủy trước khi lưu kết quả.")
                session.execute(delete(OCRDetection).where(OCRDetection.project_id == project.id))
                session.execute(delete(TextSegment).where(TextSegment.project_id == project.id))
                for segment in segments:
                    values = asdict(segment)
                    values.pop("last_time")
                    session.add(TextSegment(project_id=project.id, job_id=job_id, **values))
                session.flush()
                for detection in detections:
                    session.add(OCRDetection(project_id=project.id, job_id=job_id, **asdict(detection)))
                current.status, current.stage = "COMPLETED", "completed"
                if len(sample_times(project.duration, settings.ocr_sample_interval_seconds, 100000)) > settings.ocr_max_frames:
                    current.warning_message = "Đã chạm giới hạn khung hình; phần cuối video chưa được quét."
            log.info("ocr_completed job_id=%s segments=%d", job_id, len(segments))
        else:
            translator = translator_factory(settings, sessions)
            segments = [s for s in list_segments(sessions, project.id) if s.id in job.config["selected_ids"]]
            results = []
            for index, segment in enumerate(segments):
                translated, identity = translator.translate(segment.source_text, check_cancel)
                results.append((segment.id, segment.revision, translated, identity))
                progress(index + 1, "translation")
            check_cancel()
            with sessions.begin() as session:
                current = session.get(OCRJob, job_id)
                if current.status != "PROCESSING" or current.cancel_requested:
                    raise Cancelled("Tác vụ đã hủy trước khi lưu bản dịch.")
                for segment_id, revision, translated, identity in results:
                    updated = session.execute(update(TextSegment).where(TextSegment.id == segment_id,
                                                    TextSegment.project_id == project.id, TextSegment.revision == revision,
                                                    TextSegment.review_status != "approved")
                                              .values(translated_text=translated, translation_provider=identity,
                                                      review_status="pending", translation_error=None, revision=revision + 1))
                    if not updated.rowcount:
                        raise UserError("Một đoạn đã được sửa/duyệt trong khi dịch. Không ghi đè; hãy chọn lại các đoạn cần dịch.")
                current.status, current.stage = "COMPLETED", "completed"
    except Exception as exc:
        state = "CANCELLED" if isinstance(exc, Cancelled) else "FAILED"
        message = str(exc) if isinstance(exc, UserError) else "Tác vụ gặp lỗi. Kiểm tra mô hình, bộ nhớ và thử lại."
        with sessions.begin() as session:
            session.execute(update(OCRJob).where(OCRJob.id == job_id, OCRJob.status.in_(ACTIVE))
                            .values(status=state, stage=state.lower(), error_message=message))
        log.warning("job_finished job_id=%s state=%s type=%s", job_id, state, type(exc).__name__)
