from datetime import timezone, timedelta

import streamlit as st

from app.core.config import Settings
from app.database.models import Project
from app.services.storage_service import resolve_media

RIGHTS = {"unknown": "Chưa xác định", "owned": "Tôi sở hữu",
          "licensed": "Có giấy phép", "permission_granted": "Được tác giả cho phép"}


def project_preview(project: Project, settings: Settings) -> None:
    st.subheader(project.original_filename)
    st.success("Đã nhập · Bản gốc được giữ nguyên")
    left, right = st.columns([1, 1])
    with left:
        path = resolve_media(settings.storage_root, project.file_path)
        if path.is_file():
            if path.suffix.lower() == ".mp4" and project.video_codec == "h264" and project.audio_codec in (None, "aac", "mp3"):
                st.video(str(path), format="video/mp4", width=280)
            else:
                st.warning("Trình duyệt có thể không phát được codec/container này. Hãy mở bản gốc bằng trình phát trên máy. M0 chưa chuyển mã.")
                st.video(str(path), format="video/quicktime" if path.suffix == ".mov" else "video/x-matroska" if path.suffix == ".mkv" else "video/mp4", width=280)
            st.caption("Nếu video không phát, hãy kiểm tra khả năng hỗ trợ codec của trình duyệt.")
        else:
            st.error("Không tìm thấy bản gốc trong kho lưu trữ.")
    with right:
        timestamp = project.created_at.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=7)))
        st.table({"Thông tin": ["Dung lượng", "Thời lượng", "Kích thước", "FPS", "Codec video", "Codec audio", "Tỷ lệ", "Tải lên (VN)", "Quyền sử dụng"],
                  "Giá trị": [f"{project.file_size / 1024**2:.2f} MB", f"{project.duration:.2f} giây",
                              f"{project.width} × {project.height}", f"{project.fps:.3f}",
                              project.video_codec, project.audio_codec or "Không có âm thanh",
                              project.aspect_ratio, timestamp.strftime("%d/%m/%Y %H:%M"), RIGHTS[project.rights_status]]})
    with st.expander("Thông tin nguồn"):
        st.text(f"Mã dự án: {project.id}")
        st.text(f"Nguồn: {project.source_url or 'Chưa cung cấp'}")
        st.text(f"Tác giả: {project.creator_name or 'Chưa cung cấp'}")
        st.text(f"Ghi chú: {project.rights_notes or 'Chưa cung cấp'}")
        st.caption("Việc có tệp video không đồng nghĩa với quyền đăng lại. M0 chỉ lưu thông tin quyền, chưa có chức năng xuất.")
