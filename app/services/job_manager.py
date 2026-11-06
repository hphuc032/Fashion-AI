"""One persisted active slot, disposable worker, cancellation and crash recovery."""
import logging
import os
import subprocess
import sys
import threading
import time

from sqlalchemy import and_, or_, select, update

from app.core.config import ROOT
from app.database.m1_models import OCRJob
from app.services.ocr_service import ACTIVE

log = logging.getLogger("fashion_ai.jobs")


def worker_process(job):
    """Only identify a process if its command line includes this exact job UUID."""
    if not job.pid:
        return None
    import psutil
    try:
        process = psutil.Process(job.pid)
        command = process.cmdline()
        if "app.worker" in command and job.id in command and process.is_running():
            return process
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        pass
    return None


def reconcile_jobs(sessions, now=None):
    """Recover expired/dead jobs, never touch source media or unrelated processes."""
    now = time.time() if now is None else now
    with sessions() as session:
        jobs = list(session.scalars(select(OCRJob).where(OCRJob.status.in_(ACTIVE))))
    for job in jobs:
        process = worker_process(job) if job.status == "PROCESSING" else None
        dead = job.status == "PROCESSING" and process is None
        expired = now > job.lease_expires
        if job.cancel_requested or expired or dead:
            if process:
                try:
                    process.terminate()
                    process.wait(timeout=5)
                except Exception as exc:
                    log.warning("worker_stop_failed job_id=%s type=%s", job.id, type(exc).__name__)
                    # Keep the active lock until the OS process actually exits.
                    continue
            state = "CANCELLED" if job.cancel_requested else "FAILED"
            error = "Đã hủy tác vụ; giữ nguyên video và kết quả trước đó." if job.cancel_requested else "Worker dừng hoặc quá thời gian. Hãy thử lại; kết quả trước đó vẫn được giữ."
            with sessions.begin() as session:
                session.execute(update(OCRJob).where(OCRJob.id == job.id, OCRJob.status.in_(ACTIVE))
                                .values(status=state, stage=state.lower(), error_message=error))


class JobManager:
    def __init__(self, settings, sessions):
        self.settings, self.sessions = settings, sessions
        self.children = {}
        self.lock = threading.Lock()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self._monitor, daemon=True, name="m1-job-supervisor")
        self.thread.start()

    def launch(self, job):
        with self.lock:
            if job.id in self.children:
                return
            folder = self.settings.storage_root / "logs"
            folder.mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update({"PYTHONUTF8": "1", "PADDLE_PDX_CACHE_HOME": str(self.settings.storage_root / "models" / "paddlex-cache"),
                        "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True", "HF_HUB_OFFLINE": "1", "OMP_NUM_THREADS": "2"})
            try:
                with (folder / f"{job.id}.log").open("ab") as output:
                    process = subprocess.Popen(
                        [sys.executable, "-m", "app.worker", "--job", job.id, "--database-url", self.settings.database_url],
                        cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                        shell=False, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    )
                self.children[job.id] = process
            except OSError as exc:
                with self.sessions.begin() as session:
                    session.execute(update(OCRJob).where(OCRJob.id == job.id, OCRJob.status == "QUEUED")
                                    .values(status="FAILED", error_message="Không mở được worker. Kiểm tra Python và quyền ghi."))
                raise RuntimeError("Cannot launch OCR worker") from exc

    def _monitor(self):
        while not self.stopped.wait(0.5):
            try:
                reconcile_jobs(self.sessions)
                with self.lock:
                    for job_id, process in list(self.children.items()):
                        code = process.poll()
                        if code is not None:
                            with self.sessions.begin() as session:
                                # A duplicate launcher may exit normally after losing
                                # QUEUED claim. Only the owning child's exit can fail
                                # PROCESSING; never invalidate the winner's job.
                                session.execute(update(OCRJob).where(OCRJob.id == job_id, OCRJob.status.in_(ACTIVE),
                                                        or_(OCRJob.pid == process.pid,
                                                            and_(OCRJob.status == "QUEUED", OCRJob.pid.is_(None))))
                                                .values(status="FAILED", error_message="Worker dừng đột ngột. Kiểm tra mô hình và thử lại."))
                            self.children.pop(job_id)
            except Exception as exc:
                log.warning("supervisor_error type=%s", type(exc).__name__)

    def close(self):
        self.stopped.set()
        self.thread.join(timeout=2)
