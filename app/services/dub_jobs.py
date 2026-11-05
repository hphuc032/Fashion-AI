import json
import logging
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4
from sqlalchemy import select,update,delete
from sqlalchemy.exc import IntegrityError
from app.core.config import ROOT,Settings
from app.database.models import Project,utc_now
from app.database.speech_schema import DubJob,SpeechSegment,DubbedAudioSegment,ACTIVE
from app.providers.tts.base import VoiceSettings,make_tts
from app.services.ocr_repository import project_source,validate_id
from app.services.frame_extractor import source_hash,Cancelled
from app.services.speech_repository import list_speech,fingerprint,speaker_settings
from app.services.storage_service import resolve_media
from app.services.workload_guard import ensure_idle
from app.services.audio_extractor import extract_audio,audio_info,ffmpeg
from app.services.dubbing_service import transcribe,translate_speech,generate_audio,synthesize_cached
from app.utils.validators import UserError

log=logging.getLogger('fashion_ai.dubbing')


def history(sessions,project_id):
    validate_id(project_id)
    with sessions() as db:return list(db.scalars(select(DubJob).where(DubJob.project_id==project_id).order_by(DubJob.created_at.desc())))


def queue_dub(sessions,settings,project_id,token,kind,selected_ids=None,voice=None,replace_existing=False,rights_confirmed=False,preview_text='Xin chào, đây là giọng đọc tiếng Việt.'):
    validate_id(token)
    if kind not in {'asr','translate','tts','assemble','preview'}:raise UserError('Loại tác vụ audio không hỗ trợ.')
    with sessions() as db:
        old=db.scalar(select(DubJob).where(DubJob.request_token==token))
        if old:
            if old.project_id!=project_id:raise UserError('Token không thuộc dự án.')
            return old
    project,source=project_source(sessions,project_id,settings)
    rows=list_speech(sessions,project_id)
    ids=list(dict.fromkeys(selected_ids or []))
    selected=[s for s in rows if s.id in ids]
    if kind=='asr' and rows and not replace_existing:raise UserError('Xác nhận thay transcript trước khi chạy lại ASR; bản dịch sẽ chỉ thay khi ASR thành công.')
    if kind in {'tts','translate'} and (not ids or len(selected)!=len(ids)):raise UserError('Chọn đoạn lời thuộc dự án.')
    if kind=='translate' and any(s.review_status=='approved' for s in selected):raise UserError('Chuyển đoạn đã duyệt về pending trước khi dịch lại.')
    if kind=='translate' and sum(len(s.original_text) for s in selected)>settings.translation_max_characters:raise UserError('Chọn ít đoạn hơn; vượt giới hạn dịch.')
    if kind=='assemble':
        if not rights_confirmed or project.rights_status not in {'owned','licensed','permission_granted'}:raise UserError('Cần quyền nguồn hợp lệ và xác nhận trước khi xuất audio.')
        if any(s.review_status=='pending' for s in rows):raise UserError('Duyệt hoặc loại bỏ mọi đoạn pending trước khi ghép toàn bộ lời.')
        selected=[s for s in rows if s.review_status=='approved']
        if not rows and not any(j.kind=='asr' and j.status=='COMPLETED' for j in history(sessions,project_id)):raise UserError('Chạy ASR trước khi tạo timeline im lặng.')
    if kind in {'tts','assemble'} and any(s.review_status!='approved' or not s.translated_text.strip() for s in selected):raise UserError('TTS chỉ dùng lời Việt đã duyệt.')
    if len(selected)>settings.dub_max_segments:raise UserError('Vượt giới hạn số đoạn lời.')
    voice=voice or VoiceSettings(provider=settings.tts_provider)
    overrides=speaker_settings(sessions,project_id)
    items=[]
    for row in selected:
        chosen=overrides.get(row.speaker_id,voice).model_copy()
        if chosen.provider=='azure':chosen.cloud_confirmed=voice.cloud_confirmed
        items.append({k:getattr(row,k) for k in ('id','original_text','translated_text','start_time','end_time','speaker_id','revision','asr_provider','confidence')}|{'fingerprint':fingerprint(row),'voice':chosen.model_dump()})
    if len(preview_text)>200 or not preview_text.strip():raise UserError('Preview cần1–200 ký tự.')
    config={'settings':settings.model_dump(mode='json'),'items':items,'voice':voice.model_dump(),'speaker_settings':{k:v.model_dump() for k,v in overrides.items()},'source_hash':source_hash(source),
            'rights_status':project.rights_status,'rights_confirmed':rights_confirmed,'preview_text':preview_text}
    job=DubJob(id=str(uuid4()),project_id=project_id,request_token=token,kind=kind,config_snapshot=config,lease_expires=time.time()+settings.dub_timeout_seconds)
    try:
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            ensure_idle(db,exclude='dub_jobs')
            db.add(job);db.commit()
    except IntegrityError as exc:raise UserError('Đang có tác vụ lồng tiếng khác hoặc yêu cầu trùng; chờ/hủy trước.') from exc
    return job


def validate_items(db,items):
    for item in items:
        row=db.get(SpeechSegment,item['id'])
        if not row or fingerprint(row)!=item['fingerprint']:raise UserError('Transcript/bản duyệt thay đổi sau khi tạo job; tạo lại để tránh xuất lời cũ.')


def run_dub(sessions,job_id,asr_factory=None,tts_factory=make_tts,translator_factory=None):
    validate_id(job_id)
    with sessions.begin() as db:
        if not db.execute(update(DubJob).where(DubJob.id==job_id,DubJob.status=='QUEUED').values(status='EXTRACTING_AUDIO',pid=os.getpid())).rowcount:return
    with sessions() as db:job=db.get(DubJob,job_id)
    settings=Settings.model_validate(job.config_snapshot['settings'])
    folder=resolve_media(settings.storage_root,f'projects/{job.project_id}/audio/jobs/{job.id}')
    folder.mkdir(parents=True,exist_ok=True)
    validated=[0.]
    def check():
        with sessions() as db:
            current=db.get(DubJob,job.id)
            if current.status not in ACTIVE or current.cancel_requested:raise Cancelled('Đã hủy audio; giữ nguyên nguồn/kết quả trước.')
            if time.time()>current.lease_expires:raise UserError('Tác vụ audio quá thời gian.')
            if time.monotonic()-validated[0]>.3:
                validate_items(db,job.config_snapshot['items']);validated[0]=time.monotonic()
    def progress(stage,value):
        check()
        with sessions.begin() as db:db.execute(update(DubJob).where(DubJob.id==job.id,DubJob.status.in_(ACTIVE)).values(status=stage,progress=min(.99,value)))
    output=None
    try:
        check()
        project,source=project_source(sessions,job.project_id,settings)
        if source_hash(source)!=job.config_snapshot['source_hash']:raise UserError('Nguồn đã thay đổi; tạo tác vụ mới.')
        items=job.config_snapshot['items'];records=[];phrases=None;translations=None
        if job.kind=='asr':
            kwargs={'provider_factory':asr_factory} if asr_factory else {}
            phrases,identity,original=transcribe(sessions,settings,project,folder,check,progress,**kwargs)
        elif job.kind=='translate':
            progress('TRANSLATING',.05)
            kwargs={'translator_factory':translator_factory} if translator_factory else {}
            translations=translate_speech(sessions,settings,items,check,progress,**kwargs)
        elif job.kind=='preview':
            progress('GENERATING_TTS',.1)
            voice=VoiceSettings.model_validate(job.config_snapshot['voice'])
            provider=tts_factory(settings,voice)
            raw=synthesize_cached(sessions,settings,job.project_id,job.config_snapshot['preview_text'],voice,provider,check)
            output=folder/'preview.wav'
            ffmpeg(settings,['-i',raw,'-af',f'loudnorm=I=-20:TP=-2:LRA=7,volume={voice.volume},alimiter=limit=0.89:level=disabled','-ar','24000','-ac','1','-c:a','pcm_s16le',output],check)
        else:
            extract_audio(sessions,settings,project.id,check)
            records,output=generate_audio(sessions,settings,job,project,folder,items,check,progress,tts_factory)
        check()
        if source_hash(source)!=job.config_snapshot['source_hash']:raise UserError('Nguồn đổi trong khi xử lý audio.')
        with sessions() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            current=db.get(DubJob,job.id)
            if current.cancel_requested or current.status not in ACTIVE:raise Cancelled('Đã hủy trước khi lưu audio.')
            validate_items(db,items)
            if job.kind=='asr':
                db.execute(delete(SpeechSegment).where(SpeechSegment.project_id==project.id))
                for phrase in phrases:
                    db.add(SpeechSegment(id=str(uuid4()),project_id=project.id,start_time=phrase.start,end_time=phrase.end,original_text=phrase.text,
                                         speaker_id=phrase.speaker,asr_provider=identity,confidence=phrase.confidence))
            if translations:
                for item,text,flags in translations:
                    row=db.get(SpeechSegment,item['id']);row.translated_text=text;row.review_status='pending';row.warnings=flags;row.revision+=1
            if job.kind=='assemble' and db.get(Project,project.id).rights_status!=job.config_snapshot['rights_status']:raise UserError('Quyền nguồn thay đổi; tạo lại audio.')
            for record in records:db.add(DubbedAudioSegment(**record))
            if output:
                info=audio_info(output,settings)
                if not info:raise UserError('Đầu ra audio không hợp lệ.')
                if job.kind=='assemble':
                    final=folder/'dub.wav';output.replace(final);output=final
                    manifest={'version':1,'project_id':project.id,'job_id':job.id,'original_audio':extract_audio(sessions,settings,project.id,check)[0].relative_to(settings.storage_root).as_posix(),
                              'dubbed_audio':output.relative_to(settings.storage_root).as_posix(),'dubbed_sha256':source_hash(output),'duration':info['duration'],'sample_rate':info['sample_rate'],
                              'segments':items,'audio_segments':records,'config':job.config_snapshot['voice'],'processing_config':settings.model_dump(mode='json'),'source_hash':job.config_snapshot['source_hash']}
                    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
                current.output_path=output.relative_to(settings.storage_root).as_posix();current.output_duration=info['duration']
            current.status,current.progress,current.completed_at='COMPLETED',1,utc_now()
            db.commit()
    except Exception as exc:
        for path in folder.glob('*'):
            if path.is_file():path.unlink(missing_ok=True)
        with sessions.begin() as db:
            row=db.get(DubJob,job.id)
            if row.status in ACTIVE:
                row.status='CANCELLED' if isinstance(exc,Cancelled) or row.cancel_requested else 'FAILED'
                row.error_message=str(exc) if isinstance(exc,UserError) else 'Tác vụ audio lỗi; kiểm tra model/provider/dung lượng và thử lại.'
                row.completed_at=utc_now()
        log.warning('dub_failed job_id=%s type=%s',job.id,type(exc).__name__)


def cancel(sessions,job_id):
    validate_id(job_id)
    with sessions.begin() as db:db.execute(update(DubJob).where(DubJob.id==job_id,DubJob.status.in_(ACTIVE)).values(cancel_requested=True))


class DubManager:
    def __init__(self,settings,sessions):
        self.settings,self.sessions=settings,sessions
        self.children={};self.lock=threading.Lock();self.stopped=threading.Event()
        self.thread=threading.Thread(target=self.monitor,daemon=True);self.thread.start()

    def launch(self,job):
        with self.lock:
            if job.id in self.children:return
            folder=self.settings.storage_root/'logs';folder.mkdir(parents=True,exist_ok=True)
            env=os.environ.copy();env.update(PYTHONUTF8='1',HF_HUB_OFFLINE='1',MODELSCOPE_OFFLINE='1',OMP_NUM_THREADS='2')
            try:
                with (folder/f'dub-{job.id}.log').open('ab') as stream:
                    child=subprocess.Popen([sys.executable,'-m','app.dub_worker','--job',job.id,'--database-url',self.settings.database_url],cwd=ROOT,env=env,
                                           stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,shell=False,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.children[job.id]=child
            except OSError as exc:
                with self.sessions.begin() as db:db.execute(update(DubJob).where(DubJob.id==job.id,DubJob.status=='QUEUED').values(status='FAILED',error_message='Không mở được worker audio.'))
                raise UserError('Không mở được worker audio.') from exc

    def monitor(self):
        import psutil
        while not self.stopped.wait(.5):
            try:
                with self.sessions() as db:jobs=list(db.scalars(select(DubJob).where(DubJob.status.in_(ACTIVE))))
                for job in jobs:
                    process=None
                    try:
                        candidate=psutil.Process(job.pid) if job.pid else None
                        if candidate and 'app.dub_worker' in candidate.cmdline() and job.id in candidate.cmdline():process=candidate
                    except (psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess):pass
                    if job.cancel_requested or time.time()>job.lease_expires or (job.status!='QUEUED' and process is None):
                        if process:
                            descendants=process.children(recursive=True)
                            for child in descendants:child.terminate()
                            _,alive=psutil.wait_procs(descendants,timeout=3)
                            for child in alive:child.kill()
                            psutil.wait_procs(alive,timeout=3)
                            process.terminate()
                            try:process.wait(timeout=3)
                            except psutil.TimeoutExpired:process.kill();process.wait(timeout=3)
                        with self.sessions.begin() as db:db.execute(update(DubJob).where(DubJob.id==job.id,DubJob.status.in_(ACTIVE)).values(status='CANCELLED' if job.cancel_requested else 'FAILED',completed_at=utc_now(),error_message='Worker audio dừng/hủy/quá thời gian; kết quả trước giữ nguyên.'))
                        folder=resolve_media(self.settings.storage_root,f'projects/{job.project_id}/audio/jobs/{job.id}')
                        for path in folder.glob('*.partial.wav'):path.unlink(missing_ok=True)
                with self.lock:
                    for key,child in list(self.children.items()):
                        if child.poll() is not None:
                            with self.sessions.begin() as db:db.execute(update(DubJob).where(DubJob.id==key,DubJob.status.in_(ACTIVE),((DubJob.pid==child.pid)|(DubJob.status=='QUEUED'))).values(status='FAILED',completed_at=utc_now(),error_message='Worker audio dừng đột ngột.'))
                            self.children.pop(key)
            except Exception as exc:log.warning('dub_supervisor type=%s',type(exc).__name__)

    def close(self):self.stopped.set();self.thread.join(timeout=2)
