"""Conservative local heuristics: structural validity is not semantic proof."""
import hashlib
import json
import math
import re
from dataclasses import dataclass

from sqlalchemy import select

from app.core.config import Settings
from app.database.m1_models import OCRJob, TextSegment
from app.database.review_schema import ReviewEvent, ReviewState
from app.database.models import utc_now
from app.providers.translation.argos_provider import FASHION_TERMS
from app.services.ocr_repository import validate_id
from app.services.text_tracker import contains_chinese, normalized
from app.utils.validators import UserError


def content_hash(segment):
    return hashlib.sha256(json.dumps([segment.source_text, segment.translated_text], ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Evaluation:
    eligible: bool
    score: float
    reasons: list[str]


def evaluate(source, translated, confidence, provider_error=None, settings=None):
    settings = settings or Settings()
    source, translated = normalized(source), normalized(translated)
    reasons = []
    if not settings.auto_review_require_translation_check:
        reasons.append("Kiểm tra nghĩa chưa bật; chỉ cho phép duyệt tay")
    if not math.isfinite(confidence) or confidence < settings.auto_review_ocr_high_threshold:
        reasons.append("OCR thấp; cần kiểm tra" if confidence >= settings.auto_review_ocr_low_threshold else "OCR quá thấp; bắt buộc kiểm tra")
    if not source or not contains_chinese(source):
        reasons.append("Nguồn không phải chữ Trung hợp lệ")
    if not translated or translated == source:
        reasons.append("Bản dịch trống hoặc chưa dịch")
    if contains_chinese(translated):
        reasons.append("Còn chữ Trung trong bản dịch")
    if translated and (len(translated) < max(3, len(source) * .3) or len(translated) > max(40, len(source) * 12)):
        reasons.append("Độ dài bản dịch bất thường")
    if sorted(re.findall(r"\d+(?:[.,]\d+)?", source)) != sorted(re.findall(r"\d+(?:[.,]\d+)?", translated)):
        reasons.append("Số, giá hoặc kích thước thay đổi")
    identifiers = re.findall(r"[A-Za-z][A-Za-z0-9_-]*", source)
    if any(token.lower() not in translated.lower() for token in identifiers):
        reasons.append("Có thể mất thương hiệu hoặc mã sản phẩm")
    words = translated.lower().split()
    if len(words) >= 4 and (len(set(words)) <= len(words) / 3 or any(words[i:i+2] == words[i+2:i+4] for i in range(len(words)-3))):
        reasons.append("Bản dịch lặp bất thường")
    if re.search(r"cam kết|100%|chính hãng|giảm giá|tốt nhất|miễn phí|chữa|bảo hành", translated, re.I):
        reasons.append("Có khẳng định sản phẩm cần người kiểm tra")
    if provider_error:
        reasons.append("Nhà cung cấp dịch báo lỗi")
    # Unknown neural output cannot be semantically certified by length/numbers.
    if FASHION_TERMS.get(source) != translated:
        reasons.append("Chưa có bằng chứng đối chiếu nghĩa tin cậy; cần duyệt tay")
    return Evaluation(not reasons, 100.0 if not reasons else max(0.0, 80 - len(reasons) * 15), reasons or ["Khớp thuật ngữ đã kiểm chứng và mọi kiểm tra đạt"])


def effective_state(segment, state=None):
    if segment.review_status == "rejected":
        return "REJECTED"
    if state and state.content_hash != content_hash(segment):
        return "NEEDS_REVIEW"
    if segment.review_status == "approved":
        return "AUTO_APPROVED" if state and state.state == "AUTO_APPROVED" else "MANUALLY_APPROVED"
    return "NEEDS_REVIEW" if state and state.state == "NEEDS_REVIEW" else "PENDING"


def record(session, segment, state, mode, method, score, reasons):
    digest = content_hash(segment)
    current = session.get(ReviewState, segment.id)
    values = dict(state=state, mode=mode, method=method, score=score, reasons=reasons, content_hash=digest)
    if current and all(getattr(current, k) == v for k, v in values.items()):
        return False
    if current is None:
        current = ReviewState(segment_id=segment.id, **values)
        session.add(current)
    else:
        for key, value in values.items():
            setattr(current, key, value)
        current.reviewed_at = utc_now()
    session.add(ReviewEvent(project_id=segment.project_id, segment_id=segment.id, segment_key=segment.id, **values))
    return True


def record_editor_action(session, segment):
    state = {"approved": "MANUALLY_APPROVED", "rejected": "REJECTED", "pending": "PENDING"}[segment.review_status]
    record(session, segment, state, "manual", "manual", 0, ["Người dùng lưu chỉnh sửa / trạng thái"])


def review_batch(sessions, project_id, selections, action, settings, confirmed=False, progress=lambda done,total: None):
    validate_id(project_id)
    if action not in {"smart", "approve_all", "approve_selected", "revert"}:
        raise UserError("Thao tác duyệt không hợp lệ.")
    if len(selections) > settings.auto_review_max_batch_size or len({s['id'] for s in selections}) != len(selections):
        raise UserError("Lượt duyệt vượt giới hạn hoặc trùng đoạn.")
    if action.startswith("approve") and not confirmed:
        raise UserError("Cần xác nhận trước khi duyệt hàng loạt; thao tác này bỏ qua kiểm tra chất lượng.")
    if action == "smart" and not settings.auto_review_enabled:
        raise UserError("Tự động duyệt đang tắt trong cấu hình.")
    counts = {"changed": 0, "unchanged": 0, "failed": 0}
    with sessions() as session:
        session.connection().exec_driver_sql("BEGIN IMMEDIATE")
        try:
            if session.scalar(select(OCRJob.id).where(OCRJob.project_id == project_id, OCRJob.status.in_(["QUEUED","PROCESSING"]))):
                raise UserError("Chờ hoặc hủy tác vụ trước khi duyệt hàng loạt.")
            for index, selected in enumerate(selections):
                segment = session.get(TextSegment, validate_id(selected['id']))
                if segment is None or segment.project_id != project_id or segment.revision != selected['revision']:
                    counts['failed'] += 1
                elif segment.review_status == "rejected" and action != "revert":
                    counts['unchanged'] += 1
                else:
                    old = segment.review_status
                    result = evaluate(segment.source_text, segment.translated_text, segment.confidence, segment.translation_error, settings)
                    if action == "smart":
                        if old == "approved":
                            counts['unchanged'] += 1
                            progress(index+1,len(selections))
                            continue
                        state = "AUTO_APPROVED" if result.eligible else "NEEDS_REVIEW"
                        segment.review_status = "approved" if result.eligible else "pending"
                    elif action == "revert":
                        state, segment.review_status = "PENDING", "pending"
                    elif not segment.translated_text.strip():
                        counts['failed'] += 1
                        progress(index+1,len(selections))
                        continue
                    else:
                        state, segment.review_status = "MANUALLY_APPROVED", "approved"
                    changed = record(session, segment, state, "smart" if action == "smart" else "approve_all" if action == "approve_all" else "manual", "automatic" if action == "smart" else "manual", result.score, result.reasons)
                    if changed or old != segment.review_status:
                        segment.revision += 1
                        counts['changed'] += 1
                    else:
                        counts['unchanged'] += 1
                progress(index+1,len(selections))
            session.commit()
        except Exception:
            session.rollback()
            raise
    return counts
