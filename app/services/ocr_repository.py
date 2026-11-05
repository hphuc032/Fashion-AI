"""Project-scoped reads and optimistic, transactional human review edits."""
import math
from uuid import UUID

from sqlalchemy import select

from app.database.models import Project
from app.database.m1_models import OCRDetection, OCRJob, TextSegment
from app.services.storage_service import resolve_media
from app.utils.validators import UserError


def validate_id(value: str) -> str:
    try:
        if str(UUID(value)) != value:
            raise ValueError()
        return value
    except (ValueError, TypeError, AttributeError) as exc:
        raise UserError("Mã dự án hoặc đoạn văn bản không hợp lệ.") from exc


def get_project(sessions, project_id: str) -> Project:
    validate_id(project_id)
    with sessions() as session:
        project = session.get(Project, project_id)
        if project is None:
            raise UserError("Không tìm thấy dự án.")
        return project


def project_source(sessions, project_id: str, settings):
    project = get_project(sessions, project_id)
    path = resolve_media(settings.storage_root, project.file_path)
    expected = resolve_media(settings.storage_root, f"projects/{project.id}/source/{project.stored_filename}")
    if path != expected or not path.is_file() or path.stat().st_size != project.file_size:
        raise UserError("Video gốc bị thiếu, thay đổi hoặc không thuộc kho dự án.")
    return project, path


def list_segments(sessions, project_id: str) -> list[TextSegment]:
    validate_id(project_id)
    with sessions() as session:
        return list(session.scalars(select(TextSegment).where(TextSegment.project_id == project_id)
                                   .order_by(TextSegment.start_time, TextSegment.id)))


def list_detections(sessions, project_id: str) -> list[OCRDetection]:
    validate_id(project_id)
    with sessions() as session:
        return list(session.scalars(select(OCRDetection).where(OCRDetection.project_id == project_id)
                                   .order_by(OCRDetection.timestamp, OCRDetection.id)))


def save_reviews(sessions, project_id: str, edits: list[dict]) -> None:
    project = get_project(sessions, project_id)
    with sessions() as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            if session.scalar(select(OCRJob.id).where(OCRJob.project_id == project_id, OCRJob.kind == "ocr",
                                                     OCRJob.status.in_(["QUEUED", "PROCESSING"]))):
                raise UserError("Hãy chờ hoặc hủy OCR trước khi lưu chỉnh sửa.")
            seen = set()
            for edit in edits:
                segment_id = validate_id(edit["id"])
                segment = session.get(TextSegment, segment_id)
                if segment is None or segment.project_id != project_id or segment_id in seen:
                    raise UserError("Đoạn văn bản không thuộc dự án hoặc bị trùng.")
                seen.add(segment_id)
                if segment.revision != int(edit["revision"]):
                    raise UserError("Kết quả đã thay đổi ở cửa sổ/tác vụ khác. Tải lại rồi sửa lại để tránh ghi đè.")
                status = edit.get("review_status", segment.review_status)
                translated = str(edit.get("translated_text", segment.translated_text)).strip()
                source = str(edit.get("source_text", segment.source_text)).strip()
                start = float(edit.get("start_time", segment.start_time))
                end = float(edit.get("end_time", segment.end_time))
                box = list(edit.get("bounding_box", segment.bounding_box))
                detection = session.scalar(select(OCRDetection).where(OCRDetection.segment_id == segment.id).limit(1))
                width = detection.frame_width if detection else project.width
                height = detection.frame_height if detection else project.height
                if (status not in {"pending", "approved", "rejected"} or not source or len(source) > 1000
                        or len(translated) > 2000 or (status == "approved" and not translated)
                        or not all(math.isfinite(v) for v in (start, end)) or not 0 <= start < end <= project.duration
                        or len(box) != 4 or not all(isinstance(v, (int, float)) and math.isfinite(v) and int(v) == v for v in box)):
                    raise UserError("Nội dung, thời gian hoặc trạng thái duyệt không hợp lệ; đoạn được duyệt phải có bản dịch.")
                x, y, w, h = box
                if not (0 <= x < width and 0 <= y < height and w > 0 and h > 0 and x + w <= width and y + h <= height):
                    raise UserError("Khung chữ phải nằm bên trong kích thước video gốc.")
                if translated != segment.translated_text or source != segment.source_text:
                    if segment.review_status == "approved":
                        status = "pending"
                    segment.translation_provider = "manual"
                    segment.translation_error = None
                segment.source_text, segment.translated_text = source, translated
                segment.start_time, segment.end_time = start, end
                segment.bounding_box = [int(v) for v in box]
                segment.review_status = status
                segment.revision += 1
            session.commit()
        except Exception:
            session.rollback()
            raise
