import hashlib
import json
from uuid import uuid4

from sqlalchemy import select,inspect,text

from app.database.m1_models import OCRDetection,TextSegment
from app.database.render_schema import ReplacementConfig
from app.services.ocr_repository import get_project,validate_id
from app.services.text_compositor import ReplacementSettings,valid_box
from app.utils.validators import UserError


def segment_fingerprint(segment):
    return hashlib.sha256(json.dumps([segment.source_text,segment.translated_text,segment.start_time,
                                     segment.end_time,segment.bounding_box,segment.revision,segment.review_status],ensure_ascii=False).encode()).hexdigest()


def assert_review_current(session,segment):
    # Optional Smart Review table: both independent PRs remain interoperable.
    if inspect(session.bind).has_table('segment_reviews'):
        row=session.execute(text('SELECT content_hash FROM segment_reviews WHERE segment_id=:id'),{'id':segment.id}).first()
        expected=hashlib.sha256(json.dumps([segment.source_text,segment.translated_text],ensure_ascii=False).encode()).hexdigest()
        if row and row[0]!=expected:
            raise UserError('Bản dịch đã thay đổi sau lần duyệt. Hãy duyệt lại trước khi render.')


def save_config(sessions,project_id,segment_id,config:ReplacementSettings,enabled=True):
    validate_id(segment_id)
    project=get_project(sessions,project_id)
    with sessions.begin() as session:
        segment=session.get(TextSegment,segment_id)
        if not segment or segment.project_id!=project_id:
            raise UserError('Đoạn chữ không thuộc dự án.')
        detection=session.scalar(select(OCRDetection).where(OCRDetection.segment_id==segment_id).limit(1))
        width,height=(detection.frame_width,detection.frame_height) if detection else (project.width,project.height)
        for box in (config.box_override,config.text_box):
            if box is not None: valid_box(box,width,height)
        if not 0 <= (config.start_time if config.start_time is not None else segment.start_time) < (config.end_time if config.end_time is not None else segment.end_time) <= project.duration:
            raise UserError('Khoảng thời gian render không hợp lệ.')
        row=session.scalar(select(ReplacementConfig).where(ReplacementConfig.project_id==project_id,ReplacementConfig.segment_id==segment_id))
        if row is None:
            row=ReplacementConfig(id=str(uuid4()),project_id=project_id,segment_id=segment_id,settings=config.model_dump(mode='json'),enabled=enabled)
            session.add(row)
        else:
            row.settings,row.enabled=config.model_dump(mode='json'),enabled
    return row


def list_configs(sessions,project_id):
    validate_id(project_id)
    with sessions() as session:
        return list(session.scalars(select(ReplacementConfig).where(ReplacementConfig.project_id==project_id)))


def snapshot_items(sessions,project_id):
    items=[]
    with sessions() as session:
        configs=list(session.scalars(select(ReplacementConfig).where(ReplacementConfig.project_id==project_id,ReplacementConfig.enabled==True)))
        for row in configs:
            segment=session.get(TextSegment,row.segment_id)
            config=ReplacementSettings.model_validate(row.settings)
            if not segment or segment.review_status=='rejected':
                continue
            if segment.review_status!='approved' and not config.allow_pending:
                continue
            if not segment.translated_text.strip():
                raise UserError('Đoạn được chọn chưa có bản dịch.')
            assert_review_current(session,segment)
            detections=list(session.scalars(select(OCRDetection).where(OCRDetection.segment_id==segment.id).order_by(OCRDetection.timestamp)))
            times=sorted({d.timestamp for d in detections})
            gaps=[b-a for a,b in zip(times,times[1:])]
            interval=min(gaps) if gaps else max(.1,segment.end_time-segment.start_time)
            items.append(dict(segment_id=segment.id,fingerprint=segment_fingerprint(segment),source=segment.source_text,
                              text=segment.translated_text,start=config.start_time if config.start_time is not None else segment.start_time,
                              end=config.end_time if config.end_time is not None else segment.end_time,box=segment.bounding_box,
                              tracking_gap=min(2.2,interval*1.1),settings=row.settings,
                              detections=[dict(time=d.timestamp,box=d.bounding_box,confidence=d.confidence) for d in detections]))
    return items


def validate_snapshot(sessions,items):
    with sessions() as session:
        for item in items:
            current=session.get(TextSegment,item['segment_id'])
            if not current or segment_fingerprint(current)!=item['fingerprint']:
                raise UserError('Nội dung/trạng thái đoạn đã thay đổi từ lúc tạo render. Hãy tạo tác vụ mới.')
            assert_review_current(session,current)
