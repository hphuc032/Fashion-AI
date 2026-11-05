import time

import pytest

from app.database.m1_models import OCRJob
from app.services.job_manager import JobManager, reconcile_jobs
from app.services.ocr_service import latest_job, queue_job, request_cancel


def test_supervisor_launch_once_and_handle_child_crash(m1, monkeypatch):
    settings, sessions, project = m1
    calls = []
    class Process:
        pid = 7777
        def poll(self):
            return 1
    def launch(args, **kwargs):
        assert kwargs["shell"] is False
        assert "app.worker" in args
        calls.append(args)
        return Process()
    monkeypatch.setattr("app.services.job_manager.subprocess.Popen", launch)
    job = queue_job(sessions, settings, project.id)
    manager = JobManager(settings, sessions)
    try:
        manager.launch(job)
        manager.launch(job)
        assert len(calls) == 1
        deadline = time.time() + 3
        while latest_job(sessions, project.id).status == "QUEUED" and time.time() < deadline:
            time.sleep(.05)
        assert latest_job(sessions, project.id).status == "FAILED"
    finally:
        manager.close()


def test_cancel_only_verified_worker_process(m1, monkeypatch):
    settings, sessions, project = m1
    job = queue_job(sessions, settings, project.id)
    with sessions.begin() as session:
        row = session.get(OCRJob, job.id)
        row.status, row.pid = "PROCESSING", 1234
    stopped = []
    class Process:
        def terminate(self):
            stopped.append(True)
        def wait(self, timeout):
            pass
    monkeypatch.setattr("app.services.job_manager.worker_process", lambda row: Process())
    request_cancel(sessions, job.id)
    reconcile_jobs(sessions)
    assert stopped == [True]
    assert latest_job(sessions, project.id).status == "CANCELLED"


def test_failed_termination_keeps_exclusive_slot(m1, monkeypatch):
    settings, sessions, project = m1
    job = queue_job(sessions, settings, project.id)
    with sessions.begin() as session:
        row = session.get(OCRJob, job.id)
        row.status, row.pid = "PROCESSING", 1234
    class Process:
        def terminate(self):
            raise OSError("access denied")
    monkeypatch.setattr("app.services.job_manager.worker_process", lambda row: Process())
    request_cancel(sessions, job.id)
    reconcile_jobs(sessions)
    assert latest_job(sessions, project.id).status == "PROCESSING"


def test_duplicate_launcher_exit_does_not_fail_the_winning_worker(m1, monkeypatch):
    settings, sessions, project = m1
    job = queue_job(sessions, settings, project.id)
    with sessions.begin() as session:
        row = session.get(OCRJob, job.id)
        row.status, row.pid = "PROCESSING", 1111
    class DuplicateProcess:
        pid = 2222
        def poll(self):
            return 0
    monkeypatch.setattr("app.services.job_manager.reconcile_jobs", lambda sessions: None)
    monkeypatch.setattr("app.services.job_manager.subprocess.Popen", lambda *args, **kwargs: DuplicateProcess())
    manager = JobManager(settings, sessions)
    try:
        manager.launch(job)
        deadline = time.time() + 3
        while manager.children and time.time() < deadline:
            time.sleep(.05)
        assert not manager.children
        assert latest_job(sessions, project.id).status == "PROCESSING"
    finally:
        manager.close()
