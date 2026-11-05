"""Read-only M4 boundary: approved audio artifacts, never video muxing."""
import json
from sqlalchemy import select
from app.database.speech_schema import DubJob,SpeechSegment
from app.services.ocr_repository import project_source
from app.services.frame_extractor import source_hash
from app.services.storage_service import resolve_media
from app.services.dub_jobs import validate_items
from app.services.speech_repository import speaker_settings
from app.services.audio_extractor import audio_info
from app.utils.validators import UserError


def approved_dub(sessions,settings,project_id):
    project,source=project_source(sessions,project_id,settings)
    if project.rights_status not in {'owned','licensed','permission_granted'}:raise UserError('Quyền nguồn hiện chưa hợp lệ; không dùng audio đã xuất cho M4.')
    with sessions() as db:
        job=db.scalar(select(DubJob).where(DubJob.project_id==project_id,DubJob.kind=='assemble',DubJob.status=='COMPLETED').order_by(DubJob.created_at.desc()))
        if not job or not job.output_path:raise UserError('Chưa có audio lồng tiếng hoàn tất.')
        validate_items(db,job.config_snapshot['items'])
        current=list(db.scalars(select(SpeechSegment).where(SpeechSegment.project_id==project_id,SpeechSegment.review_status!='rejected')))
        if {s.id for s in current}!={s['id'] for s in job.config_snapshot['items']}:raise UserError('Danh sách lời thay đổi; cần ghép lại audio.')
    if source_hash(source)!=job.config_snapshot['source_hash']:raise UserError('Nguồn thay đổi; audio cũ không còn hợp lệ.')
    current_voices={k:v.model_dump() for k,v in speaker_settings(sessions,project_id).items()}
    if current_voices!=job.config_snapshot.get('speaker_settings',{}):raise UserError('Cấu hình speaker đã đổi; cần tạo lại audio.')
    output=resolve_media(settings.storage_root,job.output_path)
    manifest=output.parent/'manifest.json'
    if not output.is_file() or not manifest.is_file():raise UserError('Thiếu audio/manifest đã xuất.')
    data=json.loads(manifest.read_text(encoding='utf-8'))
    info=audio_info(output,settings)
    if not info or abs(info['duration']-project.duration)>1/24000 or source_hash(output)!=data.get('dubbed_sha256'):
        raise UserError('Audio đã xuất bị thay đổi hoặc sai timeline; tạo lại trước khi dùng.')
    for path in [data['original_audio'],data['dubbed_audio'],*[s['audio_path'] for s in data['audio_segments']],*[s['metadata_json']['raw_audio_path'] for s in data['audio_segments']]]:
        managed=resolve_media(settings.storage_root,path)
        if not managed.is_relative_to(resolve_media(settings.storage_root,f'projects/{project_id}/audio')) or not managed.is_file():
            raise UserError('Thiếu artifact audio thuộc dự án; tạo lại trước khi M4 sử dụng.')
    return data
