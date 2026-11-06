import logging
from uuid import uuid4

import streamlit as st
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.services.storage_service import import_video, list_projects
from app.ui.components import RIGHTS, project_preview
from app.utils.validators import UserError, validate_source
from app.version import __version__

log = logging.getLogger("fashion_ai.ui")


def dashboard(settings: Settings, sessions: sessionmaker) -> None:
    st.title(settings.app_name)
    st.caption("Không gian video của bạn · Nhập video, OCR và bản dịch")
    page = st.sidebar.radio("Điều hướng", ["Tổng quan", "Tải video", "Thư viện", "Nhận diện & Dịch", "Text Replacement Studio", "AI Dubbing Studio", "Final Export Studio"])
    st.sidebar.caption(f"v{__version__} • Chạy cục bộ • Cloud chỉ khi chủ động chọn")
    if page == 'Final Export Studio':
        from app.ui.final_export_studio import final_export_studio
        final_export_studio(settings,sessions)
        return
    if page == 'AI Dubbing Studio':
        from app.ui.dubbing_studio import dubbing_studio
        dubbing_studio(settings,sessions)
        return
    if page == "Text Replacement Studio":
        from app.ui.replacement_studio import replacement_studio
        replacement_studio(settings,sessions)
        return
    if page == "Nhận diện & Dịch":
        from app.ui.ocr_page import ocr_page
        ocr_page(settings, sessions)
        return
    projects = list_projects(sessions)
    if page == "Tổng quan":
        a, b, c = st.columns(3)
        a.metric("Video đã nhập", len(projects))
        b.metric("Dung lượng đã nhập", f"{sum(p.file_size for p in projects) / 1024**2:.1f} MB")
        c.metric("Thời lượng", f"{sum(p.duration for p in projects):.0f} giây")
        st.info("Tải video, xem bản gốc và nhận diện chữ Trung ở mục Nhận diện & Dịch. Mọi bản dịch cần được kiểm tra và duyệt.")
    if page == "Tải video":
        st.subheader("Nhập video mới")
        st.caption(f"MP4 / MOV / MKV · Tối đa {settings.max_upload_size_mb} MB và {settings.max_video_seconds:g} giây")
        if "upload_token" not in st.session_state:
            st.session_state.upload_token = str(uuid4())
        with st.form("upload_form", clear_on_submit=True):
            video = st.file_uploader("Chọn video trên máy", type=["mp4", "mov", "mkv"])
            source_url = st.text_input("URL nguồn (không bắt buộc)")
            creator = st.text_input("Tên tác giả (không bắt buộc)", max_chars=255)
            rights = st.selectbox("Quyền sử dụng", list(RIGHTS), format_func=RIGHTS.get)
            notes = st.text_area("Ghi chú giấy phép / sự cho phép", max_chars=4000)
            submitted = st.form_submit_button("Lưu video", type="primary")
        if submitted:
            if video is None:
                st.warning("Hãy chọn một video trước khi lưu.")
            else:
                try:
                    if video.size > settings.max_bytes:
                        raise UserError(f"Video vượt giới hạn {settings.max_upload_size_mb} MB.")
                    source = validate_source(source_url=source_url.strip() or None,
                                             creator_name=creator.strip() or None,
                                             rights_status=rights, rights_notes=notes.strip() or None)
                    with st.spinner("Đang lưu và kiểm tra video…"):
                        project = import_video(video, video.name, source, settings, sessions,
                                               st.session_state.upload_token)
                    st.session_state.selected_project = project.id
                    st.session_state.upload_token = str(uuid4())
                    st.success("Đã lưu video và thông tin dự án.")
                    projects = list_projects(sessions)
                except UserError as exc:
                    log.warning("validation_failed")
                    st.error(str(exc))
                except Exception as exc:
                    log.error("upload_unexpected type=%s", type(exc).__name__)
                    st.error("Không thể lưu dự án. Hãy kiểm tra dung lượng đĩa, quyền ghi và cấu hình SQLite rồi thử lại.")
    st.subheader("Video gần đây" if page != "Thư viện" else "Thư viện video")
    if not projects:
        st.info("Chưa có video. Chọn ‘Tải video’ ở thanh bên để bắt đầu.")
        return
    by_id = {p.id: p for p in projects}
    ids = list(by_id)
    selected = st.session_state.get("selected_project", ids[0])
    chosen = st.selectbox("Chọn dự án", ids, index=ids.index(selected) if selected in ids else 0,
                          format_func=lambda key: f"{by_id[key].original_filename} · {key[:8]}")
    st.session_state.selected_project = chosen
    project_preview(by_id[chosen], settings)
