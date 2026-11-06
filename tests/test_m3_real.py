"""Opt-in real local ASR→Argos→review→Vietnamese TTS→WAV; production workers."""
import os
import time
from pathlib import Path
from uuid import uuid4
import numpy as np
import pytest
import soundfile as sf
from app.core.config import load_settings
from app.database.session import create_database
from app.services.audio_extractor import audio_info,ffmpeg
from app.services.storage_service import import_video
from app.services.speech_repository import list_speech,save_speech
from app.services.dub_jobs import queue_dub,DubManager,history,cancel
from app.services.dubbing_contract import approved_dub
from app.utils.validators import SourceInfo
from scripts.generate_m3_fixture import generate


@pytest.mark.skipif(os.getenv('M3_RUN_REAL')!='1',reason='M3_RUN_REAL=1 enables actual local Whisper/Argos/Vietnamese TTS workers')
def test_real_mandarin_to_vietnamese_dub(tmp_path):
    settings=load_settings();fixture_models=settings.storage_root/'models/vits-icefall-zh-aishell3'
    wav=generate(tmp_path/'mandarin.wav',fixture_models)
    source=tmp_path/'source.mp4'
    ffmpeg(settings,['-f','lavfi','-i','color=s=320x240:r=25:d=5','-i',wav,'-af','apad','-t','5','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',source])
    settings.storage_root=tmp_path/'media';settings.database_url=f'sqlite:///{tmp_path/"real-dub.db"}'
    settings.asr_provider='whisper';settings.translation_provider='argos'
    sessions=create_database(settings.database_url)
    with source.open('rb') as stream:project=import_video(stream,'synthetic-mandarin.mp4',SourceInfo(rights_status='owned',creator_name='Original synthetic AISHELL3 fixture'),settings,sessions,str(uuid4()))
    original=(settings.storage_root/project.file_path).read_bytes()
    manager=DubManager(settings,sessions);started=time.perf_counter()
    def run(kind,**kwargs):
        job=queue_dub(sessions,settings,project.id,str(uuid4()),kind,**kwargs);manager.launch(job)
        deadline=time.time()+180
        while time.time()<deadline:
            current=history(sessions,project.id)[0]
            if current.status in {'COMPLETED','FAILED','CANCELLED'}:
                assert current.status=='COMPLETED',current.error_message
                return current
            time.sleep(.1)
        pytest.fail('Speech worker timeout')
    try:
        run('asr')
        rows=list_speech(sessions,project.id)
        assert rows and any(('喜欢' in row.original_text or '喜歡' in row.original_text) and '衣服' in row.original_text for row in rows),[(r.original_text,r.start_time,r.end_time) for r in rows]
        assert all(0<=s.start_time<s.end_time<=5 and s.confidence is None for s in rows)
        run('translate',selected_ids=[s.id for s in rows])
        rows=list_speech(sessions,project.id)
        assert all(s.translated_text.strip() and s.review_status=='pending' for s in rows)
        automatic=[s.translated_text for s in rows]
        # Human acceptance fixture: review/approve actual provider output, correcting
        # garment wording explicitly if needed (not an automatic fallback).
        for s in rows:
            save_speech(sessions,project.id,[dict(id=s.id,revision=s.revision,translated_text='Tôi thích bộ quần áo này.',review_status='approved')])
        run('preview')
        preview=history(sessions,project.id)[0];assert audio_info(settings.storage_root/preview.output_path,settings)['duration']>0
        completed=run('assemble',rights_confirmed=True)
        contract=approved_dub(sessions,settings,project.id)
        output=settings.storage_root/completed.output_path
        info=sf.info(output);audio,sr=sf.read(output)
        assert info.frames==5*24000 and sr==24000 and np.max(np.abs(audio))>.01 and np.max(np.abs(audio))<.99
        assert contract['duration']==5 and contract['segments'][0]['translated_text']=='Tôi thích bộ quần áo này.'
        retry=queue_dub(sessions,settings,project.id,str(uuid4()),'assemble',rights_confirmed=True);manager.launch(retry)
        deadline=time.time()+15
        while history(sessions,project.id)[0].status=='QUEUED' and time.time()<deadline:time.sleep(.02)
        cancel(sessions,retry.id)
        while history(sessions,project.id)[0].status in {'QUEUED','EXTRACTING_AUDIO','GENERATING_TTS','SYNCHRONIZING','ASSEMBLING'} and time.time()<deadline:time.sleep(.1)
        assert history(sessions,project.id)[0].status=='CANCELLED'
        assert output.is_file() and (settings.storage_root/project.file_path).read_bytes()==original
        reopened=create_database(settings.database_url)
        assert approved_dub(reopened,settings,project.id)['job_id']==completed.id;reopened.kw['bind'].dispose()
        print({'seconds':round(time.perf_counter()-started,2),'transcript':[s.original_text for s in rows],'automatic_translation':automatic,'master_seconds':info.duration,'master_samples':info.frames,'bytes':output.stat().st_size})
    finally:manager.close();sessions.kw['bind'].dispose()
