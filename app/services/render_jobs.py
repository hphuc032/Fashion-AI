import logging
import os
import subprocess
import sys
import threading
import time
from uuid import uuid4

from sqlalchemy import select,update
from sqlalchemy.exc import IntegrityError

from app.core.config import ROOT,Settings
from app.database.models import utc_now
from app.database.m1_models import OCRJob
from app.database.render_schema import RenderJob
from app.services.frame_extractor import Cancelled,source_hash
from app.services.ocr_repository import project_source,validate_id
from app.services.replacement_repository import snapshot_items,validate_snapshot
from app.services.storage_service import resolve_media
from app.services.video_renderer import render_video
from app.utils.validators import UserError

log=logging.getLogger('fashion_ai.render')
ACTIVE=('QUEUED','PROCESSING')


def render_history(sessions,project_id):
    validate_id(project_id)
    with sessions() as session:
        return list(session.scalars(select(RenderJob).where(RenderJob.project_id==project_id).order_by(RenderJob.created_at.desc())))


def queue_render(sessions,settings,project_id,token,rights_confirmed=False,regions_confirmed=False,quality='balanced'):
    validate_id(token)
    with sessions() as session:
        existing=session.scalar(select(RenderJob).where(RenderJob.request_token==token))
        if existing:
            if existing.project_id!=project_id: raise UserError('Token không thuộc dự án.')
            return existing
    project,path=project_source(sessions,project_id,settings)
    if not rights_confirmed or project.rights_status not in {'owned','licensed','permission_granted'}:
        raise UserError('Cần xác nhận quyền sử dụng hợp lệ trước khi xuất. Dự án unknown chưa được xuất.')
    if not regions_confirmed:
        raise UserError('Xác nhận chỉ thay caption được phép, không che dấu sở hữu/nguồn tác giả.')
    items=snapshot_items(sessions,project_id)
    if not items:
        raise UserError('Chưa có cấu hình được bật với bản dịch đã duyệt (hoặc chọn rõ bản pending).')
    snapshot={'settings':settings.model_dump(mode='json'),'items':items,'source_hash':source_hash(path),'quality':quality,
              'rights_status':project.rights_status,'rights_confirmed':True,'regions_confirmed':True}
    job=RenderJob(id=str(uuid4()),project_id=project_id,request_token=token,config_snapshot=snapshot,
                  lease_expires=time.time()+settings.render_timeout_seconds,status='QUEUED')
    try:
        with sessions() as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            from app.services.workload_guard import ensure_idle
            ensure_idle(session,exclude='render_jobs')
            if session.scalar(select(OCRJob.id).where(OCRJob.status.in_(ACTIVE))):
                raise UserError('Chờ OCR/dịch hoàn tất trước khi render.')
            session.add(job)
            session.commit()
    except IntegrityError as exc:
        raise UserError('Đang có render khác hoặc yêu cầu đã được gửi. Chờ hoàn tất hoặc hủy.') from exc
    return job


def run_render(sessions,job_id,renderer=render_video):
    validate_id(job_id)
    with sessions.begin() as session:
        if not session.execute(update(RenderJob).where(RenderJob.id==job_id,RenderJob.status=='QUEUED')
                               .values(status='PROCESSING',pid=os.getpid(),started_at=utc_now())).rowcount:
            return
    with sessions() as session: job=session.get(RenderJob,job_id)
    settings=Settings.model_validate(job.config_snapshot['settings'])
    folder=resolve_media(settings.storage_root,f'projects/{job.project_id}/exports')
    folder.mkdir(parents=True,exist_ok=True)
    partial=folder/f'{job_id}.partial.mp4'
    final=folder/f'{job.project_id}_vi_{job_id}.mp4'
    last_validation=[0.0]

    def check():
        with sessions() as session:
            row=session.get(RenderJob,job_id)
            if row.status!='PROCESSING' or row.cancel_requested: raise Cancelled('Render đã hủy; bản gốc và các lần xuất trước giữ nguyên.')
            if time.time()>row.lease_expires: raise UserError('Render quá thời gian cho phép.')
        if time.monotonic()-last_validation[0]>.5:
            validate_snapshot(sessions,job.config_snapshot['items'])
            last_validation[0]=time.monotonic()

    def progress(value):
        with sessions.begin() as session:
            session.execute(update(RenderJob).where(RenderJob.id==job_id,RenderJob.status=='PROCESSING').values(progress=min(.99,value)))

    try:
        check()
        project,path=project_source(sessions,job.project_id,settings)
        if project.rights_status!=job.config_snapshot['rights_status'] or source_hash(path)!=job.config_snapshot['source_hash']:
            raise UserError('Nguồn hoặc thông tin quyền đã thay đổi; tạo render mới.')
        renderer(path,partial,job.config_snapshot['items'],settings,job.config_snapshot['quality'],check,progress)
        check()
        if source_hash(path)!=job.config_snapshot['source_hash']:
            raise UserError('Video nguồn đã thay đổi trong lúc render.')
        with sessions() as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            current=session.get(RenderJob,job_id)
            if current.cancel_requested or current.status!='PROCESSING': raise Cancelled('Render đã hủy trước khi công bố.')
            from app.database.models import Project
            if session.get(Project,job.project_id).rights_status!=job.config_snapshot['rights_status']:
                raise UserError('Quyền sử dụng đã thay đổi trong lúc render.')
            # Check source text/review again under the final publication lock.
            from app.services.replacement_repository import segment_fingerprint
            from app.database.m1_models import TextSegment
            for item in job.config_snapshot['items']:
                row=session.get(TextSegment,item['segment_id'])
                if not row or segment_fingerprint(row)!=item['fingerprint']: raise UserError('Bản dịch đã đổi; không công bố render cũ.')
            partial.replace(final)
            current.status,current.progress,current.output_path,current.completed_at='COMPLETED',1,final.relative_to(settings.storage_root).as_posix(),utc_now()
            session.commit()
    except Exception as exc:
        partial.unlink(missing_ok=True)
        # This UUID belongs only to this attempt; never touch an earlier export.
        final.unlink(missing_ok=True)
        with sessions.begin() as session:
            current=session.get(RenderJob,job_id)
            cancelled=isinstance(exc,Cancelled) or bool(current and current.cancel_requested)
            session.execute(update(RenderJob).where(RenderJob.id==job_id,RenderJob.status.in_(ACTIVE))
                            .values(status='CANCELLED' if cancelled else 'FAILED',completed_at=utc_now(),
                                    error_message=str(exc) if isinstance(exc,UserError) else 'Render gặp lỗi. Kiểm tra font/FFmpeg/dung lượng và thử lại.'))
        log.warning('render_failed job_id=%s type=%s',job_id,type(exc).__name__)
    finally:
        partial.unlink(missing_ok=True)


def cancel_render(sessions,job_id):
    validate_id(job_id)
    with sessions.begin() as session:
        session.execute(update(RenderJob).where(RenderJob.id==job_id,RenderJob.status.in_(ACTIVE)).values(cancel_requested=True))


class RenderManager:
    def __init__(self,settings,sessions):
        self.settings,self.sessions=settings,sessions
        self.children={}
        self.lock=threading.Lock()
        self.stopped=threading.Event()
        self.thread=threading.Thread(target=self.monitor,daemon=True)
        self.thread.start()

    def launch(self,job):
        with self.lock:
            if job.id in self.children: return
            folder=self.settings.storage_root/'logs'
            folder.mkdir(parents=True,exist_ok=True)
            try:
                with (folder/f'render-{job.id}.log').open('ab') as stream:
                    process=subprocess.Popen([sys.executable,'-m','app.render_worker','--job',job.id,'--database-url',self.settings.database_url],
                                             cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,shell=False,
                                             creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except OSError as exc:
                with self.sessions.begin() as session:
                    session.execute(update(RenderJob).where(RenderJob.id==job.id,RenderJob.status=='QUEUED')
                                    .values(status='FAILED',completed_at=utc_now(),error_message='Không khởi động được worker render.'))
                raise UserError('Không khởi động được worker render; hãy thử lại.') from exc
            self.children[job.id]=process

    def monitor(self):
        import psutil
        while not self.stopped.wait(.5):
            try:
                with self.sessions() as session:
                    jobs=list(session.scalars(select(RenderJob).where(RenderJob.status.in_(ACTIVE))))
                for job in jobs:
                    process=None
                    try:
                        candidate=psutil.Process(job.pid) if job.pid else None
                        if candidate and 'app.render_worker' in candidate.cmdline() and job.id in candidate.cmdline(): process=candidate
                    except (psutil.NoSuchProcess,psutil.AccessDenied): pass
                    failed=job.status=='PROCESSING' and process is None
                    if job.cancel_requested or time.time()>job.lease_expires or failed:
                        if process:
                            children=process.children(recursive=True)
                            for child in children:
                                child.terminate()
                            _,alive=psutil.wait_procs(children,timeout=3)
                            for child in alive: child.kill()
                            psutil.wait_procs(alive,timeout=3)
                            process.terminate()
                            process.wait(timeout=5)
                        with self.sessions.begin() as session:
                            session.execute(update(RenderJob).where(RenderJob.id==job.id,RenderJob.status.in_(ACTIVE))
                                            .values(status='CANCELLED' if job.cancel_requested else 'FAILED',error_message='Worker đã hủy/dừng hoặc quá thời gian; có thể thử lại.'))
                        partial=resolve_media(self.settings.storage_root,f'projects/{job.project_id}/exports/{job.id}.partial.mp4')
                        partial.unlink(missing_ok=True)
                with self.lock:
                    for key,child in list(self.children.items()):
                        if child.poll() is not None:
                            with self.sessions.begin() as session:
                                session.execute(update(RenderJob).where(RenderJob.id==key,RenderJob.status.in_(ACTIVE),
                                                                        ((RenderJob.pid==child.pid)|(RenderJob.status=='QUEUED')))
                                                .values(status='FAILED',error_message='Worker render dừng đột ngột; hãy thử lại.'))
                            self.children.pop(key)
            except Exception as exc:
                log.warning('render_supervisor type=%s',type(exc).__name__)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
