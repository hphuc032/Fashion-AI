import io
import json
import os
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from uuid import uuid4

import cv2
import numpy as np
import pytest
from PIL import Image
from sqlalchemy import select

from app.core.config import load_settings
from app.database.models import Project
from app.database.render_schema import RenderJob,ReplacementConfig
from app.database.session import create_database
from app.services.frame_extractor import Cancelled
from app.services.ocr_repository import list_segments,save_reviews
from app.services.render_jobs import queue_render,run_render,render_history,cancel_render
from app.services.replacement_repository import save_config,snapshot_items,validate_snapshot
from app.services.text_compositor import ReplacementSettings,compose,region_at,valid_box
from app.services.text_layout import TextStyle,available_fonts,load_font,text_layer
from app.services.video_renderer import render_video,stream_info
from app.services.storage_service import import_video
from app.services.video_service import probe_video
from app.utils.validators import SourceInfo,UserError
from tests.test_m1_integration import detect_fixture


def item(mode='solid',**settings):
    return dict(segment_id=str(uuid4()),source='男生穿搭',text='Phối đồ nam',start=.25,end=1.75,box=[30,40,240,70],
                settings=ReplacementSettings(removal_mode=mode,fixed_box=True,**settings).model_dump(),detections=[])


@pytest.mark.parametrize('box',[[0,0,10,10],[5,6,200,30]])
def test_box_valid(box):
    assert valid_box(box,320,240)==box


@pytest.mark.parametrize('box',[[-1,0,10,10],[0,0,0,10],[319,0,10,10],[0,float('nan'),10,10],[1,2,3]])
def test_box_invalid(box):
    with pytest.raises(UserError):valid_box(box,320,240)


def test_tracking_moving_and_gap():
    spec=item()
    spec['settings']['fixed_box']=False
    spec['tracking_gap']=1.1
    spec['detections']=[dict(time=0,box=[10,10,100,30],confidence=.99),dict(time=1,box=[30,20,100,30],confidence=.99)]
    assert region_at(spec,.5,320,240)[0]==[20,15,100,30]
    assert region_at(spec,3,320,240)[1]


@pytest.mark.parametrize('mode',['solid','blur','inpaint','overlay'])
def test_removal_unicode_outside_preserved(mode):
    rng=np.random.default_rng(1)
    frame=rng.integers(0,255,(240,320,3),dtype=np.uint8)
    output,_=compose(frame,1,[item(mode)],strict=True)
    assert np.array_equal(frame[:25],output[:25])
    assert np.array_equal(frame[:,290:],output[:,290:])
    assert not np.array_equal(frame[40:110,30:270],output[40:110,30:270])
    assert np.array_equal(frame,compose(frame,0,[item(mode)])[0])
    assert np.array_equal(frame,compose(frame,1.75,[item(mode)])[0])


def test_overlay_leaves_original_region_when_position_separate():
    frame=np.full((240,320,3),80,np.uint8)
    spec=item('overlay',text_box=[30,140,240,70])
    output,_=compose(frame,1,[spec])
    assert np.array_equal(frame[40:110],output[40:110])


def test_layout_wrap_shrink_no_truncate_and_font_fallback():
    text='Áo sơ mi này rất thoải mái, phù hợp phối đồ nam nhiều lớp.'
    layer,info=text_layer(text,[0,0,240,100],TextStyle(size=36))
    assert layer.size==(240,100) and info['font_size']<=36 and info['lines']>1
    assert ''.join(info['wrapped'].split())==''.join(text.split())
    assert load_font('missing-font','Tiếng Việt đầy đủ dấu',18)
    with pytest.raises(UserError):text_layer(text*100,[0,0,50,20],TextStyle())
    with pytest.raises(UserError,match='glyph'):load_font('missing-font','\U0010ffff',18)


def test_overlap_and_uncertain_tracking_block():
    frame=np.zeros((240,320,3),np.uint8)
    with pytest.raises(UserError,match='chồng lấn'):compose(frame,1,[item(),item()])
    spec=item()
    spec['settings']['fixed_box']=False
    with pytest.raises(UserError,match='chưa chắc'):compose(frame,1,[spec])
    assert compose(frame,1,[spec],strict=False)[1]


def prepared(m1):
    settings,sessions,project=m1
    segment=detect_fixture(m1)
    save_reviews(sessions,project.id,[dict(id=segment.id,revision=0,translated_text='Phối đồ nam',review_status='approved')])
    save_config(sessions,project.id,segment.id,ReplacementSettings(fixed_box=True))
    with sessions.begin() as db:db.get(Project,project.id).rights_status='owned'
    return settings,sessions,project,list_segments(sessions,project.id)[0]


def test_config_separate_and_stale_approval(m1):
    settings,sessions,project,s=prepared(m1)
    items=snapshot_items(sessions,project.id)
    assert items[0]['text']=='Phối đồ nam'
    save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,translated_text='Đã sửa',review_status='approved')])
    assert list_segments(sessions,project.id)[0].review_status=='pending'
    with pytest.raises(UserError):validate_snapshot(sessions,items)
    assert snapshot_items(sessions,project.id)==[]


def test_pending_explicit_rejected_excluded(m1):
    settings,sessions,project,s=prepared(m1)
    save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,review_status='pending')])
    assert snapshot_items(sessions,project.id)==[]
    save_config(sessions,project.id,s.id,ReplacementSettings(fixed_box=True,allow_pending=True))
    assert len(snapshot_items(sessions,project.id))==1
    s=list_segments(sessions,project.id)[0]
    save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,review_status='rejected')])
    assert snapshot_items(sessions,project.id)==[]


def test_rights_idempotency_cancellation_and_failure_cleanup(m1):
    settings,sessions,project,s=prepared(m1)
    with pytest.raises(UserError):queue_render(sessions,settings,project.id,str(uuid4()))
    token=str(uuid4())
    job=queue_render(sessions,settings,project.id,token,True,True)
    assert queue_render(sessions,settings,project.id,token,True,True).id==job.id
    with pytest.raises(UserError):queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    cancel_render(sessions,job.id)
    run_render(sessions,job.id)
    assert render_history(sessions,project.id)[0].status=='CANCELLED'
    retry=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    def broken(source,output,*args):
        output.write_bytes(b'broken')
        raise UserError('fixture failure')
    run_render(sessions,retry.id,renderer=broken)
    assert render_history(sessions,project.id)[0].status=='FAILED'
    assert not list(settings.storage_root.rglob('*.partial.mp4'))
    assert (settings.storage_root/project.file_path).read_bytes()==b'unit-test-video'


def test_success_job_reopen_and_old_outputs_unchanged(m1):
    settings,sessions,project,s=prepared(m1)
    def renderer(source,output,items,settings,quality,check,progress):
        check();output.write_bytes(b'unit fake output');progress(1)
    job=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    run_render(sessions,job.id,renderer)
    stored=render_history(sessions,project.id)[0]
    assert stored.status=='COMPLETED' and stored.progress==1
    reopened=create_database(settings.database_url)
    assert render_history(reopened,project.id)[0].output_path==stored.output_path
    assert (settings.storage_root/stored.output_path).read_bytes()==b'unit fake output'
    reopened.kw['bind'].dispose()


def test_snapshot_changed_during_render_not_published(m1):
    settings,sessions,project,s=prepared(m1)
    job=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    def edit(source,output,*args):
        output.write_bytes(b'new output')
        save_reviews(sessions,project.id,[dict(id=s.id,revision=s.revision,translated_text='Đã thay đổi')])
    run_render(sessions,job.id,edit)
    assert render_history(sessions,project.id)[0].status=='FAILED'
    assert not list(settings.storage_root.rglob('*.mp4'))==[]  # Original still present.
    assert not list((settings.storage_root/f'projects/{project.id}/exports').glob('*.mp4'))


def real_settings():
    settings=load_settings()
    import shutil
    if not shutil.which(settings.ffmpeg_path) or not shutil.which(settings.ffprobe_path):pytest.skip('FFmpeg/FFprobe required')
    return settings


def packet_hashes(path,settings):
    raw=subprocess.run([settings.ffprobe_path,'-v','error','-select_streams','a:0','-show_packets','-show_data_hash','sha256','-of','json',str(path)],check=True,capture_output=True,timeout=30)
    return [p['data_hash'] for p in json.loads(raw.stdout)['packets']]


@pytest.mark.parametrize('mode',['solid','blur','inpaint','overlay'])
def test_real_ffmpeg_render_audio_and_dimensions(tmp_path,mode):
    settings=real_settings()
    source=tmp_path/'source.mp4'
    subprocess.run([settings.ffmpeg_path,'-nostdin','-y','-v','error','-f','lavfi','-i','color=c=blue:s=320x240:r=25:d=2',
                    '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(source)],check=True,timeout=30)
    original=source.read_bytes()
    output=tmp_path/'output.mp4'
    result=render_video(source,output,[item(mode)],settings)
    metadata=probe_video(output,settings.ffprobe_path,'.mp4')
    assert (metadata.width,metadata.height,metadata.audio_codec)==(320,240,'aac')
    assert abs(metadata.duration-2)<.12 and result['audio_copied']
    assert packet_hashes(source,settings)==packet_hashes(output,settings)
    assert source.read_bytes()==original
    capture=cv2.VideoCapture(str(output))
    capture.set(cv2.CAP_PROP_POS_MSEC,1000)
    ok,frame=capture.read();capture.release()
    assert ok and frame[40:110,30:270].std()>5


def test_real_vfr_normalization(tmp_path):
    settings=real_settings()
    for i,duration in enumerate([.12,.36,.2,.52]):
        Image.new('RGB',(320,240),(i*50,30,50)).save(tmp_path/f'{i}.png')
    listing=tmp_path/'frames.txt'
    listing.write_text(''.join(f"file '{i}.png'\nduration {duration}\n" for i,duration in enumerate([.12,.36,.2,.52]))+"file '3.png'\n",encoding='utf-8')
    source=tmp_path/'vfr.mp4'
    subprocess.run([settings.ffmpeg_path,'-nostdin','-y','-v','error','-f','concat','-safe','1','-i',str(listing),'-fps_mode','vfr','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
    fps,duration,_=stream_info(source,settings)
    output=tmp_path/'normalized.mp4'
    result=render_video(source,output,[],settings)
    assert abs(result['duration']-duration)<=max(.12,2/float(fps))
    assert result['normalized_vfr']


def test_fractional_fps_and_rotation(tmp_path):
    settings=real_settings()
    source=tmp_path/'source.mp4'
    rotated=tmp_path/'rotated.mp4'
    subprocess.run([settings.ffmpeg_path,'-nostdin','-y','-v','error','-f','lavfi','-i',
                    'color=c=blue:s=320x240:r=30000/1001:d=1','-c:v','libx264','-pix_fmt','yuv420p',str(source)],check=True,timeout=30)
    subprocess.run([settings.ffmpeg_path,'-nostdin','-y','-v','error','-display_rotation','90','-i',str(source),'-c','copy',str(rotated)],check=True,timeout=30)
    output=tmp_path/'output.mp4'
    result=render_video(rotated,output,[],settings)
    metadata=probe_video(output,settings.ffprobe_path,'.mp4')
    assert (metadata.width,metadata.height)==(240,320)
    assert stream_info(output,settings)[0]==Fraction(30000,1001)
    assert result['frames']==30


def test_render_blocks_ocr_and_launch_failure_releases_slot(m1,monkeypatch):
    from app.services.ocr_service import queue_job
    from app.services.render_jobs import RenderManager
    settings,sessions,project,s=prepared(m1)
    job=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    with pytest.raises(UserError,match='render'):queue_job(sessions,settings,project.id,replace_existing=True)
    manager=RenderManager(settings,sessions)
    def fail(*args,**kwargs):raise OSError('fixture')
    monkeypatch.setattr('app.services.render_jobs.subprocess.Popen',fail)
    try:
        with pytest.raises(UserError,match='worker'):manager.launch(job)
        assert render_history(sessions,project.id)[0].status=='FAILED'
        assert queue_render(sessions,settings,project.id,str(uuid4()),True,True).status=='QUEUED'
    finally:manager.close()


def test_studio_empty_and_populated_ui(m1,monkeypatch):
    import streamlit as st
    from streamlit.testing.v1 import AppTest
    settings,sessions,project=m1
    st.cache_resource.clear()

    monkeypatch.setenv('STORAGE_ROOT',str(settings.storage_root))
    monkeypatch.setenv('DATABASE_URL',settings.database_url)
    monkeypatch.setattr('app.ui.replacement_studio.manager',lambda *args:None)
    app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app/main.py')).run(timeout=30)
    app.sidebar.radio[0].set_value('Text Replacement Studio').run()
    assert not app.exception
    assert any('Chạy OCR' in x.value for x in app.info)
    segment=detect_fixture(m1)
    save_reviews(sessions,project.id,[dict(id=segment.id,revision=0,translated_text='Phối đồ nam',review_status='approved')])
    app.run()
    assert not app.exception and not app.error
    assert any(x.label=='Render MP4' for x in app.button)
    next(x for x in app.button if x.label=='Lưu cấu hình đoạn').click().run()
    assert not app.exception and not app.error
    assert any('Đã lưu cấu hình' in x.value for x in app.success)
    next(x for x in app.button if x.label=='Render MP4').click().run()
    assert any('quyền' in x.value for x in app.error)
    st.cache_resource.clear()


def test_multiple_regions_disappear_and_reappear():
    frame=np.zeros((240,320,3),np.uint8)
    first=item()
    second=item()
    second['box']=[30,140,240,70]
    third=dict(first,start=2.5,end=3.)
    assert compose(frame,1,[first,second])[0][140:210].std()>0
    assert np.array_equal(compose(frame,2,[first,second,third])[0],frame)
    assert compose(frame,2.6,[first,second,third])[0].std()>0


def test_optional_inpainting_provider_is_roi_scoped():
    class Provider:
        def apply(self,image,mask,radius):
            assert mask.max()==255 and radius==3
            return np.full_like(image,200)
    frame=np.zeros((240,320,3),np.uint8)
    output,_=compose(frame,1,[item('inpaint')],inpainting_provider=Provider())
    assert np.array_equal(output[:20],frame[:20])
    assert output[37,27,0]==200


def test_dead_render_recovery_and_foreign_keys(m1):
    from app.services.render_jobs import RenderManager
    from sqlalchemy.exc import IntegrityError
    settings,sessions,project,s=prepared(m1)
    with pytest.raises(IntegrityError):
        with sessions.begin() as db:
            db.add(ReplacementConfig(id=str(uuid4()),project_id=project.id,segment_id=str(uuid4()),settings={}))
    job=queue_render(sessions,settings,project.id,str(uuid4()),True,True)
    with sessions.begin() as db:
        row=db.get(RenderJob,job.id)
        row.status='PROCESSING';row.pid=99999999
    manager=RenderManager(settings,sessions)
    try:
        deadline=time.time()+5
        while render_history(sessions,project.id)[0].status=='PROCESSING' and time.time()<deadline:time.sleep(.1)
        assert render_history(sessions,project.id)[0].status=='FAILED'
        assert queue_render(sessions,settings,project.id,str(uuid4()),True,True).status=='QUEUED'
    finally:manager.close()
