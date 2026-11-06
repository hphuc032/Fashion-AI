"""Read-only M2 contract; no second replacement pipeline or source fallback."""
import json
from sqlalchemy import select
from app.database.render_schema import RenderJob
from app.services.ocr_repository import project_source
from app.services.replacement_repository import snapshot_items,validate_snapshot
from app.services.frame_extractor import source_hash
from app.services.storage_service import resolve_media
from app.services.video_service import probe_video
from app.utils.validators import UserError


def localized_video(sessions,settings,project_id):
    project,source=project_source(sessions,project_id,settings)
    with sessions() as db:job=db.scalar(select(RenderJob).where(RenderJob.project_id==project_id,RenderJob.status=='COMPLETED').order_by(RenderJob.created_at.desc()))
    if not job or not job.output_path:raise UserError('Chưa có M2 render hoàn tất thuộc dự án; xuất video trong Text Replacement Studio trước.')
    path=resolve_media(settings.storage_root,job.output_path)
    expected=resolve_media(settings.storage_root,f'projects/{project_id}/exports/{project_id}_vi_{job.id}.mp4')
    if path!=expected or not path.is_file():raise UserError('Thiếu video M2 hợp lệ thuộc dự án.')
    if source_hash(source)!=job.config_snapshot.get('source_hash'):raise UserError('Nguồn đã đổi; cần render lại M2.')
    items=job.config_snapshot['items'];validate_snapshot(sessions,items)
    canonical=lambda rows:json.dumps(sorted(rows,key=lambda x:x['segment_id']),sort_keys=True,ensure_ascii=False)
    if canonical(snapshot_items(sessions,project_id))!=canonical(items):raise UserError('Cấu hình/lời đã đổi; cần render lại M2 trước khi xuất cuối.')
    metadata=probe_video(path,settings.ffprobe_path,'.mp4')
    if metadata.video_codec!='h264' or abs(metadata.duration-project.duration)>max(.12,2/metadata.fps):raise UserError('Video M2 không đạt codec/timeline; cần tạo lại.')
    return {'project_id':project_id,'job_id':job.id,'path':job.output_path,'sha256':source_hash(path),'metadata':metadata.model_dump(),'replacement_items':items}
