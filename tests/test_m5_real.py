"""Opt-in explicit real HTTPS model download, not a mocked installation."""
import os
import time
import pytest
from app.database.session import create_database
from app.desktop.model_manager import queue_download,history,inventory


@pytest.mark.skipif(os.getenv('M5_RUN_REAL')!='1',reason='M5_RUN_REAL=1 enables explicit Paddle mobile model download')
def test_real_explicit_model_download_and_verified_reopen(tmp_path):
    sessions=create_database('sqlite:///'+(tmp_path/'model-jobs.db').as_posix());root=tmp_path/'external-models'
    job=queue_download(sessions,root,'ocr');deadline=time.time()+240
    while time.time()<deadline:
        row=history(sessions)[0]
        if row.status in {'COMPLETED','FAILED','CANCELLED'}:break
        time.sleep(.1)
    assert row.status=='COMPLETED',row.error
    rows=[r for r in inventory(root,True) if r['group']=='ocr'];assert len(rows)==2 and all(r['status']=='verified' for r in rows)
    reopened=create_database('sqlite:///'+(tmp_path/'model-jobs.db').as_posix());assert history(reopened)[0].id==job.id
    reopened.kw['bind'].dispose();sessions.kw['bind'].dispose()
