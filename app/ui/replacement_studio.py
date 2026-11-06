import logging
from uuid import uuid4

import streamlit as st

from app.core.config import Settings
from app.database.models import Project
from app.services.ocr_repository import list_segments
from app.services.storage_service import list_projects,resolve_media
from app.services.replacement_repository import list_configs,save_config
from app.services.render_preview import preview_frame
from app.services.render_jobs import RenderManager,render_history,queue_render,cancel_render
from app.services.text_compositor import ReplacementSettings
from app.services.text_layout import TextStyle,available_fonts
from app.utils.validators import UserError

log=logging.getLogger('fashion_ai.studio')


@st.cache_resource
def manager(settings_json,_sessions):
    return RenderManager(Settings.model_validate_json(settings_json),_sessions)


@st.fragment(run_every=2)
def render_status(sessions,project_id):
    jobs=render_history(sessions,project_id)
    if jobs:
        current=jobs[0]
        labels={'QUEUED':'Đang chờ','PROCESSING':'Đang render','COMPLETED':'Hoàn tất','FAILED':'Thất bại','CANCELLED':'Đã hủy'}
        st.write(f"Trạng thái render: **{labels[current.status]}**")
        st.progress(current.progress)
        if current.error_message: st.error(current.error_message)
        if current.status in {'QUEUED','PROCESSING'} and st.button('Hủy render',key=f'cancel_render_{current.id}'):
            cancel_render(sessions,current.id)


def replacement_studio(settings,sessions):
    st.title('Text Replacement Studio')
    st.caption('Thay caption được phép sử dụng; không che watermark, tên tác giả hoặc dấu sở hữu. Audio nguồn được giữ nguyên khi codec cho phép; codec khác chuyển AAC.')
    projects=list_projects(sessions)
    if not projects:
        st.info('Hãy tải video trước.'); return
    project_id=st.selectbox('Dự án render',[p.id for p in projects],format_func=lambda key:next(p.original_filename for p in projects if p.id==key))
    project=next(p for p in projects if p.id==project_id)
    st.video(str(resolve_media(settings.storage_root,project.file_path)),width=240)
    segments=list_segments(sessions,project_id)
    configs={c.segment_id:c for c in list_configs(sessions,project_id)}
    if not segments:
        st.info('Chạy OCR và dịch ở Nhận diện & Dịch trước.'); return
    st.dataframe([{'Chữ Trung':s.source_text,'Tiếng Việt':s.translated_text,'Duyệt':s.review_status,'Bắt đầu':s.start_time,'Kết thúc':s.end_time,
                   'Bật render':configs[s.id].enabled if s.id in configs else False} for s in segments],hide_index=True)
    selected=st.selectbox('Đoạn cần cấu hình',[s.id for s in segments],format_func=lambda key:next(f'{s.start_time:.2f}s · {s.source_text}' for s in segments if s.id==key))
    segment=next(s for s in segments if s.id==selected)
    old=ReplacementSettings.model_validate(configs[selected].settings) if selected in configs else ReplacementSettings()
    box=old.box_override or segment.bounding_box
    with st.form(f'replacement_{selected}'):
        enabled=st.checkbox('Bật đoạn này khi render',value=configs[selected].enabled if selected in configs else segment.review_status=='approved')
        mode=st.selectbox('Cách xử lý nền',['solid','blur','inpaint','overlay'],index=['solid','blur','inpaint','overlay'].index(old.removal_mode),
                          format_func=lambda m:{'solid':'A · Mask màu','blur':'A · Làm mờ','inpaint':'B · OpenCV inpaint','overlay':'C · Chỉ chèn chữ'}[m])
        override=st.checkbox('Dùng khung chỉnh tay cố định',value=old.box_override is not None)
        cols=st.columns(4)
        region=[int(col.number_input(label,min_value=0 if i<2 else 1,value=int(value),step=1)) for i,(col,label,value) in enumerate(zip(cols,['X vùng gốc','Y vùng gốc','Rộng vùng gốc','Cao vùng gốc'],box))]
        text_position=st.checkbox('Vị trí chữ riêng',value=old.text_box is not None)
        target=old.text_box or box
        cols=st.columns(4)
        text_box=[int(col.number_input(label,min_value=0 if i<2 else 1,value=int(value),step=1)) for i,(col,label,value) in enumerate(zip(cols,['X chữ','Y chữ','Rộng chữ tối đa','Cao chữ tối đa'],target))]
        start=st.number_input('Hiện từ (giây)',min_value=0.,value=float(old.start_time if old.start_time is not None else segment.start_time),step=.01)
        end=st.number_input('Ẩn từ (giây)',min_value=.01,value=float(old.end_time if old.end_time is not None else segment.end_time),step=.01)
        wording=st.text_area('Tiếng Việt dùng riêng cho render',value=old.text_override if old.text_override is not None else segment.translated_text)
        wording_reviewed=st.checkbox('Tôi đã kiểm tra nội dung sửa riêng cho render',value=old.override_reviewed)
        fonts=list(available_fonts()) or ['Arial']
        font=st.selectbox('Font',fonts,index=fonts.index(old.style.font) if old.style.font in fonts else 0)
        size=st.number_input('Cỡ chữ',min_value=12,max_value=200,value=old.style.size)
        color=st.color_picker('Màu chữ',old.style.color)
        outline=st.color_picker('Màu viền',old.style.outline_color)
        stroke=st.number_input('Độ dày viền',min_value=0,max_value=10,value=old.style.outline_width)
        shadow=st.checkbox('Bóng chữ',value=old.style.shadow)
        background_on=st.checkbox('Nền chữ',value=bool(old.style.background))
        background=st.color_picker('Màu nền chữ',old.style.background or '#182235')
        alignment=st.selectbox('Căn dòng',['left','center','right'],index=['left','center','right'].index(old.style.align))
        spacing=st.number_input('Giãn dòng',min_value=0,max_value=30,value=old.style.line_spacing)
        margin=st.number_input('Lề an toàn trong khung chữ',min_value=0,max_value=100,value=old.style.safe_margin)
        padding=st.number_input('Đệm mask',min_value=0,max_value=100,value=old.padding)
        opacity=st.slider('Độ che mask',0.,1.,float(old.opacity))
        mask_color=st.color_picker('Màu mask',old.mask_color)
        radius=st.number_input('Bán kính inpaint',min_value=1,max_value=15,value=old.inpaint_radius)
        ack=st.checkbox('Tôi đã xem tracking và chấp nhận/chỉnh các vùng chưa chắc chắn',value=old.acknowledge_tracking)
        pending=st.checkbox('Chọn rõ đoạn pending sau khi tự kiểm tra (không áp dụng rejected)',value=old.allow_pending)
        saved=st.form_submit_button('Lưu cấu hình đoạn',type='primary')
    try:
        if saved:
            style=TextStyle(font=font,size=int(size),color=color,outline_color=outline,outline_width=int(stroke),shadow=shadow,
                            background=background if background_on else None,align=alignment,line_spacing=int(spacing),safe_margin=int(margin))
            config=ReplacementSettings(removal_mode=mode,box_override=region if override else None,text_box=text_box if text_position else None,
                                       start_time=start,end_time=end,text_override=wording if wording!=segment.translated_text else None,
                                       override_reviewed=wording_reviewed,padding=int(padding),opacity=opacity,mask_color=mask_color,
                                       inpaint_radius=int(radius),style=style,acknowledge_tracking=ack,allow_pending=pending)
            save_config(sessions,project_id,selected,config,enabled)
            st.success('Đã lưu cấu hình; dữ liệu OCR/bản dịch M1 không đổi.')
        timestamp=st.number_input('Mốc xem trước (giây)',min_value=0.,max_value=max(0.,project.duration-.001),value=min(segment.start_time,max(0.,project.duration-.001)),step=.1)
        if st.button('Xem frame trước / sau'):
            before,after,warnings=preview_frame(sessions,settings,project_id,timestamp)
            cols=st.columns(2)
            cols[0].image(before,caption='Trước',width=320)
            cols[1].image(after,caption='Sau · Cấu hình đã lưu',width=320)
            for warning in set(warnings): st.warning(warning)
    except UserError as exc: st.error(str(exc))
    with st.expander('Quyền sử dụng nguồn'):
        rights=st.selectbox('Trạng thái quyền',['unknown','owned','licensed','permission_granted'],index=['unknown','owned','licensed','permission_granted'].index(project.rights_status))
        if st.button('Lưu quyền sử dụng'):
            with sessions.begin() as session: session.get(Project,project_id).rights_status=rights
            st.rerun()
    rights_confirmed=st.checkbox('Tôi xác nhận có quyền sử dụng video/âm thanh và xuất bản theo giấy phép')
    regions_confirmed=st.checkbox('Tôi xác nhận các vùng chỉ là caption được phép thay, không phải watermark hay dấu sở hữu')
    quality=st.selectbox('Chất lượng xuất',['balanced','draft','high'])
    jobs=render_history(sessions,project_id)
    supervisor=manager(settings.model_dump_json(),sessions)
    if jobs and jobs[0].status=='QUEUED': supervisor.launch(jobs[0])
    token_key=f'render_token_{project_id}'
    if token_key not in st.session_state: st.session_state[token_key]=str(uuid4())
    if st.button('Render MP4',disabled=bool(jobs and jobs[0].status in {'QUEUED','PROCESSING'}),type='primary'):
        try:
            job=queue_render(sessions,settings,project_id,st.session_state[token_key],rights_confirmed,regions_confirmed,quality)
            supervisor.launch(job)
            st.session_state[token_key]=str(uuid4())
            st.rerun()
        except UserError as exc: st.error(str(exc))
    render_status(sessions,project_id)
    if st.button('Nạp lịch sử xuất'): st.rerun()
    for job in jobs[:10]:
        st.caption(f'{job.created_at:%d/%m %H:%M} · {job.status} · {job.id[:8]}')
        if job.status=='COMPLETED' and job.output_path:
            path=resolve_media(settings.storage_root,job.output_path)
            if path.is_file():
                st.video(str(path),width=240)
                with path.open('rb') as stream:
                    st.download_button('Tải MP4',stream,file_name=path.name,mime='video/mp4',key=f'download_{job.id}')
