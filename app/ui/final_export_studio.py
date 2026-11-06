import json
from datetime import timezone,timedelta
from uuid import uuid4
import streamlit as st
from sqlalchemy import select
from app.core.config import Settings
from app.database.final_schema import FinalRenderJob,ACTIVE
from app.services.storage_service import list_projects,resolve_media
from app.services.text_layout import available_fonts
from app.services.final_render_config import FinalRenderConfig,SubtitleStyle,dimensions
from app.services.final_render_service import retrieve_inputs,available_background,queue_final,final_history,cancel_final,exports,move_export,export_contract
from app.services.final_job_manager import FinalManager
from app.utils.validators import UserError


@st.cache_resource
def manager(settings_json,_sessions):return FinalManager(Settings.model_validate_json(settings_json),_sessions)


@st.fragment(run_every=2)
def render_status(sessions,project_id):
    jobs=final_history(sessions,project_id)
    if not jobs:return
    row=jobs[0];names={'QUEUED':'Đang chờ','PREPARING':'Chuẩn bị','GENERATING_SUBTITLES':'Tạo phụ đề','MUXING':'Đang render','VALIDATING':'Kiểm tra đầu ra','COMPLETED':'Hoàn tất','FAILED':'Thất bại','CANCELLED':'Đã hủy'}
    st.write(f'Xuất cuối: **{names[row.status]}**');st.progress(row.progress)
    if row.error_message:st.error(row.error_message)
    if row.status in ACTIVE and st.button('Hủy final render',key=f'cancel_final_{row.id}'):cancel_final(sessions,row.id)


def final_export_studio(settings,sessions):
    st.title('Final Export Studio')
    st.caption('Video M2 + lời Việt đã duyệt M3 + phụ đề lời nói. Không dùng caption OCR làm phụ đề, không trộn thoại gốc.')
    projects=list_projects(sessions)
    if not projects:st.info('Hãy nhập video và hoàn tất M2/M3 trước.');return
    project_id=st.selectbox('Dự án xuất cuối',[p.id for p in projects],format_func=lambda v:next(p.original_filename for p in projects if p.id==v))
    project=next(p for p in projects if p.id==project_id)
    saved_key=f'm4_config_{project_id}';nonce_key=f'm4_nonce_{project_id}'
    if saved_key not in st.session_state:st.session_state[saved_key]=FinalRenderConfig(preview_seconds=min(5.,project.duration)).model_dump(mode='json')
    if nonce_key not in st.session_state:st.session_state[nonce_key]=0
    config=FinalRenderConfig.model_validate(st.session_state[saved_key]);nonce=st.session_state[nonce_key]
    inputs=None;bg=None
    try:
        inputs=retrieve_inputs(sessions,settings,project_id,config)
        m=inputs['m2']['metadata'];a=inputs['audio_info']
        st.success('M2 video và M3 audio đã hoàn tất, đúng dự án và bản duyệt hiện tại.')
        st.dataframe([{'Nguồn':'Video M2','Thời lượng':m['duration'],'Định dạng':f"{m['width']} × {m['height']} · {m['fps']:.3f} FPS · {m['video_codec']}"},
                      {'Nguồn':'Audio M3','Thời lượng':a['duration'],'Định dạng':f"{a['sample_rate']} Hz · {a['channels']} kênh · lời Việt đã duyệt"}],hide_index=True)
        st.caption(f"Phụ đề lấy từ {len(inputs['m3']['segments'])} đoạn lời M3. Đổi bản dịch/voice/M2 config cần tạo lại artifact tương ứng.")
    except UserError as exc:st.warning(str(exc))
    try:bg=available_background(sessions,settings,project_id)
    except UserError as exc:st.warning(str(exc))
    speakers=sorted({s['speaker_id'] for s in inputs['m3']['segments']}) if inputs else []
    target=st.selectbox('Style phụ đề cho',['Tất cả',*speakers],key=f'style_target_{project_id}_{nonce}')
    st.caption('Style từng speaker ghi đè style mặc định. Chọn Tất cả để đổi mặc định; giữ các ghi đè riêng đã lưu.')
    style=config.speaker_styles.get(target,config.style)
    prefix=f'm4_{project_id}_{nonce}_{target}'
    fonts=list(available_fonts()) or ['Arial']
    with st.form(prefix):
        st.subheader('Phụ đề lời nói')
        enabled=st.checkbox('Bật phụ đề',value=config.subtitle_mode!='none')
        mode=st.selectbox('Cách hiển thị',['burn','soft'],index=1 if config.subtitle_mode=='soft' else 0,
                          format_func=lambda v:'Burn-in ASS · luôn hiện trên video' if v=='burn' else 'Soft MP4 · chuyển ASS sang mov_text')
        st.caption('Soft MP4 không giữ đầy đủ style ASS và không được mọi player hỗ trợ. ASS gốc luôn có sidecar tải riêng.')
        soft_ack=st.checkbox('Tôi chấp nhận giới hạn style/player của soft mov_text',value=config.soft_compatibility_confirmed)
        font=st.selectbox('Font phụ đề',fonts,index=fonts.index(style.font) if style.font in fonts else 0)
        size=st.number_input('Cỡ chữ (mốc ngang 1080px)',min_value=12,max_value=120,value=int(style.font_size))
        color=st.color_picker('Màu phụ đề',style.primary_color)
        outline_color=st.color_picker('Màu viền phụ đề',style.outline_color)
        outline=st.slider('Độ dày viền phụ đề',0.,8.,float(style.outline_width),step=.5)
        shadow=st.slider('Bóng phụ đề',0.,5.,float(style.shadow),step=.5)
        background=st.checkbox('Hộp nền phụ đề',value=style.background)
        background_color=st.color_picker('Màu hộp nền',style.background_color)
        alignment=st.selectbox('Căn phụ đề',list(range(1,10)),index=style.alignment-1,
                               format_func=lambda v:['Dưới trái','Dưới giữa','Dưới phải','Giữa trái','Chính giữa','Giữa phải','Trên trái','Trên giữa','Trên phải'][v-1])
        position_on=st.checkbox('Chỉnh vị trí dọc riêng',value=style.vertical_position is not None)
        position=st.slider('Vị trí dọc từ mép trên (%)',5.,95.,float((style.vertical_position or .85)*100),step=1.)
        spacing=st.number_input('Giãn dòng phụ đề',min_value=0,max_value=30,value=int(style.line_spacing))
        margin_x=st.slider('Lề ngang (%)',1.,30.,float(style.horizontal_margin*100),step=1.)
        margin_y=st.slider('Lề dọc an toàn (%)',1.,30.,float(style.vertical_margin*100),step=1.)
        max_lines=st.selectbox('Số dòng tối đa',[1,2],index=style.max_lines-1)
        readability=st.checkbox('Tôi đã xem và chấp nhận cảnh báo tốc độ đọc/câu rất ngắn',value=config.readability_confirmed)
        st.subheader('Audio và video')
        audio_choices=['voice','background'] if bg else ['voice']
        audio_mode=st.selectbox('Nguồn âm thanh',audio_choices,index=1 if bg and config.background_path else 0,
                                format_func=lambda v:'Chỉ lời Việt M3' if v=='voice' else 'Lời Việt + background đã tách riêng',disabled=not bg)
        if not bg:st.caption('Background chưa có track tách riêng hợp lệ: tùy chọn trộn bị tắt. Không lấy lại audio gốc chứa thoại Trung.')
        voice_volume=st.slider('Âm lượng lời Việt',0.,1.5,float(config.voice_volume),step=.1)
        bg_volume=st.slider('Âm lượng background đã tách',0.,1.,float(config.background_volume),step=.05,disabled=not bg)
        preset=st.selectbox('Preset video',['original','tiktok','compact'],index=['original','tiktok','compact'].index(config.preset),
                            format_func=lambda v:{'original':'Giữ nguyên M2','tiktok':'TikTok dọc 9:16','compact':'Compact · chỉ preview'}[v])
        resolution=st.selectbox('Độ phân giải TikTok',['1080x1920','720x1280'],index=0 if config.tiktok_resolution=='1080x1920' else 1)
        aspect=st.selectbox('Xử lý tỷ lệ',['fit','crop'],index=0 if config.aspect_mode=='fit' else 1,format_func=lambda v:'Fit + padding · giữ nội dung' if v=='fit' else 'Crop giữa khung · có thể mất nội dung')
        crop_ack=st.checkbox('Tôi xác nhận crop không cắt mất nội dung/attribution cần giữ',value=config.crop_confirmed)
        quality=st.selectbox('Chất lượng xuất',['fast','balanced','high'],index=['fast','balanced','high'].index(config.quality),format_func=lambda v:{'fast':'Fast Preview','balanced':'Balanced','high':'High Quality'}[v])
        fps=st.selectbox('Frame rate',['source','24','25','30','60'],index=['source','24','25','30','60'].index(config.output_fps),format_func=lambda v:'Giữ FPS M2' if v=='source' else f'{v} FPS')
        start=st.number_input('Preview từ giây',min_value=0.,max_value=max(0.,project.duration-.01),value=min(float(config.preview_start),max(0.,project.duration-.01)),step=.1)
        limit=max(.01,min(float(settings.final_preview_max_seconds),project.duration))
        seconds=st.number_input('Độ dài preview (giây)',min_value=.01,max_value=limit,value=min(float(config.preview_seconds),limit),step=.1)
        apply=st.form_submit_button('Áp dụng cấu hình xuất',type='primary')
    if apply:
        updated=SubtitleStyle(font=font,font_size=size,primary_color=color,outline_color=outline_color,outline_width=outline,shadow=shadow,background=background,background_color=background_color,
                              alignment=alignment,vertical_position=position/100 if position_on else None,line_spacing=spacing,horizontal_margin=margin_x/100,vertical_margin=margin_y/100,max_lines=max_lines)
        overrides=dict(config.speaker_styles)
        if target!='Tất cả':overrides[target]=updated
        config=FinalRenderConfig(preset=preset,tiktok_resolution=resolution,aspect_mode=aspect,crop_confirmed=crop_ack,quality=quality,output_fps=fps,
                                 subtitle_mode=mode if enabled else 'none',soft_compatibility_confirmed=soft_ack,style=updated if target=='Tất cả' else config.style,speaker_styles=overrides,
                                 readability_confirmed=readability,voice_volume=voice_volume,background_path=bg['file_path'] if bg and audio_mode=='background' else None,
                                 background_volume=bg_volume,preview_start=start,preview_seconds=seconds)
        st.session_state[saved_key]=config.model_dump(mode='json');st.rerun()
    st.caption('Lưu cấu hình trước khi tạo preview. Cỡ chữ/margins scale theo khung; tối đa2 dòng, không tự cắt nội dung. Preview là bản thu nhỏ cùng cấu hình.')
    if inputs:
        m=inputs['m2']['metadata'];w,h=dimensions(m['width'],m['height'],config)
        st.write(f'Khung đích: **{w} × {h}** · audio AAC48k mono · H.264/yuv420p · faststart')
    jobs=final_history(sessions,project_id);supervisor=manager(settings.model_dump_json(),sessions)
    if jobs and jobs[0].status=='QUEUED':supervisor.launch(jobs[0])
    active=bool(jobs and jobs[0].status in ACTIVE)
    rights=st.checkbox('Tôi xác nhận quyền dùng video/audio và giữ attribution theo giấy phép')
    reviewed=st.checkbox('Tôi đã xem preview đúng cấu hình, phụ đề và sync âm thanh')
    def launch(is_preview):
        try:
            job=queue_final(sessions,settings,project_id,str(uuid4()),config,is_preview,rights,reviewed)
            supervisor.launch(job);st.rerun()
        except UserError as exc:st.error(str(exc))
    if st.button('Tạo preview phụ đề và audio',disabled=inputs is None or active):launch(True)
    if st.button('Xuất MP4 cuối',type='primary',disabled=inputs is None or active or config.preset=='compact'):launch(False)
    render_status(sessions,project_id)
    if st.button('Nạp preview và thư viện xuất'):st.rerun()
    for job in jobs[:5]:
        stamp=job.created_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7)))
        st.caption(f"{'Preview' if job.is_preview else 'Final'} · {job.status} · {stamp:%d/%m %H:%M} VN")
        if job.is_preview and job.status=='COMPLETED' and job.output_path:
            path=resolve_media(settings.storage_root,job.output_path)
            if path.is_file():st.video(str(path),width=360)
    st.subheader('Thư viện bản xuất cuối')
    rows=exports(sessions,project_id,include_deleted=True)
    if not rows:st.info('Chưa có MP4 cuối. Tạo/xem preview trước rồi xuất.')
    for i,row in enumerate(rows):
        with st.expander(f"Bản xuất {len(rows)-i} · {row.width}×{row.height} · {row.duration:.2f}s"+(' · Trong thùng rác' if row.deleted_at else '')):
            with sessions() as db:job=db.get(FinalRenderJob,row.render_job_id)
            stamp=row.created_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7)))
            st.caption(f'{row.file_size/1024**2:.2f} MB · {stamp:%d/%m/%Y %H:%M} VN · preset {job.render_config["preset"]} · phụ đề {job.render_config["subtitle_mode"]}')
            if not row.deleted_at:
                try:
                    contract=export_contract(sessions,settings,project_id,row.id);path=resolve_media(settings.storage_root,contract['final_mp4_path'])
                    st.video(str(path),width=360)
                    with path.open('rb') as stream:st.download_button('Tải MP4 cuối',stream,file_name=row.filename,mime='video/mp4',key=f'dl_final_{row.id}')
                    ass=path.parent/'subtitles.ass'
                    if ass.is_file():st.download_button('Tải ASS gốc',ass.read_bytes(),file_name=row.filename.removesuffix('.mp4')+'.ass',key=f'dl_ass_{row.id}')
                    with st.expander('Metadata, sync và cấu hình xuất'):st.json(contract)
                except UserError as exc:st.error(str(exc))
            if st.button('Dùng lại cấu hình để render mới',key=f'reuse_{row.id}'):
                st.session_state[saved_key]=job.render_config;st.session_state[nonce_key]+=1;st.rerun()
            confirmation=st.checkbox('Xác nhận '+('khôi phục' if row.deleted_at else 'chuyển MP4 này vào thùng rác, giữ nguyên M2/M3/bản gốc'),key=f'trash_ack_{row.id}')
            if st.button('Khôi phục MP4' if row.deleted_at else 'Chuyển MP4 vào thùng rác',key=f'trash_{row.id}',disabled=not confirmation):
                try:move_export(sessions,settings,project_id,row.id,True,restore=bool(row.deleted_at));st.rerun()
                except UserError as exc:st.error(str(exc))
