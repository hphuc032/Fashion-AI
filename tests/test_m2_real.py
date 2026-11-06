"""Opt-in complete real M1→M2 path, separate native-model/render workers."""
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from app.core.config import load_settings
from app.database.session import create_database
from app.services.job_manager import JobManager
from app.services.ocr_service import queue_job,latest_job
from app.services.ocr_repository import list_segments,save_reviews
from app.services.storage_service import import_video
from app.services.replacement_repository import save_config
from app.services.text_compositor import ReplacementSettings
from app.services.text_layout import TextStyle
from app.services.render_jobs import RenderManager,queue_render,render_history,cancel_render
from app.services.render_preview import preview_frame
from app.services.video_service import probe_video
from app.utils.validators import SourceInfo
from scripts.generate_m1_fixture import generate_fixture
from tests.test_m2 import packet_hashes


@pytest.mark.skipif(os.getenv('M2_RUN_REAL')!='1',reason='M2_RUN_REAL=1 enables actual OCR/translation/render end-to-end')
def test_real_m1_to_m2_export_audio_and_restart(tmp_path):
    settings=load_settings()
    settings.storage_root=tmp_path/'storage'
    settings.database_url=f'sqlite:///{tmp_path / "real-m2.db"}'
    settings.translation_provider='argos'
    fixture=tmp_path/'silent.mp4'
    source=tmp_path/'chinese-audio.mp4'
    font=Path(os.getenv('M1_CHINESE_FONT',str(Path(os.getenv('WINDIR',''))/'Fonts'/'msyh.ttc')))
    generate_fixture(fixture,settings.ffmpeg_path,font)
    subprocess.run([settings.ffmpeg_path,'-nostdin','-y','-v','error','-i',str(fixture),'-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=6',
                    '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac',str(source)],check=True,timeout=30)
    original=source.read_bytes()
    sessions=create_database(settings.database_url)
    with source.open('rb') as stream:
        project=import_video(stream,source.name,SourceInfo(rights_status='owned',creator_name='Synthetic fixture'),settings,sessions,str(uuid4()))
    started=time.perf_counter()
    ocr=JobManager(settings,sessions)
    def wait_for(getter):
        deadline=time.time()+180
        while time.time()<deadline:
            job=getter()
            if job.status not in {'QUEUED','PROCESSING'}:
                assert job.status=='COMPLETED',job.error_message
                return job
            time.sleep(.1)
        pytest.fail('Worker timeout')
    job=queue_job(sessions,settings,project.id)
    ocr.launch(job);wait_for(lambda:latest_job(sessions,project.id))
    segment=next(s for s in list_segments(sessions,project.id) if s.source_text=='男生穿搭')
    job=queue_job(sessions,settings,project.id,kind='translate',selected_ids=[segment.id])
    ocr.launch(job);wait_for(lambda:latest_job(sessions,project.id))
    segment=next(s for s in list_segments(sessions,project.id) if s.id==segment.id)
    assert segment.translated_text=='Phối đồ nam'
    save_reviews(sessions,project.id,[dict(id=segment.id,revision=segment.revision,review_status='approved')])
    config=ReplacementSettings(removal_mode='solid',style=TextStyle(size=30))
    save_config(sessions,project.id,segment.id,config)
    before,after,_=preview_frame(sessions,settings,project.id,1)
    assert not np.array_equal(np.asarray(before),np.asarray(after))
    manager=RenderManager(settings,sessions)
    job=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    manager.launch(job)
    completed=wait_for(lambda:render_history(sessions,project.id)[0])
    output=settings.storage_root/completed.output_path
    metadata=probe_video(output,settings.ffprobe_path,'.mp4')
    assert (metadata.width,metadata.height,metadata.video_codec,metadata.audio_codec)==(540,960,'h264','aac')
    assert abs(metadata.duration-6)<.12
    assert packet_hashes(source,settings)==packet_hashes(output,settings)
    # Packet timestamps are also unchanged: copied sound has no accumulated shift.
    def audio_times(path):
        import json
        result=subprocess.run([settings.ffprobe_path,'-v','error','-select_streams','a:0','-show_entries','packet=pts_time','-of','json',str(path)],check=True,capture_output=True,timeout=30)
        return [float(p['pts_time']) for p in json.loads(result.stdout)['packets']]
    assert np.allclose(audio_times(source),audio_times(output),atol=1/48000)
    cancelled=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    manager.launch(cancelled)
    deadline=time.time()+15
    while render_history(sessions,project.id)[0].status=='QUEUED' and time.time()<deadline:time.sleep(.02)
    assert render_history(sessions,project.id)[0].status=='PROCESSING'
    cancel_render(sessions,cancelled.id)
    while render_history(sessions,project.id)[0].status in {'QUEUED','PROCESSING'} and time.time()<deadline:time.sleep(.1)
    assert render_history(sessions,project.id)[0].status=='CANCELLED'
    assert output.is_file() and source.read_bytes()==original
    manager.close();ocr.close();sessions.kw['bind'].dispose()
    reopened=create_database(settings.database_url)
    assert any(j.output_path==completed.output_path and j.status=='COMPLETED' for j in render_history(reopened,project.id))
    assert list_segments(reopened,project.id)[0].project_id==project.id
    print({'m1_m2_seconds':round(time.perf_counter()-started,2),'output_bytes':output.stat().st_size,'duration':metadata.duration,'audio_packet_copy_and_pts':'verified'})
    reopened.kw['bind'].dispose()
