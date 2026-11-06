"""The existing disposable-worker/supervisor pattern, scoped to final renders."""
import logging
import os
import subprocess
import sys
import threading
import time
from sqlalchemy import select,update
from app.core.config import ROOT
from app.database.models import utc_now
from app.database.final_schema import FinalRenderJob,ACTIVE
from app.services.storage_service import resolve_media
from app.services.final_render_service import cleanup_staging
from app.utils.validators import UserError

log=logging.getLogger('fashion_ai.final_supervisor')


class FinalManager:
    def __init__(self,settings,sessions):
        self.settings,self.sessions=settings,sessions
        self.children={};self.lock=threading.Lock();self.stopped=threading.Event()
        self.thread=threading.Thread(target=self.monitor,daemon=True);self.thread.start()

    def launch(self,job):
        with self.lock:
            with self.sessions() as db:current=db.get(FinalRenderJob,job.id)
            if not current or current.status!='QUEUED' or job.id in self.children:return
            folder=self.settings.storage_root/'logs';folder.mkdir(parents=True,exist_ok=True)
            env=os.environ.copy();env.update(PYTHONUTF8='1',OMP_NUM_THREADS='2')
            try:
                with (folder/f'final-{job.id}.log').open('ab') as stream:
                    child=subprocess.Popen([sys.executable,'-m','app.final_worker','--job',job.id,'--database-url',self.settings.database_url],cwd=ROOT,env=env,
                                           stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,shell=False,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.children[job.id]=child
            except OSError as exc:
                with self.sessions.begin() as db:db.execute(update(FinalRenderJob).where(FinalRenderJob.id==job.id,FinalRenderJob.status=='QUEUED').values(status='FAILED',completed_at=utc_now(),error_message='Không mở được worker final render.'))
                raise UserError('Không mở được worker final render.') from exc

    def monitor(self):
        import psutil
        while not self.stopped.wait(.5):
            try:
                with self.sessions() as db:jobs=list(db.scalars(select(FinalRenderJob).where(FinalRenderJob.status.in_(ACTIVE))))
                for job in jobs:
                    process=None
                    try:
                        candidate=psutil.Process(job.pid) if job.pid else None
                        if candidate and 'app.final_worker' in candidate.cmdline() and job.id in candidate.cmdline():process=candidate
                    except (psutil.NoSuchProcess,psutil.AccessDenied,psutil.ZombieProcess):pass
                    if job.cancel_requested or time.time()>job.lease_expires or (job.status!='QUEUED' and process is None):
                        with self.sessions() as db:
                            if db.get(FinalRenderJob,job.id).status not in ACTIVE:continue
                        if process:
                            descendants=process.children(recursive=True)
                            for child in descendants:child.terminate()
                            _,alive=psutil.wait_procs(descendants,timeout=3)
                            for child in alive:child.kill()
                            psutil.wait_procs(alive,timeout=3)
                            process.terminate()
                            try:process.wait(timeout=3)
                            except psutil.TimeoutExpired:process.kill();process.wait(timeout=3)
                        with self.sessions.begin() as db:
                            changed=db.execute(update(FinalRenderJob).where(FinalRenderJob.id==job.id,FinalRenderJob.status.in_(ACTIVE)).values(status='CANCELLED' if job.cancel_requested else 'FAILED',
                                                completed_at=utc_now(),error_message='Worker final dừng/hủy/quá thời gian; đầu vào và bản xuất trước giữ nguyên.')).rowcount
                        if changed:
                            folder=resolve_media(self.settings.storage_root,f'projects/{job.project_id}/final/{job.id}');cleanup_staging(folder,failed=True)
                with self.lock:
                    for key,child in list(self.children.items()):
                        if child.poll() is not None:
                            with self.sessions.begin() as db:
                                row=db.get(FinalRenderJob,key)
                                changed=db.execute(update(FinalRenderJob).where(FinalRenderJob.id==key,FinalRenderJob.status.in_(ACTIVE),((FinalRenderJob.pid==child.pid)|(FinalRenderJob.status=='QUEUED')))
                                           .values(status='FAILED',completed_at=utc_now(),error_message='Worker final render dừng đột ngột; có thể thử lại.')).rowcount
                            if changed:cleanup_staging(resolve_media(self.settings.storage_root,f'projects/{row.project_id}/final/{key}'),failed=True)
                            self.children.pop(key)
            except Exception as exc:log.warning('final_supervisor type=%s',type(exc).__name__)

    def close(self):self.stopped.set();self.thread.join(timeout=2)
