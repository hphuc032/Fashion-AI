import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import pytest
from app.desktop.launcher import InstanceLock,initialize_data,child_environment,healthy,owned_process
from app.desktop.runtime import backup_data,restore_data,cleanup_temp
from app.desktop import model_manager as models
from app.database.session import create_database
from app.database.desktop_schema import ModelDownloadJob
from app.services.workload_guard import ensure_idle
from app.utils.validators import UserError


def test_instance_lock_exclusion_and_release(tmp_path):
    first,second=InstanceLock(tmp_path),InstanceLock(tmp_path)
    assert first.acquire() and not second.acquire()
    first.close();assert second.acquire();second.close()


def test_first_start_and_upgrade_preserve_config_database_and_media(tmp_path):
    initialize_data(tmp_path);config=tmp_path/'config.env';config.write_text('ASR_PROVIDER=whisper\nCUSTOM=preserved\n')
    db=tmp_path/'storage/fashion_ai.db';sessions=create_database('sqlite:///'+db.as_posix());sessions.kw['bind'].dispose()
    with sqlite3.connect(db) as c:c.execute('create table user_probe(value text)');c.execute("insert into user_probe values ('keep')")
    original=tmp_path/'storage/projects/owned.mp4';original.write_bytes(b'original-private-fixture')
    initialize_data(tmp_path);sessions=create_database('sqlite:///'+db.as_posix());sessions.kw['bind'].dispose()
    assert config.read_text().endswith('CUSTOM=preserved\n') and original.read_bytes()==b'original-private-fixture'
    with sqlite3.connect(db) as c:assert c.execute('select value from user_probe').fetchone()==('keep',)


def test_child_environment_relocates_data_and_ignores_developer_python(tmp_path,monkeypatch):
    bundle=tmp_path/'bundle';(bundle/'_code').mkdir(parents=True);(bundle/'tools').mkdir();(bundle/'tools/ffmpeg.exe').write_bytes(b'tool')
    monkeypatch.setenv('PYTHONHOME','private-dev-python');monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR','private-build')
    env=child_environment(bundle,tmp_path/'data')
    assert 'PYTHONHOME' not in env and '_PYI_APPLICATION_HOME_DIR' not in env
    assert env['STORAGE_ROOT']==str(tmp_path/'data/storage') and env['PYTHONPATH']==str(bundle/'_code')
    assert env['FFMPEG_PATH']==str(bundle/'tools/ffmpeg.exe') and env['ASR_MODEL_DIR'].endswith('models'+os.sep+'funasr')


@pytest.mark.parametrize('status',[{},dict(port=80,token='a'*32),dict(port=12345,token='../private')])
def test_health_never_requests_unsafe_status(status):assert not healthy(status)


def test_health_readiness_scoped_loopback_server():
    from http.server import BaseHTTPRequestHandler,HTTPServer
    import threading
    token='b'*32
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200 if self.path==f'/{token}/_stcore/health' else 404);self.end_headers();self.wfile.write(b'ok')
        def log_message(self,*args):pass
    server=HTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:assert healthy(dict(port=server.server_port,token=token))
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def test_pid_reuse_or_unrelated_process_is_not_owned():
    import psutil
    p=psutil.Process()
    assert owned_process(dict(server_pid=p.pid,server_created=p.create_time()+5,python=p.exe(),token='x'*32)) is None
    assert owned_process(dict(server_pid=p.pid,server_created=p.create_time(),python=p.exe(),token='x'*32)) is None


def test_backup_restore_validates_sha_and_preserves_data(tmp_path):
    source=tmp_path/'data';initialize_data(source)
    with sqlite3.connect(source/'storage/fashion_ai.db') as c:c.execute('create table owned(value text)');c.execute("insert into owned values ('original')")
    (source/'storage/projects/original.mp4').write_bytes(b'private-source')
    backup=tmp_path/'backup';assert backup_data(source,backup)>0
    restored=tmp_path/'restored';assert restore_data(backup,restored)>0
    assert (restored/'storage/projects/original.mp4').read_bytes()==b'private-source'
    with sqlite3.connect(restored/'storage/fashion_ai.db') as c:assert c.execute('select * from owned').fetchone()==('original',)
    with pytest.raises(ValueError):restore_data(backup,source)
    (backup/'config.env').write_text('tampered')
    with pytest.raises(ValueError,match='integrity'):restore_data(backup,tmp_path/'bad')


@pytest.mark.parametrize('entry',['../outside.txt','/absolute.txt','D:\\outside.txt'])
def test_restore_rejects_traversal(tmp_path,entry):
    backup=tmp_path/'backup';backup.mkdir();(backup/'backup-manifest.json').write_text(json.dumps({entry:'a'*64}))
    with pytest.raises(ValueError):restore_data(backup,tmp_path/'restored')


def test_cleanup_only_expired_owned_top_level_temporary_files(tmp_path):
    initialize_data(tmp_path);root=tmp_path/'storage/temp'
    for name in ['old.tmp','old.part','keep.wav','keep.mp4','recent.tmp']:(root/name).write_bytes(b'keep')
    for name in ['old.tmp','old.part','keep.wav','keep.mp4']:os.utime(root/name,(1,1))
    (root/'nested').mkdir();(root/'nested/old.tmp').write_bytes(b'nested')
    with pytest.raises(ValueError):cleanup_temp(tmp_path)
    assert cleanup_temp(tmp_path,True)==2
    assert {p.name for p in root.iterdir()}=={'keep.wav','keep.mp4','recent.tmp','nested'}


def test_catalog_and_inventory_are_offline_and_detect_corruption(tmp_path,monkeypatch):
    file=tmp_path/'model/weights.bin';file.parent.mkdir();file.write_bytes(b'verified')
    item=dict(id='fixture',group='ocr',path='model',files={'weights.bin':hashlib.sha256(b'verified').hexdigest()},license='fixture',download_bytes=8)
    monkeypatch.setattr(models,'catalog',lambda:[item])
    assert models.inventory(tmp_path)[0]['status']=='installed (hash not checked)'
    assert models.inventory(tmp_path,True)[0]['status']=='verified'
    file.write_bytes(b'changed');assert models.inventory(tmp_path,True)[0]['status']=='corrupt'
    file.unlink();assert models.inventory(tmp_path)[0]['status']=='missing'


@pytest.mark.parametrize('corrupt,cancel',[(False,False),(True,False),(False,True)])
def test_download_hash_cancel_and_partial_cleanup(tmp_path,monkeypatch,corrupt,cancel):
    import requests
    class Response:
        url='https://example.com/fixture'
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def raise_for_status(self):pass
        def iter_content(self,*args):yield b'fixture'
    monkeypatch.setattr(requests,'get',lambda *args,**kwargs:Response())
    target=tmp_path/'archive';expected=hashlib.sha256(b'bad' if corrupt else b'fixture').hexdigest()
    def check():
        if cancel:raise UserError('cancelled')
    if corrupt or cancel:
        with pytest.raises(UserError):models.download_file('https://example.com/fixture',target,expected,7,check,lambda n:None)
        assert not target.exists()
    else:models.download_file('https://example.com/fixture',target,expected,7,check,lambda n:None);assert target.read_bytes()==b'fixture'
    assert not list(tmp_path.glob('*.part'))


def test_download_refuses_insecure_source_and_existing_model(tmp_path):
    with pytest.raises(UserError):models.download_file('http://example.com',tmp_path/'bad','a'*64,10,lambda:None,lambda n:None)
    (tmp_path/'owned').mkdir();(tmp_path/'owned/private').write_bytes(b'preserve')
    with pytest.raises(UserError,match='overwrite'):models.install_model(dict(path='owned',files={'missing':'a'*64}),tmp_path)
    assert (tmp_path/'owned/private').read_bytes()==b'preserve'


def test_model_job_excludes_other_heavy_work_and_recovers_dead_process(tmp_path):
    sessions=create_database('sqlite:///'+(tmp_path/'jobs.db').as_posix())
    with sessions.begin() as db:db.add(ModelDownloadJob(id='fixture',group='ocr',models_root=str(tmp_path),pid=99999999,process_created=1,lease_expires=time.time()+30,status='RUNNING'))
    with sessions() as db:
        with pytest.raises(UserError):ensure_idle(db)
    models.recover_downloads(sessions)
    assert models.history(sessions)[0].status=='FAILED'
    with sessions() as db:ensure_idle(db)
    sessions.kw['bind'].dispose()


def test_desktop_studio_without_network_or_models(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    import requests
    monkeypatch.setenv('STORAGE_ROOT',str(tmp_path/'storage'));monkeypatch.setenv('DATABASE_URL','sqlite:///'+(tmp_path/'ui.db').as_posix())
    monkeypatch.setenv('FASHION_AI_MODELS_DIR',str(tmp_path/'models'))
    monkeypatch.setattr(requests,'get',lambda *args,**kwargs:(_ for _ in ()).throw(AssertionError('No startup download')))
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/main.py')).run();app.sidebar.radio[0].set_value('Desktop & Models').run()
    assert not app.exception and any(t.value=='Desktop & Models' for t in app.title)
    assert any('Tải nhóm' in b.label and b.disabled for b in app.button)


def test_build_filter_keeps_native_model_modules_but_excludes_weights_and_media():
    from scripts.build_windows import copy_ignore
    blocked=copy_ignore('fixture',['models','streamlit','static','native.dll','weights.onnx','source.mp4','.cache','__pycache__','fixture.wav'])
    assert set(blocked)=={'weights.onnx','source.mp4','.cache','__pycache__','fixture.wav'}


def test_user_environment_file_is_loaded_without_overwriting_process_values(tmp_path,monkeypatch):
    from app.core.config import load_settings
    config=tmp_path/'config.env';config.write_text('APP_ENV=desktop-fixture\nASR_PROVIDER=whisper\n')
    monkeypatch.setenv('FASHION_AI_ENV_FILE',str(config));monkeypatch.delenv('APP_ENV',raising=False)
    monkeypatch.setenv('ASR_PROVIDER','explicit-existing')
    assert load_settings().app_env=='desktop-fixture' and load_settings().asr_provider=='explicit-existing'
    monkeypatch.delenv('APP_ENV',raising=False)


def test_dead_download_cleanup_requires_matching_uuid_and_owner(tmp_path):
    from uuid import uuid4
    job=str(uuid4());folder=models.staging_root(tmp_path,job);folder.mkdir(parents=True)
    (folder/'keep.part').write_bytes(b'owned staging')
    models.cleanup_download(tmp_path,job);assert folder.exists() # No ownership marker: do not delete.
    (folder/'owner.json').write_text(json.dumps({'job_id':job}));models.cleanup_download(tmp_path,job);assert not folder.exists()
    with pytest.raises(UserError):models.staging_root(tmp_path,'../project')


def test_wal_backup_manifest_stays_valid_after_all_connections_close(tmp_path):
    data=tmp_path/'data';initialize_data(data)
    connection=sqlite3.connect(data/'storage/fashion_ai.db');connection.execute('PRAGMA journal_mode=WAL');connection.execute('create table original(v text)');connection.execute("insert into original values ('preserved')");connection.commit()
    backup=tmp_path/'backup';backup_data(data,backup);connection.close()
    manifest=json.loads((backup/'backup-manifest.json').read_text())
    assert not any(name.endswith(('-wal','-shm')) for name in manifest)
    restore_data(backup,tmp_path/'restored')
    with sqlite3.connect(tmp_path/'restored/storage/fashion_ai.db') as c:assert c.execute('select * from original').fetchone()==('preserved',)
