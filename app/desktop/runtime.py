"""Executed only by managed CPython, never by the frozen launcher interpreter."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()


def backup_data(data, destination):
    data,destination=Path(data).resolve(),Path(destination).resolve()
    if destination.is_relative_to(data) or data.is_relative_to(destination) or destination.exists():
        raise ValueError('Backup destination must be new and outside the data directory.')
    if any(p.is_symlink() for p in data.rglob('*')):raise ValueError('Backup refuses symbolic links.')
    destination.mkdir(parents=True)
    try:
        shutil.copytree(data,destination,dirs_exist_ok=True,ignore=shutil.ignore_patterns('desktop.lock','desktop-status.json','fashion_ai.db','*.db-wal','*.db-shm'))
        db=data/'storage/fashion_ai.db'
        if db.is_file():
            # sqlite3's connection context manager commits but does not close.
            # Close/checkpoint before hashing, otherwise WAL/SHM disappear/change
            # after the manifest is written and a valid backup cannot restore.
            with closing(sqlite3.connect(db)) as source,closing(sqlite3.connect(destination/'storage/fashion_ai.db')) as target:
                source.backup(target);target.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        files={p.relative_to(destination).as_posix():digest(p) for p in destination.rglob('*') if p.is_file()}
        (destination/'backup-manifest.json').write_text(json.dumps(files,sort_keys=True),encoding='utf-8')
        return len(files)
    except Exception:
        # Retain an incomplete backup for diagnosis; never delete user data.
        raise


def restore_data(backup, data):
    backup,data=Path(backup).resolve(),Path(data).resolve()
    if data==backup or data.is_relative_to(backup) or backup.is_relative_to(data):raise ValueError('Restore needs separate directories.')
    data.mkdir(parents=True,exist_ok=True)
    if any(p.name!='desktop.lock' for p in data.iterdir()):raise ValueError('Restore only into an empty new data directory.')
    manifest=json.loads((backup/'backup-manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest.items():
        if Path(name).is_absolute() or '..' in Path(name).parts or '\\' in name or ':' in name:raise ValueError('Unsafe backup entry.')
        path=(backup/name).resolve()
        if not path.is_relative_to(backup) or not path.is_file() or path.is_symlink() or digest(path)!=expected:raise ValueError('Backup integrity check failed.')
    for name in manifest:
        target=data/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(backup/name,target)
    return len(manifest)


def cleanup_temp(data,confirmed=False,now=None):
    if not confirmed:raise ValueError('Explicit --confirm is required.')
    root=Path(data)/'storage/temp';count=0;now=now or time.time()
    if root.is_dir():
        for p in root.iterdir():
            if p.is_file() and not p.is_symlink() and p.suffix in {'.part','.tmp'} and now-p.stat().st_mtime>86400:
                p.unlink();count+=1
    return count


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--backup',type=Path);parser.add_argument('--restore',type=Path);parser.add_argument('--clean-temp',action='store_true');parser.add_argument('--confirm',action='store_true')
    args=parser.parse_args(argv);data=args.data_dir.resolve()
    try:
        if args.restore:
            print(json.dumps({'restored_files':restore_data(args.restore,data)}));return 0
        if args.backup:
            print(json.dumps({'backup_files':backup_data(data,args.backup)}));return 0
        if args.clean_temp:
            print(json.dumps({'expired_temp_files_removed':cleanup_temp(data,args.confirm)}));return 0
        from app.core.config import load_settings
        from app.database.session import create_database
        from app.services.video_mux_service import capabilities
        from app.services.text_layout import available_fonts
        from app.desktop.model_manager import inventory,recover_downloads
        from app.version import __version__
        settings=load_settings();sessions=create_database(settings.database_url);recover_downloads(sessions)
        caps=capabilities(settings)
        if not caps['video_encoder'] or not caps['aac'] or not caps['ass_filter'] or not caps['mov_text']:raise RuntimeError('FFmpeg lacks CPU H264/AAC/libass/mov_text.')
        fonts=available_fonts()
        if not fonts:raise RuntimeError('Install a licensed Vietnamese-compatible font.')
        versions={}
        from importlib.metadata import version
        for name in ['streamlit','paddleocr','paddlepaddle','ctranslate2','faster-whisper','sherpa-onnx']:versions[name]=version(name)
        result=dict(version=__version__,python='3.11',data_dir=str(data),models=inventory(Path(os.environ['FASHION_AI_MODELS_DIR'])),encoders=caps,font_names=list(fonts),dependencies=versions)
        (data/'logs').mkdir(parents=True,exist_ok=True)
        (data/'logs/runtime-check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False));sessions.kw['bind'].dispose();return 0
    except Exception as exc:
        (data/'logs').mkdir(parents=True,exist_ok=True)
        (data/'logs/runtime-check.log').write_text('Runtime check failed: '+type(exc).__name__+'\n',encoding='utf-8')
        print('Runtime check failed ('+type(exc).__name__+'); see Windows troubleshooting guide.');return 1


if __name__=='__main__':raise SystemExit(main())
