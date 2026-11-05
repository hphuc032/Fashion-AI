import io
import math
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import select
from app.core.config import load_settings
from app.database.session import create_database
from app.database.speech_schema import SpeechSegment,DubJob,ACTIVE
from app.providers.asr.base import SpeechPhrase
from app.providers.asr.funasr_provider import parse_funasr,FunASRProvider
from app.providers.asr.whisper_provider import WhisperProvider
from app.providers.tts.base import VoiceSettings,make_tts
from app.services.audio_extractor import audio_info,extract_audio,ffmpeg
from app.services.audio_sync_service import atempo_chain,synchronize,assemble_timeline,RATE
from app.services.speech_segmentation import normalize_phrases
from app.services.speech_repository import list_speech,save_speech,save_speaker
from app.services.dubbing_service import synthesize_cached
from app.services.dub_jobs import queue_dub,run_dub,history,cancel,DubManager
from app.services.dubbing_contract import approved_dub
from app.services.storage_service import import_video
from app.services.frame_extractor import Cancelled
from app.utils.validators import SourceInfo,UserError


@pytest.fixture
def audio_project(tmp_path):
    settings=load_settings();settings.storage_root=tmp_path/'store';settings.database_url=f'sqlite:///{tmp_path/"m3.db"}'
    sessions=create_database(settings.database_url)
    source=tmp_path/'source.mp4'
    subprocess.run([settings.ffmpeg_path,'-nostdin','-y','-v','error','-f','lavfi','-i','color=s=320x240:r=25:d=4',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,timeout=30)
    with source.open('rb') as stream:project=import_video(stream,source.name,SourceInfo(rights_status='owned'),settings,sessions,str(uuid4()))
    yield settings,sessions,project
    sessions.kw['bind'].dispose()


def seed(env,status='approved'):
    settings,sessions,project=env
    row=SpeechSegment(id=str(uuid4()),project_id=project.id,start_time=.5,end_time=2.5,original_text='男生穿搭',translated_text='Phối đồ nam',review_status=status,asr_provider='test',speaker_id='speaker_1')
    with sessions.begin() as db:db.add(row)
    return row


def test_extract_stream_copy_and_asr_wav(audio_project):
    settings,sessions,project=audio_project
    source=settings.storage_root/project.file_path;before=source.read_bytes()
    original,wav=extract_audio(sessions,settings,project.id)
    assert audio_info(original,settings)['codec']=='aac'
    info=audio_info(wav,settings)
    assert (info['sample_rate'],info['channels'])==(16000,1)
    assert abs(info['duration']-4)<1/16000
    assert source.read_bytes()==before
    stamp=wav.stat().st_mtime_ns;assert extract_audio(sessions,settings,project.id)[1].stat().st_mtime_ns==stamp


def test_no_audio_and_corrupted(audio_project,tmp_path):
    settings,sessions,project=audio_project
    path=settings.storage_root/project.file_path
    silent=tmp_path/'silent.mp4'
    ffmpeg(settings,['-i',path,'-an','-c:v','copy',silent])
    with silent.open('rb') as stream:p=import_video(stream,'silent.mp4',SourceInfo(),settings,sessions,str(uuid4()))
    with pytest.raises(UserError,match='không có audio'):extract_audio(sessions,settings,p.id)
    broken=tmp_path/'broken.wav';broken.write_bytes(b'not audio')
    with pytest.raises(UserError):audio_info(broken,settings)


def test_funasr_milliseconds_and_optional_speaker():
    output=parse_funasr([{'sentence_info':[{'start':100,'end':1200,'sentence':'你好。','spk':2}]}])
    assert (output[0].start,output[0].end,output[0].speaker,output[0].confidence)==(.1,1.2,'speaker_2',None)
    fallback=parse_funasr([{'text':'你好','timestamp':[[0,200],[200,500]]}])[0]
    assert fallback.end==.5
    with pytest.raises(UserError):parse_funasr([{'text':'没有时间'}])


def test_chunk_overlap_dedup_and_timing():
    first=normalize_phrases([SpeechPhrase(1,3,'你好。')],0,10)
    output=normalize_phrases([SpeechPhrase(0,1.5,'你好。'),SpeechPhrase(2,4,'男生穿搭。')],2,10,first)
    assert len(output)==2 and output[0].start==1 and output[0].end==3.5
    assert output[1].start==4


@pytest.mark.parametrize('start,end,confidence',[(float('nan'),1,None),(-1,1,None),(2,1,None),(0,1,1.1),(0,1,float('nan'))])
def test_invalid_asr_timestamps(start,end,confidence):
    with pytest.raises(UserError):normalize_phrases([SpeechPhrase(start,end,'你好',confidence)],0,10)


def test_missing_local_models(tmp_path):
    s=load_settings();s.asr_model_dir=tmp_path/'none';s.whisper_model_dir=tmp_path/'none'
    with pytest.raises(UserError,match='FunASR'):FunASRProvider(s)
    with pytest.raises(UserError,match='Whisper'):WhisperProvider(s)


@pytest.mark.parametrize('factor',[float('nan'),0,-1,10])
def test_invalid_atempo(factor):
    with pytest.raises(UserError):atempo_chain(factor)


@pytest.mark.parametrize('factor',[.25,.85,1,1.2,4])
def test_atempo_chain_bounds(factor):
    values=[float(x.split('=')[1]) for x in atempo_chain(factor).split(',')]
    assert all(.5<=x<=2 for x in values) and math.isclose(math.prod(values),factor,rel_tol=1e-8)


def tone(path,duration=.7):sf.write(str(path),.1*np.sin(2*np.pi*220*np.arange(round(duration*RATE))/RATE),RATE,subtype='PCM_16')


@pytest.mark.parametrize('duration,available,expected',[(.5,2,1),(1.1,1,1.1),(.9,1,.9)])
def test_sync_policy_and_normalization(tmp_path,duration,available,expected):
    settings=load_settings();source=tmp_path/'tts.wav';out=tmp_path/'sync.wav';tone(source,duration)
    result=synchronize(source,out,available,VoiceSettings(),settings)
    assert math.isclose(result['sync_factor'],expected,abs_tol=.001)
    data,sr=sf.read(out);assert sr==RATE and max(abs(data))<.99
    assert len(data)/sr<=available+.035


def test_severe_mismatch_not_compressed(tmp_path):
    s=load_settings();source=tmp_path/'tts.wav';out=tmp_path/'sync.wav';tone(source,2)
    with pytest.raises(UserError,match='quá dài'):synchronize(source,out,.5,VoiceSettings(),s)
    assert not out.exists()


def test_assembly_silence_position_duration_overlap_cleanup(tmp_path):
    source=tmp_path/'tts.wav';tone(source,.5);out=tmp_path/'master.wav'
    assemble_timeline([dict(start=1,end=2,path=source)],out,3)
    data,sr=sf.read(out);assert len(data)==3*RATE and np.max(abs(data[:RATE]))==0
    assert np.max(abs(data[RATE:RATE+1000]))>.05 and np.max(abs(data[2*RATE:]))==0
    with pytest.raises(UserError,match='chồng'):assemble_timeline([dict(start=1,end=2,path=source),dict(start=1.1,end=2,path=source)],out,3)
    assert not out.exists()


class FakeTTS:
    identity='test-tone-not-a-real-voice'
    calls=0
    def voices(self):return [dict(id='test')]
    def synthesize(self,text,voice,output,check):self.calls+=1;check();tone(output)


def test_tts_cache_and_cloud_gate(audio_project):
    settings,sessions,project=audio_project;p=FakeTTS()
    a=synthesize_cached(sessions,settings,project.id,'Phối đồ nam',VoiceSettings(),p,lambda:None)
    assert synthesize_cached(sessions,settings,project.id,'Phối đồ nam',VoiceSettings(),p,lambda:None)==a and p.calls==1
    synthesize_cached(sessions,settings,project.id,'Phối đồ nam',VoiceSettings(rate=1.1),p,lambda:None)
    assert p.calls==2
    with pytest.raises(UserError,match='Azure'):make_tts(settings,VoiceSettings(provider='azure'))


def test_speech_approval_stale_and_manual_speaker(audio_project):
    settings,sessions,project=audio_project;s=seed(audio_project)
    save_speech(sessions,project.id,[dict(id=s.id,revision=0,translated_text='Áo đẹp',speaker_id='speaker_2',review_status='approved')])
    row=list_speech(sessions,project.id)[0]
    assert row.review_status=='pending' and row.speaker_id=='speaker_2'
    with pytest.raises(UserError):save_speech(sessions,project.id,[dict(id=s.id,revision=0)])
    save_speaker(sessions,project.id,'speaker_2',VoiceSettings())


def test_job_state_contract_restart_and_stale(audio_project):
    settings,sessions,project=audio_project;s=seed(audio_project)
    token=str(uuid4());job=queue_dub(sessions,settings,project.id,token,'assemble',rights_confirmed=True)
    assert queue_dub(sessions,settings,project.id,token,'assemble').id==job.id
    with pytest.raises(UserError):queue_dub(sessions,settings,project.id,str(uuid4()),'preview')
    run_dub(sessions,job.id,tts_factory=lambda *args:FakeTTS())
    stored=history(sessions,project.id)[0];assert stored.status=='COMPLETED',stored.error_message
    contract=approved_dub(sessions,settings,project.id)
    assert contract['duration']==4 and len(contract['segments'])==1
    reopened=create_database(settings.database_url);assert approved_dub(reopened,settings,project.id)['job_id']==job.id;reopened.kw['bind'].dispose()
    save_speech(sessions,project.id,[dict(id=s.id,revision=0,translated_text='Đã sửa')])
    with pytest.raises(UserError):approved_dub(sessions,settings,project.id)


def test_cancel_failure_rights_and_old_audio_safe(audio_project):
    settings,sessions,project=audio_project;seed(audio_project)
    with pytest.raises(UserError,match='quyền'):queue_dub(sessions,settings,project.id,str(uuid4()),'assemble')
    job=queue_dub(sessions,settings,project.id,str(uuid4()),'assemble',rights_confirmed=True)
    cancel(sessions,job.id);run_dub(sessions,job.id,tts_factory=lambda *args:FakeTTS())
    assert history(sessions,project.id)[0].status=='CANCELLED'
    class Broken(FakeTTS):
        def synthesize(self,text,voice,out,check):out.write_bytes(b'bad');raise UserError('provider fixture')
    job=queue_dub(sessions,settings,project.id,str(uuid4()),'assemble',rights_confirmed=True)
    run_dub(sessions,job.id,tts_factory=lambda *args:Broken())
    assert history(sessions,project.id)[0].status=='FAILED'
    assert not list(settings.storage_root.rglob('*.partial.wav'))


def test_other_queues_block_while_dubbing(audio_project):
    from app.services.ocr_service import queue_job
    settings,sessions,project=audio_project
    queue_dub(sessions,settings,project.id,str(uuid4()),'preview')
    with pytest.raises(UserError,match='tác vụ'):queue_job(sessions,settings,project.id)


def test_asr_mock_and_translation_worker_stages(audio_project):
    settings,sessions,project=audio_project
    class ASR:
        identity='mock-only'
        def transcribe(self,path,check):return [SpeechPhrase(.2,2.5,'男生穿搭')]
    job=queue_dub(sessions,settings,project.id,str(uuid4()),'asr')
    run_dub(sessions,job.id,asr_factory=lambda *args:ASR())
    assert history(sessions,project.id)[0].status=='COMPLETED'
    s=list_speech(sessions,project.id)[0];assert s.confidence is None
    class Translator:
        def __init__(self,*args,**kwargs):pass
        def translate(self,*args):return 'Phối đồ nam','test'
    job=queue_dub(sessions,settings,project.id,str(uuid4()),'translate',selected_ids=[s.id])
    run_dub(sessions,job.id,translator_factory=Translator)
    assert list_speech(sessions,project.id)[0].translated_text=='Phối đồ nam'


def test_dubbing_studio_populated_and_empty(audio_project,monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    settings,sessions,project=audio_project;st.cache_resource.clear()
    monkeypatch.setenv('STORAGE_ROOT',str(settings.storage_root));monkeypatch.setenv('DATABASE_URL',settings.database_url)
    monkeypatch.setattr('app.ui.dubbing_studio.manager',lambda *args:None)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/main.py')).run(timeout=30)
    app.sidebar.radio[0].set_value('AI Dubbing Studio').run()
    assert not app.exception and not app.error
    assert any('Chưa có lời' in x.value for x in app.info)
    seed(audio_project);app.run();assert not app.exception and not app.error
    assert any(b.label=='Lưu sửa và duyệt lời' for b in app.button)
    st.cache_resource.clear()


@pytest.mark.parametrize('container',['mov','mkv'])
def test_other_supported_containers(audio_project,tmp_path,container):
    settings,sessions,project=audio_project
    source=tmp_path/f'input.{container}'
    ffmpeg(settings,['-i',settings.storage_root/project.file_path,'-c','copy',source])
    with source.open('rb') as stream:p=import_video(stream,source.name,SourceInfo(),settings,sessions,str(uuid4()))
    _,wav=extract_audio(sessions,settings,p.id)
    assert audio_info(wav,settings)['sample_rate']==16000


def test_initial_audio_offset_preserved(audio_project,tmp_path):
    settings,sessions,project=audio_project
    delayed=tmp_path/'delayed.mp4'
    ffmpeg(settings,['-f','lavfi','-i','color=s=320x240:r=25:d=3','-itsoffset','0.7','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1',
                     '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',delayed])
    with delayed.open('rb') as stream:p=import_video(stream,delayed.name,SourceInfo(),settings,sessions,str(uuid4()))
    _,wav=extract_audio(sessions,settings,p.id)
    data,sr=sf.read(wav)
    assert np.max(np.abs(data[:int(.6*sr)]))<.001
    assert np.max(np.abs(data[int(.8*sr):int(1.2*sr)]))>.01


def test_dead_worker_recovery_and_pending_gate(audio_project):
    settings,sessions,project=audio_project;seed(audio_project,status='pending')
    with pytest.raises(UserError,match='pending'):queue_dub(sessions,settings,project.id,str(uuid4()),'assemble',rights_confirmed=True)
    job=queue_dub(sessions,settings,project.id,str(uuid4()),'preview')
    with sessions.begin() as db:
        row=db.get(DubJob,job.id);row.status='GENERATING_TTS';row.pid=99999999
    manager=DubManager(settings,sessions)
    try:
        deadline=time.time()+5
        while history(sessions,project.id)[0].status in ACTIVE and time.time()<deadline:time.sleep(.1)
        assert history(sessions,project.id)[0].status=='FAILED'
    finally:manager.close()


def test_cancellation_cleans_assembly(tmp_path):
    source=tmp_path/'tts.wav';out=tmp_path/'master.wav';tone(source)
    def stop():raise Cancelled('fixture')
    with pytest.raises(Cancelled):assemble_timeline([dict(start=0,end=1,path=source)],out,5,stop)
    assert source.exists() and not out.exists()


def test_azure_voice_validation_and_ssml_escaping(tmp_path,monkeypatch):
    from app.providers.tts.azure_tts_provider import AzureTTS
    monkeypatch.setenv('AZURE_SPEECH_KEY','unit-test-placeholder')
    monkeypatch.setenv('AZURE_SPEECH_REGION','eastus')
    class Reply:
        status_code=200
        content=b'unit fake wave'
        def raise_for_status(self):pass
        def json(self):return [{'Locale':'vi-VN','ShortName':'test-voice','DisplayName':'Test','Gender':'Female'}]
    payload=[]
    monkeypatch.setattr('app.providers.tts.azure_tts_provider.requests.get',lambda *a,**k:Reply())
    def post(*a,**k):payload.append(k['data']);return Reply()
    monkeypatch.setattr('app.providers.tts.azure_tts_provider.requests.post',post)
    provider=AzureTTS(load_settings())
    with pytest.raises(UserError):provider.synthesize('Test',VoiceSettings(provider='azure',voice='missing',cloud_confirmed=True),tmp_path/'bad.wav',lambda:None)
    provider.synthesize('Áo <đẹp> & mới',VoiceSettings(provider='azure',voice='test-voice',cloud_confirmed=True),tmp_path/'out.wav',lambda:None)
    assert b'&lt;' in payload[0] and b'&amp;' in payload[0]


def test_clipping_blocks_assembly(tmp_path):
    path=tmp_path/'clipped.wav';sf.write(path,np.ones(1000),RATE,subtype='PCM_16')
    out=tmp_path/'master.wav'
    with pytest.raises(UserError,match='clipping'):assemble_timeline([dict(start=0,end=1,path=path)],out,2)
    assert not out.exists()
