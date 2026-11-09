"""Pinned explicit downloads only; no inference implementation or startup network."""
import json
import os
from pathlib import Path
import tempfile
import shutil
import threading
import time
from uuid import uuid4
from sqlalchemy import select,update
from app.database.desktop_schema import ModelDownloadJob
from app.database.models import utc_now
from app.desktop.runtime import digest
from app.services.workload_guard import ensure_idle
from app.utils.validators import UserError

CATALOG=Path(__file__).with_name('models.json')


def catalog():return json.loads(CATALOG.read_text(encoding='utf-8'))['models']


def verified(folder,files):
    folder=Path(folder).resolve()
    for name,sha in files.items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or not path.is_file() or path.is_symlink() or digest(path)!=sha:return False
    return bool(files)


def inventory(root,verify=False):
    result=[]
    for item in catalog():
        folder=Path(root)/item['path'];present=all((folder/name).is_file() for name in item['files'])
        status='missing' if not present else ('verified' if verified(folder,item['files']) else 'corrupt') if verify else 'installed (hash not checked)'
        result.append(dict(id=item['id'],group=item['group'],path=str(folder),status=status,license=item['license'],
                           source_url=item.get('url') or (item.get('downloads') or [{}])[0].get('url',''),
                           download_mb=round((item.get('download_bytes',0)+sum(f['download_bytes'] for f in item.get('downloads',[])))/1024**2,1)))
    return result


def download_file(url,target,expected,max_bytes,check,progress):
    import requests
    if not url.startswith('https://'):raise UserError('Model source must use HTTPS.')
    partial=target.with_suffix(target.suffix+'.part');total=0
    try:
        with requests.get(url,stream=True,timeout=(15,30)) as response:
            response.raise_for_status()
            if not response.url.startswith('https://'):raise UserError('Model redirect must retain HTTPS.')
            with partial.open('wb') as output:
                for block in response.iter_content(1024*1024):
                    check();total+=len(block)
                    if total>max_bytes:raise UserError('Model download exceeds pinned size.')
                    output.write(block);progress(total)
        if digest(partial)!=expected:raise UserError('Model SHA256 mismatch; previous model untouched.')
        partial.replace(target)
    finally:partial.unlink(missing_ok=True)


def staging_root(root,job_id):
    # UUID and ownership marker scope cleanup strictly to our download staging.
    try:
        if str(__import__('uuid').UUID(job_id))!=job_id:raise ValueError()
    except (ValueError,TypeError,AttributeError) as exc:raise UserError('Invalid download job UUID.') from exc
    parent=(Path(root).resolve()/'.fashion-ai-downloads');folder=parent/job_id
    if not folder.resolve().is_relative_to(parent.resolve()):raise UserError('Unsafe download staging path.')
    return folder


def cleanup_download(root,job_id):
    folder=staging_root(root,job_id);marker=folder/'owner.json'
    if folder.is_dir() and not folder.is_symlink() and marker.is_file() and json.loads(marker.read_text()).get('job_id')==job_id:
        shutil.rmtree(folder)


def install_model(item,root,check=lambda:None,progress=lambda n:None,job_id=None):
    from scripts.setup_m1_models import install_archive
    root=Path(root).resolve();target=root/item['path']
    if not target.resolve().is_relative_to(root):raise UserError('Invalid model path.')
    if target.exists():
        if verified(target,item['files']):return 'already verified'
        raise UserError('Existing model incomplete/changed. Move it aside or restore a verified backup; no automatic overwrite.')
    target.parent.mkdir(parents=True,exist_ok=True)
    stage_parent=target.parent
    if job_id:
        stage_parent=staging_root(root,job_id);stage_parent.mkdir(parents=True,exist_ok=True)
        (stage_parent/'owner.json').write_text(json.dumps({'job_id':job_id}),encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='model-stage-',dir=stage_parent) as temporary:
        stage=Path(temporary)
        if item.get('archive'):
            archive=stage/item['archive']
            download_file(item['url'],archive,item['sha256'],item['download_bytes'],check,progress)
            install_archive(archive,stage/'unpacked',target.name);candidate=stage/'unpacked'/target.name
        else:
            candidate=stage/target.name;candidate.mkdir()
            transferred=0
            for file in item['downloads']:
                check();download_file(file['url'],candidate/file['name'],file['sha256'],file['download_bytes'],check,lambda n:progress(transferred+n))
                transferred+=file['download_bytes']
            (candidate/'local-manifest.json').write_text(json.dumps(item['files'],sort_keys=True),encoding='utf-8')
        check()
        if not verified(candidate,item['files']):raise UserError('Extracted model integrity check failed.')
        if target.exists():raise UserError('Model target appeared during download; refusing overwrite.')
        candidate.rename(target)
    return 'installed and verified'


def history(sessions):
    with sessions() as db:return list(db.scalars(select(ModelDownloadJob).order_by(ModelDownloadJob.created_at.desc())))


def recover_downloads(sessions):
    import psutil
    with sessions.begin() as db:
        for row in db.scalars(select(ModelDownloadJob).where(ModelDownloadJob.status.in_(['QUEUED','RUNNING']))):
            alive=False
            try:alive=abs(psutil.Process(row.pid).create_time()-row.process_created)<.01
            except psutil.Error:pass
            if not alive:
                row.status='FAILED';row.error='Download process stopped/expired; staging never replaces installed models.';row.completed_at=utc_now()
                try:cleanup_download(row.models_root,row.id)
                except (ValueError,OSError,UserError):pass
            elif time.time()>row.lease_expires:
                # Do not release the heavy slot until the live thread stops.
                row.cancel_requested=True


def queue_download(sessions,root,group):
    import psutil
    if group not in {i['group'] for i in catalog()}:raise UserError('Unknown supported model group.')
    recover_downloads(sessions)
    with sessions() as db:
        db.connection().exec_driver_sql('BEGIN IMMEDIATE');ensure_idle(db)
        job=ModelDownloadJob(id=str(uuid4()),group=group,models_root=str(Path(root).resolve()),pid=os.getpid(),process_created=psutil.Process().create_time(),lease_expires=time.time()+1800)
        db.add(job);db.commit()
    threading.Thread(target=run_download,args=(sessions,job.id),daemon=True,name='explicit-model-download').start()
    return job


def run_download(sessions,job_id):
    try:
        with sessions.begin() as db:
            row=db.get(ModelDownloadJob,job_id)
            if row.status!='QUEUED':return
            row.status='RUNNING';group,root=row.group,row.models_root
        items=[i for i in catalog() if i['group']==group];result={}
        def check():
            with sessions() as db:
                row=db.get(ModelDownloadJob,job_id)
                if row.cancel_requested:raise UserError('Model download cancelled.')
                if row.status!='RUNNING' or time.time()>row.lease_expires:raise UserError('Model download expired.')
        for index,item in enumerate(items):
            def progress(n):
                denominator=item.get('download_bytes',0) or sum(f['download_bytes'] for f in item.get('downloads',[]))
                with sessions.begin() as db:db.execute(update(ModelDownloadJob).where(ModelDownloadJob.id==job_id).values(progress=min(.99,(index+min(1,n/max(1,denominator)))/len(items))))
            check();result[item['id']]=install_model(item,root,check,progress,job_id=job_id)
        check()
        with sessions.begin() as db:
            row=db.get(ModelDownloadJob,job_id);row.status='COMPLETED';row.progress=1;row.result=result;row.completed_at=utc_now()
    except Exception as exc:
        with sessions.begin() as db:
            row=db.get(ModelDownloadJob,job_id)
            if row.status in {'QUEUED','RUNNING'}:
                row.status='CANCELLED' if row.cancel_requested else 'FAILED';row.error=str(exc) if isinstance(exc,UserError) else 'Model download failed ('+type(exc).__name__+'); retry after checking network/disk.';row.completed_at=utc_now()
    finally:
        with sessions() as db:row=db.get(ModelDownloadJob,job_id)
        if row:
            try:cleanup_download(row.models_root,row.id)
            except (ValueError,OSError,UserError):pass
