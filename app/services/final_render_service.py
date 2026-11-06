"""Completed M2/M3 orchestration, preview gate, jobs and final export library."""
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from uuid import uuid4
from sqlalchemy import select,update
from sqlalchemy.exc import IntegrityError
from app.core.config import Settings
from app.database.models import Project,utc_now
from app.database.speech_schema import DubJob
from app.database.final_schema import FinalRenderJob,FinalExport,SubtitleFile,ACTIVE
from app.services.ocr_repository import project_source,validate_id
from app.services.frame_extractor import source_hash,Cancelled
from app.services.storage_service import resolve_media
from app.services.workload_guard import ensure_idle
from app.services.replacement_contract import localized_video
from app.services.dubbing_contract import approved_dub
from app.services.dub_jobs import validate_items
from app.services.replacement_repository import validate_snapshot
from app.services.audio_extractor import audio_info
from app.services.final_render_config import FinalRenderConfig
from app.services.subtitle_service import generate_ass
from app.services.video_mux_service import timeline_options,run_mux
from app.services.final_output_validation import validate_output
from app.utils.validators import UserError

log=logging.getLogger('fashion_ai.final')


def available_background(sessions,settings,project_id):
    project,source=project_source(sessions,project_id,settings)
    root=resolve_media(settings.storage_root,f'projects/{project_id}/audio/separated')
    manifest=root/'background.json'
    if not manifest.is_file():return None
    try:
        data=json.loads(manifest.read_text(encoding='utf-8'));path=resolve_media(settings.storage_root,data['file_path'])
        if data['project_id']!=project_id or not data['dialogue_removed'] or not data['rights_confirmed'] or not data['provider'] or data['source_sha256']!=source_hash(source):raise ValueError()
        if not path.is_relative_to(root) or not path.is_file() or source_hash(path)!=data['sha256']:raise ValueError()
        info=audio_info(path,settings)
        if not info or abs(info['duration']-project.duration)>.05:raise ValueError()
        return data
    except (KeyError,ValueError,TypeError,UserError) as exc:raise UserError('Background tách riêng thiếu provenance/quyền/SHA/timeline hợp lệ; không trộn audio gốc.') from exc


def retrieve_inputs(sessions,settings,project_id,config):
    project,source=project_source(sessions,project_id,settings)
    m2=localized_video(sessions,settings,project_id);m3=approved_dub(sessions,settings,project_id)
    validate_id(m3['job_id'])
    expected=f"projects/{project_id}/audio/jobs/{m3['job_id']}/dub.wav"
    with sessions() as db:dub=db.get(DubJob,m3['job_id'])
    if m3.get('project_id')!=project_id or m3.get('dubbed_audio')!=expected or not dub or dub.project_id!=project_id or dub.status!='COMPLETED' or dub.output_path!=expected:
        raise UserError('Contract audio M3 không khớp dự án/job đã hoàn tất.')
    if m2['project_id']!=project_id:raise UserError('Video M2 không thuộc dự án.')
    bg=None
    if config.background_path:
        bg=available_background(sessions,settings,project_id)
        if not bg or bg['file_path']!=config.background_path:raise UserError('Không có background tách riêng hợp lệ để trộn. Chọn chỉ giọng Việt.')
    info=audio_info(resolve_media(settings.storage_root,m3['dubbed_audio']),settings)
    return {'project_id':project_id,'project_duration':project.duration,'rights_status':project.rights_status,'source_sha256':source_hash(source),
            'm2':m2,'m3':m3,'audio_info':info,'background':bg}


def signature(inputs,config):
    payload={'m2_job':inputs['m2']['job_id'],'m2_sha':inputs['m2']['sha256'],'m2_items':inputs['m2']['replacement_items'],
             'm3':inputs['m3'],'source':inputs['source_sha256'],'rights':inputs['rights_status'],'background':inputs['background'],
             'config':config.model_dump(mode='json',exclude={'preview_start','preview_seconds'})}
    return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def final_history(sessions,project_id):
    validate_id(project_id)
    with sessions() as db:return list(db.scalars(select(FinalRenderJob).where(FinalRenderJob.project_id==project_id).order_by(FinalRenderJob.created_at.desc())))


def queue_final(sessions,settings,project_id,token,config=None,is_preview=False,rights_confirmed=False,preview_reviewed=False):
    validate_id(token);config=config or FinalRenderConfig()
    with sessions() as db:
        existing=db.scalar(select(FinalRenderJob).where(FinalRenderJob.request_token==token))
        if existing:
            if existing.project_id!=project_id:raise UserError('Token không thuộc dự án.')
            return existing
    if not is_preview and (not rights_confirmed or not preview_reviewed):raise UserError('Xác nhận quyền và đã xem preview trước khi xuất cuối.')
    if not is_preview and config.preset=='compact':raise UserError('Compact dành cho preview; chọn Original/TikTok để xuất cuối.')
    inputs=retrieve_inputs(sessions,settings,project_id,config);key=signature(inputs,config)
    options=timeline_options(resolve_media(settings.storage_root,inputs['m2']['path']),resolve_media(settings.storage_root,inputs['m3']['dubbed_audio']),inputs['project_duration'],config,settings,is_preview)
    if is_preview:
        for old in final_history(sessions,project_id):
            if old.is_preview and old.status=='COMPLETED' and old.cache_key==key and old.render_config==config.model_dump(mode='json') and old.output_path and resolve_media(settings.storage_root,old.output_path).is_file():return old
    else:
        previews=[j for j in final_history(sessions,project_id) if j.is_preview and j.status=='COMPLETED' and j.cache_key==key and j.output_path and resolve_media(settings.storage_root,j.output_path).is_file()]
        if not previews:raise UserError('Cần tạo/xem preview đúng cấu hình và nguồn hiện tại trước khi xuất cuối.')
    snapshot={'settings':settings.model_dump(mode='json'),'artifacts':inputs,'options':options,'rights_confirmed':rights_confirmed,'preview_reviewed':preview_reviewed}
    job=FinalRenderJob(id=str(uuid4()),project_id=project_id,request_token=token,is_preview=is_preview,cache_key=key,render_config=config.model_dump(mode='json'),inputs=snapshot,
                       lease_expires=time.time()+settings.final_timeout_seconds)
    try:
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE');ensure_idle(db,exclude='final_render_jobs');db.add(job);db.commit()
    except IntegrityError as exc:raise UserError('Đang có final render khác hoặc yêu cầu trùng; chờ/hủy trước.') from exc
    return job


def cleanup_staging(folder,failed=False):
    # Caller supplies only its validated UUID job directory, never an input root.
    for name in ['final.partial.mp4','progress.txt','soft-bridge.srt','validation-output.wav','validation-reference.wav','validation-frame.png','validation-reference.png']:
        (folder/name).unlink(missing_ok=True)
    fonts=folder/'fonts'
    if fonts.is_dir():
        for path in fonts.iterdir():
            if path.is_file():path.unlink(missing_ok=True)
        fonts.rmdir()
    if failed:
        for name in ['final.mp4','subtitles.ass','report.json']:(folder/name).unlink(missing_ok=True)


def run_final(sessions,job_id,muxer=run_mux,validator=validate_output):
    validate_id(job_id)
    with sessions.begin() as db:
        if not db.execute(update(FinalRenderJob).where(FinalRenderJob.id==job_id,FinalRenderJob.status=='QUEUED').values(status='PREPARING',pid=os.getpid(),started_at=utc_now())).rowcount:return
    with sessions() as db:job=db.get(FinalRenderJob,job_id)
    settings=Settings.model_validate(job.inputs['settings']);config=FinalRenderConfig.model_validate(job.render_config)
    inputs=job.inputs['artifacts'];options=job.inputs['options']
    folder=resolve_media(settings.storage_root,f'projects/{job.project_id}/final/{job.id}');folder.mkdir(parents=True,exist_ok=True)
    last=[0.];published=False
    def check():
        validate=False
        with sessions() as db:
            row=db.get(FinalRenderJob,job.id)
            if row.status not in ACTIVE or row.cancel_requested:raise Cancelled('Đã hủy final render; giữ nguyên đầu vào và các bản xuất trước.')
            if time.time()>row.lease_expires:raise UserError('Final render quá thời gian.')
            if db.get(Project,job.project_id).rights_status!=inputs['rights_status']:raise UserError('Quyền nguồn đã thay đổi.')
            if time.monotonic()-last[0]>.5:
                validate_items(db,inputs['m3']['segments']);last[0]=time.monotonic();validate=True
        if validate:validate_snapshot(sessions,inputs['m2']['replacement_items'])
    def progress(stage,value):
        check()
        with sessions.begin() as db:db.execute(update(FinalRenderJob).where(FinalRenderJob.id==job.id,FinalRenderJob.status.in_(ACTIVE)).values(status=stage,progress=min(.99,max(0,value))))
    try:
        check()
        fresh=retrieve_inputs(sessions,settings,job.project_id,config)
        if signature(fresh,config)!=job.cache_key:raise UserError('Nguồn/config đầu vào đã đổi; tạo job mới.')
        video=resolve_media(settings.storage_root,inputs['m2']['path']);audio=resolve_media(settings.storage_root,inputs['m3']['dubbed_audio'])
        bg=resolve_media(settings.storage_root,inputs['background']['file_path']) if inputs['background'] else None
        ass=folder/'subtitles.ass';partial=folder/'final.partial.mp4';final=folder/'final.mp4'
        progress('GENERATING_SUBTITLES',.08)
        window=(options['start'],options['start']+options['duration'])
        subtitle_segments=inputs['m3']['segments'] if config.subtitle_mode!='none' else []
        subtitles=generate_ass(subtitle_segments,ass,options['width'],options['height'],inputs['project_duration'],config.style,config.speaker_styles,
                               window,config.readability_confirmed,soft=config.subtitle_mode=='soft')
        progress('MUXING',.15)
        mux_report=muxer(video,audio,ass,partial,options,config,settings,subtitles,bg,check,lambda v:progress('MUXING',.15+.65*v))
        progress('VALIDATING',.82)
        validation=validator(partial,video,audio,options,config,subtitles,settings,bg,check)
        check()
        if signature(retrieve_inputs(sessions,settings,job.project_id,config),config)!=job.cache_key:raise UserError('Artifact/duyệt/config thay đổi trong lúc render; không công bố output cũ.')
        digest=source_hash(partial)
        report={'project_id':job.project_id,'job_id':job.id,'is_preview':job.is_preview,'render_config':job.render_config,'mux':mux_report,'validation':validation,
                'subtitles':subtitles,'sha256':digest,'exported_at':utc_now().isoformat(),'input_m2_job':inputs['m2']['job_id'],'input_m3_job':inputs['m3']['job_id']}
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE');current=db.get(FinalRenderJob,job.id)
            if current.cancel_requested or current.status not in ACTIVE:raise Cancelled('Hủy trước khi công bố final output.')
            validate_items(db,inputs['m3']['segments'])
            from app.database.m1_models import TextSegment
            from app.database.render_schema import ReplacementConfig
            from app.services.replacement_repository import segment_fingerprint
            selected={i['segment_id']:i for i in inputs['m2']['replacement_items']}
            for item in selected.values():
                segment=db.get(TextSegment,item['segment_id'])
                if not segment or segment_fingerprint(segment)!=item['fingerprint']:raise UserError('Lời M2 đã thay đổi trước khi công bố.')
            current_configs=list(db.scalars(select(ReplacementConfig).where(ReplacementConfig.project_id==job.project_id,ReplacementConfig.enabled==True)))
            current_selected={}
            for row in current_configs:
                segment=db.get(TextSegment,row.segment_id)
                if segment and segment.review_status!='rejected' and (segment.review_status=='approved' or row.settings.get('allow_pending')):current_selected[row.segment_id]=row.settings
            if current_selected!={key:item['settings'] for key,item in selected.items()}:raise UserError('Cấu hình M2 đã đổi trước khi công bố.')
            if db.get(Project,job.project_id).rights_status!=inputs['rights_status']:raise UserError('Quyền nguồn thay đổi trước khi công bố.')
            partial.replace(final)
            current.output_path=final.relative_to(settings.storage_root).as_posix();current.status='COMPLETED';current.progress=1;current.completed_at=utc_now();current.report=report
            (folder/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            db.add(SubtitleFile(id=str(uuid4()),project_id=job.project_id,job_id=job.id,file_path=ass.relative_to(settings.storage_root).as_posix(),subtitle_mode=config.subtitle_mode,style_config=config.style.model_dump(mode='json'),report=subtitles))
            if not job.is_preview:
                m=validation['metadata']
                db.add(FinalExport(id=str(uuid4()),project_id=job.project_id,render_job_id=job.id,filename=f'{job.project_id}_vi_{job.id[:8]}.mp4',file_path=current.output_path,
                                   file_size=final.stat().st_size,duration=m['duration'],width=m['width'],height=m['height'],sha256=digest))
            db.commit()
        published=True
        try:
            cleanup_staging(folder)
            if job.is_preview:prune_previews(sessions,settings,job.project_id,job.id)
        except OSError as exc:log.warning('final_cache_cleanup job_id=%s type=%s',job.id,type(exc).__name__)
    except Exception as exc:
        if published:
            log.warning('final_post_publish job_id=%s type=%s',job.id,type(exc).__name__);return
        cleanup_staging(folder,failed=True)
        with sessions.begin() as db:
            row=db.get(FinalRenderJob,job.id)
            if row.status in ACTIVE:
                row.status='CANCELLED' if isinstance(exc,Cancelled) or row.cancel_requested else 'FAILED';row.completed_at=utc_now()
                row.error_message=str(exc) if isinstance(exc,UserError) else 'Final render lỗi. Kiểm tra FFmpeg/font/artifacts/dung lượng rồi thử lại.'
        log.warning('final_failed job_id=%s type=%s',job.id,type(exc).__name__)


def prune_previews(sessions,settings,project_id,current_id):
    jobs=[j for j in final_history(sessions,project_id) if j.is_preview and j.status=='COMPLETED' and j.id!=current_id]
    for job in jobs[max(0,settings.final_preview_cache_entries-1):]:
        if job.output_path:
            expected=resolve_media(settings.storage_root,f'projects/{project_id}/final/{job.id}/final.mp4')
            if resolve_media(settings.storage_root,job.output_path)==expected:expected.unlink(missing_ok=True)


def cancel_final(sessions,job_id):
    validate_id(job_id)
    with sessions.begin() as db:db.execute(update(FinalRenderJob).where(FinalRenderJob.id==job_id,FinalRenderJob.status.in_(ACTIVE)).values(cancel_requested=True))


def exports(sessions,project_id,include_deleted=False):
    validate_id(project_id)
    with sessions() as db:
        query=select(FinalExport).where(FinalExport.project_id==project_id)
        if not include_deleted:query=query.where(FinalExport.deleted_at.is_(None))
        return list(db.scalars(query.order_by(FinalExport.created_at.desc())))


def move_export(sessions,settings,project_id,export_id,confirmed=False,restore=False):
    validate_id(export_id)
    if not confirmed:raise UserError('Cần xác nhận chuyển thùng rác/khôi phục bản xuất.')
    with sessions() as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE');row=db.get(FinalExport,export_id)
        if not row or row.project_id!=project_id:raise UserError('Bản xuất không thuộc dự án.')
        expected=resolve_media(settings.storage_root,f'projects/{project_id}/final/{row.render_job_id}/final.mp4')
        if resolve_media(settings.storage_root,row.file_path)!=expected:raise UserError('Đường dẫn export không hợp lệ.')
        trash=resolve_media(settings.storage_root,f'projects/{project_id}/final/.trash/{row.id}.mp4')
        source,target=(trash,expected) if restore else (expected,trash)
        if not source.is_file() or target.exists():raise UserError('Tệp nguồn thiếu hoặc đích đã tồn tại; không ghi đè.')
        target.parent.mkdir(parents=True,exist_ok=True);source.replace(target)
        try:row.deleted_at=None if restore else utc_now();db.commit()
        except Exception:target.replace(source);raise


def export_contract(sessions,settings,project_id,export_id):
    validate_id(export_id)
    with sessions() as db:
        row=db.get(FinalExport,export_id)
        if not row or row.project_id!=project_id or row.deleted_at:raise UserError('Bản xuất bị thiếu/đã chuyển thùng rác hoặc không thuộc dự án.')
        job=db.get(FinalRenderJob,row.render_job_id)
    if not job or job.status!='COMPLETED' or job.is_preview:raise UserError('Final render chưa hoàn tất.')
    path=resolve_media(settings.storage_root,row.file_path)
    if path!=resolve_media(settings.storage_root,f'projects/{project_id}/final/{job.id}/final.mp4') or not path.is_file() or path.stat().st_size!=row.file_size or source_hash(path)!=row.sha256:
        raise UserError('Bản xuất đã thay đổi/hỏng/mất; không dùng output không hợp lệ.')
    metadata=job.report['validation']['metadata']
    return {'project_id':project_id,'export_id':row.id,'final_mp4_path':row.file_path,'filename':row.filename,'file_size':row.file_size,'sha256':row.sha256,
            'duration':row.duration,'resolution':[row.width,row.height],'aspect_ratio':metadata['aspect_ratio'],'video_codec':metadata['video_codec'],'audio_codec':metadata['audio_codec'],
            'subtitle_mode':job.render_config['subtitle_mode'],'subtitle_language':metadata['subtitle_language'],'audio_sync_report':job.report['validation']['audio_sync'],
            'ffprobe_validation':metadata,'render_config':job.render_config,'export_timestamp':row.created_at.isoformat(),'validated_when_rendered':True}
