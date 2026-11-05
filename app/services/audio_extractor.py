"""Bounded, cancellable FFmpeg audio operations; source files are read-only."""
import json
import subprocess
import time
from pathlib import Path
from app.services.ocr_repository import project_source
from app.services.frame_extractor import source_hash
from app.services.storage_service import resolve_media
from app.utils.validators import UserError


def audio_info(path,settings):
    try:
        result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file','-show_streams','-show_format','-of','json',str(path)],check=True,capture_output=True,timeout=30)
        raw=json.loads(result.stdout)
        audio=next((s for s in raw['streams'] if s['codec_type']=='audio'),None)
        if not audio:return None
        return {'sample_rate':int(audio['sample_rate']),'channels':int(audio['channels']),
                'duration':float(audio.get('duration') or raw['format']['duration']),'codec':audio['codec_name']}
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as exc:
        raise UserError('Không đọc được âm thanh. Kiểm tra FFprobe/tệp nguồn.') from exc


def ffmpeg(settings,args,check=lambda:None,timeout=120):
    process=None
    try:
        process=subprocess.Popen([settings.ffmpeg_path,'-nostdin','-y','-v','error',*map(str,args)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,shell=False)
        deadline=time.monotonic()+timeout
        while process.poll() is None:
            check()
            if time.monotonic()>deadline:raise UserError('Xử lý âm thanh quá thời gian.')
            time.sleep(.04)
        check()
        if process.returncode:raise UserError('FFmpeg không xử lý được âm thanh; kiểm tra codec/dung lượng.')
    except OSError as exc:raise UserError('Không chạy được FFmpeg.') from exc
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)


def extract_audio(sessions,settings,project_id,check=lambda:None):
    project,source=project_source(sessions,project_id,settings)
    if not audio_info(source,settings):raise UserError('Video không có audio; không có lời để nhận diện/lồng tiếng.')
    fingerprint=source_hash(source)
    folder=resolve_media(settings.storage_root,f'projects/{project_id}/audio/{fingerprint}')
    folder.mkdir(parents=True,exist_ok=True)
    original=folder/'original.mka'
    wav=folder/'asr-16k.wav'
    for target,args in [(original,['-map','0:a:0','-vn','-c:a','copy']),
                        (wav,['-map','0:a:0','-vn','-af',f'aresample=16000:async=1:first_pts=0,apad,atrim=duration={project.duration}', '-ac','1','-ar','16000','-c:a','pcm_s16le'])]:
        if target.is_file():
            info=audio_info(target,settings)
            if info and (target==original or (info['sample_rate']==16000 and info['channels']==1 and abs(info['duration']-project.duration)<.01)):continue
        partial=target.with_name('partial-'+target.name)
        try:
            ffmpeg(settings,['-copyts','-start_at_zero','-protocol_whitelist','file','-i',source,*args,partial],check)
            if not audio_info(partial,settings):raise UserError('Không tạo được audio hợp lệ.')
            if source_hash(source)!=fingerprint:raise UserError('Nguồn thay đổi trong khi trích audio.')
            partial.replace(target)
        finally:partial.unlink(missing_ok=True)
    return original,wav
