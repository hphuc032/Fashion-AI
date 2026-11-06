import math
import subprocess
from pathlib import Path
from uuid import uuid4
import numpy as np
import pytest
from app.core.config import load_settings
from app.services.final_render_config import FinalRenderConfig,SubtitleStyle,dimensions
from app.services.subtitle_service import ass_time,escape_ass,ass_color,generate_ass
from app.utils.validators import UserError
from app.services.video_mux_service import timeline_options,run_mux,capabilities
from app.services.final_output_validation import validate_output,validate_metadata
from app.services.audio_extractor import ffmpeg
import soundfile as sf
from app.database.session import create_database
from app.database.m1_models import OCRJob,TextSegment
from app.database.speech_schema import SpeechSegment
from app.database.final_schema import FinalRenderJob
from app.services.storage_service import import_video
from app.utils.validators import SourceInfo
from app.services.replacement_repository import save_config
from app.services.text_compositor import ReplacementSettings
from app.services.text_layout import TextStyle
from app.services.render_jobs import queue_render,run_render
from app.services.dub_jobs import queue_dub,run_dub
from app.services.final_render_service import queue_final,run_final,final_history,cancel_final,exports,move_export,export_contract,retrieve_inputs
from tests.test_m3 import FakeTTS
from app.services.frame_extractor import Cancelled


def speech(text='Tiếng Việt đầy đủ dấu, chiếc áo rất thoải mái.',start=.123,end=2.345,speaker='speaker_1'):
    return {'id':str(uuid4()),'start_time':start,'end_time':end,'translated_text':text,'speaker_id':speaker,'review_status':'approved'}


@pytest.mark.parametrize('seconds,expected',[(0,'0:00:00.00'),(.125,'0:00:00.13'),(62.34,'0:01:02.34'),(3601.999,'1:00:02.00')])
def test_ass_fractional_time(seconds,expected):assert ass_time(seconds)==expected


@pytest.mark.parametrize('value',[-1,float('inf'),float('nan')])
def test_bad_ass_time(value):
    with pytest.raises(UserError):ass_time(value)


def test_ass_unicode_escaping_and_approved_source(tmp_path):
    path=tmp_path/'caption.ass';s=speech('Áo {đẹp}, giá 100.000đ \\N vẫn nguyên.\nDòng thứ hai!')
    result=generate_ass([s],path,1080,1920,3)
    content=path.read_text(encoding='utf-8')
    assert '[Script Info]' in content and 'ScriptType: v4.00+' in content and 'Áo' in content
    assert r'\{đẹp\}' in content and '\\\u2060N' in content and '0:00:00.12,0:00:02.34' in content
    assert result['events'][0]['text']==s['translated_text'] and result['language']=='vie'
    assert ass_color('#123456')=='&H00563412'


@pytest.mark.parametrize('start,end',[(-.1,2),(1,1),(2,1),(0,4),(float('nan'),2)])
def test_ass_invalid_event_boundaries(tmp_path,start,end):
    with pytest.raises(UserError):generate_ass([speech(start=start,end=end)],tmp_path/'bad.ass',540,960,3)


def test_long_caption_and_missing_glyph_block(tmp_path):
    with pytest.raises(UserError):generate_ass([speech('Rất dài '*200)],tmp_path/'long.ass',320,240,3,readability_confirmed=True)
    with pytest.raises(UserError,match='glyph'):generate_ass([speech('\U0010ffff')],tmp_path/'missing.ass',540,960,3)


def test_subtitle_overlap_speaker_styles_and_fallback(tmp_path):
    s=[speech('Lời người một.',0,2,'a'),speech('Lời người hai.',.5,2.5,'b')]
    report=generate_ass(s,tmp_path/'overlap.ass',540,960,3,style=SubtitleStyle(font='not-installed'),speaker_styles={'b':SubtitleStyle(primary_color='#ffff00')})
    a,b=[r['bbox'] for r in report['events']]
    assert b[3]<=a[1]+30 and report['fonts']
    assert '&H0000FFFF' in (tmp_path/'overlap.ass').read_text(encoding='utf-8')


def test_readability_warning_and_preview_clip(tmp_path):
    s=speech('Nhanh!',.05,.25)
    with pytest.raises(UserError,match='ngắn'):generate_ass([s],tmp_path/'short.ass',540,960,3)
    result=generate_ass([speech(start=.5,end=2.5)],tmp_path/'preview.ass',540,960,3,window=(1.,2.))
    assert result['events'][0]['start']==0 and result['events'][0]['end']==1


def test_presets_dimensions():
    assert dimensions(320,240,FinalRenderConfig())==(320,240)
    assert dimensions(320,240,FinalRenderConfig(preset='tiktok'))==(1080,1920)
    assert dimensions(540,960,FinalRenderConfig(),True)==(360,640)


@pytest.fixture
def mux_media(tmp_path):
    settings=load_settings();video=tmp_path/'m2.mp4';audio=tmp_path/'dub.wav'
    ffmpeg(settings,['-f','lavfi','-i','color=c=0x244568:s=320x240:r=25:d=3','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=3',
                     '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',video])
    sr=24000;signal=.12*np.sin(2*np.pi*220*np.arange(3*sr)/sr);signal[2*sr:]=0
    sf.write(audio,signal,sr,subtype='PCM_16')
    return settings,video,audio


@pytest.mark.parametrize('mode',['burn','soft','none'])
def test_real_mux_modes_audio_exclusion_and_validation(mux_media,tmp_path,mode):
    settings,video,audio=mux_media
    config=FinalRenderConfig(subtitle_mode=mode,soft_compatibility_confirmed=mode=='soft')
    options=timeline_options(video,audio,3,config,settings)
    ass=tmp_path/'subtitles.ass'
    subtitles=generate_ass([speech()],ass,320,240,3,soft=mode=='soft')
    output=tmp_path/'output.mp4'
    before=(video.read_bytes(),audio.read_bytes())
    run_mux(video,audio,ass,output,options,config,settings,subtitles)
    report=validate_output(output,video,audio,options,config,subtitles,settings)
    assert report['metadata']['audio_codec']=='aac' and report['metadata']['width']==320
    assert report['audio_sync']['zero_lag_waveform_correlation']>.95
    if mode=='burn':assert report['representative_frames'][0]['burned_subtitle']['changed_pixels']>=10
    if mode=='soft':assert report['soft_subtitle_text_validated']
    assert before==(video.read_bytes(),audio.read_bytes())


def test_soft_compatibility_and_crop_confirmation(mux_media,tmp_path):
    settings,video,audio=mux_media
    config=FinalRenderConfig(subtitle_mode='soft')
    options=timeline_options(video,audio,3,config,settings)
    with pytest.raises(UserError,match='Soft'):run_mux(video,audio,tmp_path/'subtitles.ass',tmp_path/'output.mp4',options,config,settings,{'fonts':[]})
    with pytest.raises(UserError,match='Crop'):timeline_options(video,audio,3,FinalRenderConfig(preset='tiktok',aspect_mode='crop'),settings)


def test_audio_duration_policy(mux_media,tmp_path):
    settings,video,audio=mux_media
    short=tmp_path/'short.wav';long=tmp_path/'long.wav'
    sf.write(short,np.zeros(24000),24000);sf.write(long,np.zeros(4*24000),24000)
    assert timeline_options(video,short,3,FinalRenderConfig(),settings)['audio_padding_seconds']==2
    with pytest.raises(UserError,match='dài hơn'):timeline_options(video,long,3,FinalRenderConfig(),settings)


def test_invalid_output_metadata(mux_media,tmp_path):
    settings,video,audio=mux_media
    options=timeline_options(video,audio,3,FinalRenderConfig(),settings)
    path=tmp_path/'empty.mp4';path.touch()
    with pytest.raises(UserError):validate_metadata(path,options,'burn',settings)
    # The source is H264/AAC, but lacks our required48000 mono/faststart contract.
    wrong=dict(options,width=640)
    with pytest.raises(UserError):validate_metadata(video,wrong,'none',settings)


@pytest.fixture
def integrated(mux_media,tmp_path):
    settings,video,audio=mux_media
    settings.storage_root=tmp_path/'storage';settings.database_url=f'sqlite:///{tmp_path/"final.db"}'
    sessions=create_database(settings.database_url)
    with video.open('rb') as stream:project=import_video(stream,'original-synthetic.mp4',SourceInfo(rights_status='owned'),settings,sessions,str(uuid4()))
    ocr_id=str(uuid4());segment_id=str(uuid4())
    with sessions.begin() as db:
        db.add(OCRJob(id=ocr_id,project_id=project.id,kind='ocr',status='COMPLETED',config={},total_frames=1,completed_frames=1));db.flush()
        db.add(TextSegment(id=segment_id,project_id=project.id,job_id=ocr_id,source_text='男生穿搭',translated_text='Phối đồ nam',start_time=0,end_time=3,bounding_box=[20,20,220,50],confidence=.99,review_status='approved'))
        db.add(SpeechSegment(id=str(uuid4()),project_id=project.id,start_time=.3,end_time=2.,original_text='我喜欢这件衣服',translated_text='Tôi thích bộ quần áo này.',asr_provider='unit fixture',review_status='approved'))
    save_config(sessions,project.id,segment_id,ReplacementSettings(fixed_box=True,style=TextStyle(size=24)))
    m2=queue_render(sessions,settings,project.id,str(uuid4()),True,True);run_render(sessions,m2.id)
    m3=queue_dub(sessions,settings,project.id,str(uuid4()),'assemble',rights_confirmed=True);run_dub(sessions,m3.id,tts_factory=lambda *a:FakeTTS())
    yield settings,sessions,project
    sessions.kw['bind'].dispose()


def test_complete_preview_final_library_restore_and_reopen(integrated):
    settings,sessions,project=integrated;config=FinalRenderConfig(preview_seconds=1.5)
    with pytest.raises(UserError,match='preview'):queue_final(sessions,settings,project.id,str(uuid4()),config,rights_confirmed=True,preview_reviewed=True)
    preview=queue_final(sessions,settings,project.id,str(uuid4()),config,is_preview=True);run_final(sessions,preview.id)
    assert final_history(sessions,project.id)[0].status=='COMPLETED',final_history(sessions,project.id)[0].error_message
    assert queue_final(sessions,settings,project.id,str(uuid4()),config,is_preview=True).id==preview.id
    final=queue_final(sessions,settings,project.id,str(uuid4()),config,rights_confirmed=True,preview_reviewed=True);run_final(sessions,final.id)
    assert final_history(sessions,project.id)[0].status=='COMPLETED',final_history(sessions,project.id)[0].error_message
    row=exports(sessions,project.id)[0];contract=export_contract(sessions,settings,project.id,row.id)
    assert contract['resolution']==[320,240] and contract['audio_codec']=='aac'
    reopened=create_database(settings.database_url);assert exports(reopened,project.id)[0].id==row.id;reopened.kw['bind'].dispose()
    with pytest.raises(UserError):move_export(sessions,settings,project.id,row.id)
    move_export(sessions,settings,project.id,row.id,True)
    assert exports(sessions,project.id)==[]
    move_export(sessions,settings,project.id,row.id,True,restore=True)
    assert export_contract(sessions,settings,project.id,row.id)['sha256']==row.sha256


def test_missing_inputs_and_cross_project_paths(m1):
    settings,sessions,project=m1
    with pytest.raises(UserError,match='M2'):queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)


def test_final_cancel_single_slot_and_failed_cleanup(integrated):
    settings,sessions,project=integrated
    job=queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)
    with pytest.raises(UserError):queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)
    with pytest.raises(UserError):queue_dub(sessions,settings,project.id,str(uuid4()),'preview')
    cancel_final(sessions,job.id);run_final(sessions,job.id)
    assert final_history(sessions,project.id)[0].status=='CANCELLED'
    job=queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)
    def broken(*args,**kwargs):raise UserError('fixture render failure')
    run_final(sessions,job.id,muxer=broken)
    assert final_history(sessions,project.id)[0].status=='FAILED' and not list(settings.storage_root.rglob('*.partial.mp4'))


@pytest.mark.parametrize('preset,aspect,preview',[('tiktok','fit',False),('tiktok','crop',True),('compact','fit',True)])
def test_real_output_presets_and_preview_range(mux_media,tmp_path,preset,aspect,preview):
    settings,video,audio=mux_media
    config=FinalRenderConfig(preset=preset,aspect_mode=aspect,crop_confirmed=True,quality='fast',preview_start=.5,preview_seconds=1.)
    options=timeline_options(video,audio,3,config,settings,preview)
    report=generate_ass([speech()],tmp_path/'subtitles.ass',options['width'],options['height'],3,window=(options['start'],options['start']+options['duration']))
    output=tmp_path/'preset.mp4'
    run_mux(video,audio,tmp_path/'subtitles.ass',output,options,config,settings,report)
    validated=validate_output(output,video,audio,options,config,report,settings)
    if preset=='tiktok' and not preview:assert (validated['metadata']['width'],validated['metadata']['height'])==(1080,1920)
    if preview:assert abs(validated['metadata']['duration']-1)<.06


def test_final_studio_existing_inputs_and_first_use(integrated,monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    settings,sessions,project=integrated;st.cache_resource.clear()
    monkeypatch.setenv('STORAGE_ROOT',str(settings.storage_root));monkeypatch.setenv('DATABASE_URL',settings.database_url)
    monkeypatch.setattr('app.ui.final_export_studio.manager',lambda *args:None)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/main.py')).run(timeout=30)
    app.sidebar.radio[0].set_value('Final Export Studio').run()
    assert not app.exception and not app.error
    assert any('đúng dự án' in s.value for s in app.success)
    assert any(b.label=='Xuất MP4 cuối' for b in app.button)
    next(b for b in app.button if b.label=='Áp dụng cấu hình xuất').click().run()
    assert not app.exception and not app.error
    st.cache_resource.clear()


def test_real_soft_literal_ass_escapes(mux_media,tmp_path):
    settings,video,audio=mux_media;config=FinalRenderConfig(subtitle_mode='soft',soft_compatibility_confirmed=True)
    options=timeline_options(video,audio,3,config,settings)
    report=generate_ass([speech('Áo {đẹp}, giá 100k \\N thật.')],tmp_path/'subtitles.ass',320,240,3,soft=True)
    output=tmp_path/'literal.mp4';run_mux(video,audio,tmp_path/'subtitles.ass',output,options,config,settings,report)
    assert validate_output(output,video,audio,options,config,report,settings)['soft_subtitle_text_validated']


def test_real_short_audio_pad_and_background_mix(mux_media,tmp_path):
    settings,video,audio=mux_media
    short=tmp_path/'short.wav';bg=tmp_path/'background.wav'
    sf.write(short,.1*np.sin(2*np.pi*220*np.arange(24000)/24000),24000)
    sf.write(bg,.03*np.sin(2*np.pi*660*np.arange(3*24000)/24000),24000)
    config=FinalRenderConfig(subtitle_mode='none')
    options=timeline_options(video,short,3,config,settings)
    report=generate_ass([],tmp_path/'subtitles.ass',320,240,3)
    output=tmp_path/'mixed.mp4';run_mux(video,short,tmp_path/'subtitles.ass',output,options,config,settings,report,background=bg)
    validation=validate_output(output,video,short,options,config,report,settings,background=bg)
    assert validation['metadata']['duration']==3 and validation['audio_sync']['zero_lag_waveform_correlation']>.95


def test_cancelled_mux_cleans_only_owned_output(mux_media,tmp_path):
    settings,video,audio=mux_media;config=FinalRenderConfig()
    options=timeline_options(video,audio,3,config,settings)
    report=generate_ass([speech()],tmp_path/'subtitles.ass',320,240,3)
    output=tmp_path/'cancel.partial.mp4'
    def stop():raise Cancelled('fixture')
    original=video.read_bytes()
    with pytest.raises(Cancelled):run_mux(video,audio,tmp_path/'subtitles.ass',output,options,config,settings,report,check=stop)
    assert not output.exists() and video.read_bytes()==original
    with pytest.raises(UserError,match='ghi đè'):run_mux(video,audio,tmp_path/'subtitles.ass',video,options,config,settings,report)


@pytest.mark.parametrize('kind',['no_audio','no_video','wrong_codec'])
def test_output_missing_streams_or_wrong_codec(mux_media,tmp_path,kind):
    settings,video,audio=mux_media;output=tmp_path/'invalid.mp4'
    if kind=='no_audio':ffmpeg(settings,['-i',video,'-an','-c:v','copy','-movflags','+faststart',output])
    elif kind=='no_video':ffmpeg(settings,['-i',audio,'-c:a','aac','-movflags','+faststart',output])
    else:ffmpeg(settings,['-i',video,'-c:v','mpeg4','-c:a','aac','-movflags','+faststart',output])
    options=timeline_options(video,audio,3,FinalRenderConfig(),settings)
    with pytest.raises(UserError):validate_metadata(output,options,'none',settings)


def test_stale_m2_config_blocks_final_inputs(integrated):
    settings,sessions,project=integrated
    from app.services.ocr_repository import list_segments
    row=list_segments(sessions,project.id)[0]
    save_config(sessions,project.id,row.id,ReplacementSettings(fixed_box=True,opacity=.5))
    with pytest.raises(UserError,match='M2'):queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)


def test_edit_during_mux_is_not_published(integrated):
    settings,sessions,project=integrated
    from app.services.ocr_repository import list_segments,save_reviews
    row=list_segments(sessions,project.id)[0]
    job=queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)
    def editing_mux(*args,**kwargs):
        result=run_mux(*args,**kwargs)
        save_reviews(sessions,project.id,[dict(id=row.id,revision=row.revision,translated_text='Lời đã sửa')])
        return result
    run_final(sessions,job.id,muxer=editing_mux)
    assert final_history(sessions,project.id)[0].status=='FAILED' and exports(sessions,project.id)==[]
    assert not list((settings.storage_root/f'projects/{project.id}/final').rglob('*.mp4'))


def test_invalid_separated_background_provenance(integrated):
    settings,sessions,project=integrated
    config=FinalRenderConfig(background_path=f'projects/{project.id}/audio/original.mka')
    with pytest.raises(UserError,match='background'):retrieve_inputs(sessions,settings,project.id,config)


def test_final_dead_worker_recovery(integrated):
    import time
    from app.services.final_job_manager import FinalManager
    settings,sessions,project=integrated
    job=queue_final(sessions,settings,project.id,str(uuid4()),is_preview=True)
    with sessions.begin() as db:
        row=db.get(FinalRenderJob,job.id);row.status='MUXING';row.pid=99999999
    manager=FinalManager(settings,sessions)
    try:
        deadline=time.time()+5
        while final_history(sessions,project.id)[0].status not in {'COMPLETED','FAILED','CANCELLED'} and time.time()<deadline:time.sleep(.1)
        assert final_history(sessions,project.id)[0].status=='FAILED'
    finally:manager.close()


def test_disabled_subtitles_do_not_require_unused_glyph_or_layout(integrated):
    settings,sessions,project=integrated
    config=FinalRenderConfig(subtitle_mode='none',style=SubtitleStyle(primary_color='unused-invalid-color'))
    job=queue_final(sessions,settings,project.id,str(uuid4()),config,is_preview=True);run_final(sessions,job.id)
    row=final_history(sessions,project.id)[0]
    assert row.status=='COMPLETED',row.error_message
    assert row.report['subtitles']['events']==[] and row.report['validation']['metadata']['subtitle_codec'] is None
