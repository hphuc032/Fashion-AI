"""Real original Chinese captions+speech → approved M2/M3 → M4 preview/final."""
import os
import time
from pathlib import Path
from uuid import uuid4
import pytest
from PIL import Image
from app.core.config import load_settings
from app.database.session import create_database
from app.services.audio_extractor import ffmpeg
from app.services.storage_service import import_video
from app.services.job_manager import JobManager
from app.services.ocr_service import queue_job,latest_job
from app.services.ocr_repository import list_segments,save_reviews
from app.services.replacement_repository import save_config
from app.services.text_compositor import ReplacementSettings
from app.services.text_layout import TextStyle
from app.services.render_jobs import RenderManager,queue_render,render_history
from app.services.dub_jobs import DubManager,queue_dub,history
from app.services.speech_repository import list_speech,save_speech
from app.services.dubbing_contract import approved_dub
from app.services.final_render_config import FinalRenderConfig,SubtitleStyle
from app.services.final_render_service import queue_final,final_history,exports,export_contract,cancel_final
from app.services.final_job_manager import FinalManager
from app.services.final_output_validation import frame
from app.services.frame_extractor import source_hash
from app.utils.validators import SourceInfo
from scripts.generate_m1_fixture import generate_fixture
from scripts.generate_m3_fixture import generate


@pytest.mark.skipif(os.getenv('M4_RUN_REAL')!='1',reason='M4_RUN_REAL=1 enables real Paddle/Argos/Whisper/Vietnamese TTS→final FFmpeg E2E')
def test_real_full_localization_to_final_mp4(tmp_path):
    settings=load_settings();root=settings.storage_root
    font=Path(os.getenv('M1_CHINESE_FONT',str(Path(os.getenv('WINDIR',''))/'Fonts/msyh.ttc')))
    silent=tmp_path/'chinese-captions.mp4';generate_fixture(silent,settings.ffmpeg_path,font)
    spoken=generate(tmp_path/'mandarin.wav',root/'models/vits-icefall-zh-aishell3')
    source=tmp_path/'original.mp4'
    ffmpeg(settings,['-i',silent,'-i',spoken,'-af','apad','-t','6','-c:v','copy','-c:a','aac',source])
    settings.storage_root=tmp_path/'media';settings.database_url=f'sqlite:///{tmp_path/"m4.db"}'
    settings.asr_provider='whisper';settings.translation_provider='argos'
    sessions=create_database(settings.database_url)
    with source.open('rb') as stream:project=import_video(stream,source.name,SourceInfo(rights_status='owned',creator_name='Original synthetic Chinese fashion demo'),settings,sessions,str(uuid4()))
    started=time.perf_counter();ocr=JobManager(settings,sessions);render=RenderManager(settings,sessions);dub=DubManager(settings,sessions);final=FinalManager(settings,sessions)
    def wait(getter,timeout=240):
        deadline=time.time()+timeout
        while time.time()<deadline:
            job=getter()
            if job.status in {'COMPLETED','FAILED','CANCELLED'}:
                assert job.status=='COMPLETED',job.error_message
                return job
            time.sleep(.1)
        pytest.fail('Real milestone worker timeout')
    try:
        job=queue_job(sessions,settings,project.id);ocr.launch(job);wait(lambda:latest_job(sessions,project.id))
        rows=list_segments(sessions,project.id);assert any(s.source_text=='男生穿搭' for s in rows)
        job=queue_job(sessions,settings,project.id,kind='translate',selected_ids=[s.id for s in rows]);ocr.launch(job);wait(lambda:latest_job(sessions,project.id))
        rows=list_segments(sessions,project.id)
        accepted={'男生穿搭':'Phối đồ nam','秋冬新款':'Mẫu mới Thu Đông','我喜欢这件衬衫':'Tôi thích chiếc áo sơ mi này.'}
        for s in rows:
            assert s.source_text in accepted
            save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,translated_text=accepted[s.source_text],review_status='approved')])
            save_config(sessions,project.id,s.id,ReplacementSettings(fixed_box=True,style=TextStyle(size=28)))
        job=queue_render(sessions,settings,project.id,str(uuid4()),True,True);render.launch(job);m2=wait(lambda:render_history(sessions,project.id)[0])
        job=queue_dub(sessions,settings,project.id,str(uuid4()),'asr');dub.launch(job);wait(lambda:history(sessions,project.id)[0])
        rows=list_speech(sessions,project.id);assert rows
        job=queue_dub(sessions,settings,project.id,str(uuid4()),'translate',selected_ids=[s.id for s in rows]);dub.launch(job);wait(lambda:history(sessions,project.id)[0])
        rows=list_speech(sessions,project.id)
        for s in rows:save_speech(sessions,project.id,[dict(id=s.id,revision=s.revision,translated_text='Tôi thích bộ quần áo này.',review_status='approved')])
        job=queue_dub(sessions,settings,project.id,str(uuid4()),'assemble',rights_confirmed=True);dub.launch(job);m3=wait(lambda:history(sessions,project.id)[0])
        m3_contract=approved_dub(sessions,settings,project.id)
        paths=[settings.storage_root/project.file_path,settings.storage_root/m2.output_path,settings.storage_root/m3.output_path]
        original_hashes=[source_hash(p) for p in paths]
        config=FinalRenderConfig(quality='fast',preview_seconds=3.,style=SubtitleStyle(font_size=56,background=True))
        job=queue_final(sessions,settings,project.id,str(uuid4()),config,is_preview=True);final.launch(job);wait(lambda:final_history(sessions,project.id)[0])
        job=queue_final(sessions,settings,project.id,str(uuid4()),config,rights_confirmed=True,preview_reviewed=True);final.launch(job);done=wait(lambda:final_history(sessions,project.id)[0])
        contract=export_contract(sessions,settings,project.id,exports(sessions,project.id)[0].id)
        assert contract['resolution']==[540,960] and contract['video_codec']=='h264' and contract['audio_codec']=='aac'
        assert abs(contract['duration']-6)<.06 and contract['ffprobe_validation']['audio_sample_rate']==48000
        assert contract['audio_sync_report']['zero_lag_waveform_correlation']>.95
        assert all(r['burned_subtitle'] for r in done.report['validation']['representative_frames'])
        still=tmp_path/'inspected-final.png';frame(settings.storage_root/done.output_path,.5,still,settings,lambda:None)
        with Image.open(still) as image:assert image.size==(540,960)
        assert [source_hash(p) for p in paths]==original_hashes
        # An actual cancelled retry must not damage the completed export.
        config.preview_start=1.;config.preview_seconds=2.
        retry=queue_final(sessions,settings,project.id,str(uuid4()),config,is_preview=True);final.launch(retry)
        deadline=time.time()+15
        while final_history(sessions,project.id)[0].status=='QUEUED' and time.time()<deadline:time.sleep(.02)
        cancel_final(sessions,retry.id)
        while final_history(sessions,project.id)[0].status not in {'COMPLETED','FAILED','CANCELLED'} and time.time()<deadline:time.sleep(.1)
        assert final_history(sessions,project.id)[0].status=='CANCELLED'
        reopened=create_database(settings.database_url)
        assert export_contract(reopened,settings,project.id,contract['export_id'])['sha256']==contract['sha256'];reopened.kw['bind'].dispose()
        print({'seconds':round(time.perf_counter()-started,2),'metadata':contract['ffprobe_validation'],'audio_sync':contract['audio_sync_report'],
               'm2_segments':len(accepted),'m3_segments':len(m3_contract['segments']),'mp4_bytes':contract['file_size']})
    finally:
        ocr.close();render.close();dub.close();final.close();sessions.kw['bind'].dispose()
