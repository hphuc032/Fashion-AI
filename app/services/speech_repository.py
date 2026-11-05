import hashlib
import json
import math
from uuid import uuid4
from sqlalchemy import select
from app.database.speech_schema import SpeechSegment,SpeakerProfile,DubJob,ACTIVE
from app.services.ocr_repository import get_project,validate_id
from app.providers.tts.base import VoiceSettings
from app.utils.validators import UserError


def fingerprint(row):
    return hashlib.sha256(json.dumps([row.id,row.original_text,row.translated_text,row.start_time,row.end_time,row.speaker_id,row.review_status,row.revision],ensure_ascii=False).encode()).hexdigest()


def list_speech(sessions,project_id):
    validate_id(project_id)
    with sessions() as db:return list(db.scalars(select(SpeechSegment).where(SpeechSegment.project_id==project_id).order_by(SpeechSegment.start_time,SpeechSegment.id)))


def save_speech(sessions,project_id,edits):
    project=get_project(sessions,project_id)
    with sessions() as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE')
        if db.scalar(select(DubJob.id).where(DubJob.project_id==project_id,DubJob.kind=='asr',DubJob.status.in_(ACTIVE))):raise UserError('Chờ hoặc hủy ASR trước khi sửa lời.')
        seen=set()
        for edit in edits:
            key=validate_id(edit['id']);row=db.get(SpeechSegment,key)
            if not row or row.project_id!=project_id or key in seen or row.revision!=int(edit['revision']):raise UserError('Lời đã thay đổi hoặc không thuộc dự án; tải lại trước khi lưu.')
            seen.add(key)
            source=str(edit.get('original_text',row.original_text)).strip()
            text=str(edit.get('translated_text',row.translated_text)).strip()
            start=float(edit.get('start_time',row.start_time));end=float(edit.get('end_time',row.end_time))
            speaker=str(edit.get('speaker_id',row.speaker_id)).strip()
            status=edit.get('review_status',row.review_status)
            if not source or len(source)>1000 or len(text)>2000 or not speaker or len(speaker)>80 or not all(math.isfinite(x) for x in [start,end]) or not 0<=start<end<=project.duration or status not in {'pending','approved','rejected'} or (status=='approved' and not text):raise UserError('Nội dung/timing/speaker/duyệt lời không hợp lệ.')
            changed=(source,text,start,end,speaker)!=(row.original_text,row.translated_text,row.start_time,row.end_time,row.speaker_id)
            if changed and row.review_status=='approved':status='pending'
            if changed or status!=row.review_status:row.revision+=1
            row.original_text,row.translated_text,row.start_time,row.end_time,row.speaker_id,row.review_status=source,text,start,end,speaker,status
        db.commit()


def speaker_settings(sessions,project_id):
    with sessions() as db:return {s.speaker_label:VoiceSettings.model_validate(s.settings) for s in db.scalars(select(SpeakerProfile).where(SpeakerProfile.project_id==project_id))}


def save_speaker(sessions,project_id,label,voice):
    get_project(sessions,project_id)
    if not label.strip() or len(label)>80:raise UserError('Speaker không hợp lệ.')
    with sessions.begin() as db:
        row=db.scalar(select(SpeakerProfile).where(SpeakerProfile.project_id==project_id,SpeakerProfile.speaker_label==label))
        settings=voice.model_dump();settings['cloud_confirmed']=False
        if row:row.settings=settings
        else:db.add(SpeakerProfile(id=str(uuid4()),project_id=project_id,speaker_label=label,speaker_name=label,settings=settings))
