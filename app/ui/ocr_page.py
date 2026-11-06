import logging
from dataclasses import replace

import streamlit as st

from app.core.config import Settings
from app.services.frame_extractor import extract_frames
from app.services.job_manager import JobManager
from app.services.ocr_repository import list_detections, project_source
from app.services.ocr_service import ACTIVE, latest_job, queue_job, request_cancel
from app.services.storage_service import list_projects
from app.ui.translation_editor import translation_editor
from app.utils.validators import UserError

log = logging.getLogger("fashion_ai.ocr_ui")
STATES = {"NOT_STARTED": "Chưa chạy", "QUEUED": "Đang chờ", "PROCESSING": "Đang xử lý",
          "COMPLETED": "Hoàn tất", "FAILED": "Thất bại", "CANCELLED": "Đã hủy"}


@st.cache_resource
def manager(settings_json, _sessions):
    return JobManager(Settings.model_validate_json(settings_json), _sessions)


@st.fragment(run_every=2)
def job_status(sessions, project_id):
    job = latest_job(sessions, project_id)
    state = job.status if job else "NOT_STARTED"
    st.write(f"Trạng thái: **{STATES[state]}**")
    if job:
        st.progress(job.completed_frames / max(1, job.total_frames),
                    text=f"Đã xử lý {job.completed_frames}/{job.total_frames} {'khung hình' if job.kind == 'ocr' else 'đoạn'}")
        if job.error_message:
            st.error(job.error_message)
        if job.warning_message:
            st.warning(job.warning_message)
        if job.status in ACTIVE and st.button("Hủy tác vụ", key=f"cancel_{job.id}"):
            request_cancel(sessions, job.id)
            st.info("Đã gửi yêu cầu hủy.")
        if job.status not in ACTIVE:
            st.caption("Nhấn ‘Tải lại kết quả’ sau khi tác vụ hoàn tất để nạp bảng mới.")


def diagnostic_preview(sessions, settings, project_id):
    detections = list_detections(sessions, project_id)
    if not detections:
        return
    times = sorted({d.timestamp for d in detections})
    timestamp = st.selectbox("Khung hình cần kiểm tra (giây)", times, format_func=lambda t: f"{t:.2f} s")
    selected = [d for d in detections if d.timestamp == timestamp]
    project, path = project_source(sessions, project_id, settings)
    sample = next(extract_frames(path, project_id, project.duration, settings, timestamps=[timestamp]))
    from PIL import Image, ImageDraw
    with Image.open(sample.path) as image:
        image = image.convert("RGB")
        draw = ImageDraw.Draw(image)
        scale_x, scale_y = image.width / sample.original_width, image.height / sample.original_height
        for index, detection in enumerate(selected, 1):
            x, y, w, h = detection.bounding_box
            draw.rectangle((x * scale_x, y * scale_y, (x + w) * scale_x, (y + h) * scale_y), outline="#38bdf8", width=3)
            draw.text((x * scale_x, max(0, y * scale_y - 16)), str(index), fill="#ffff00")
        st.image(image, caption=f"{timestamp:.2f} s · Tọa độ gốc {sample.original_width}×{sample.original_height} · Ảnh chỉ phục vụ kiểm tra", width=420)
    st.dataframe([{"Vùng": i, "Chữ nhận diện": d.source_text, "Tin cậy": round(d.confidence, 4),
                   "Khung gốc [x,y,w,h]": str(d.bounding_box), "Đưa vào đoạn dịch": bool(d.segment_id)}
                  for i, d in enumerate(selected, 1)], hide_index=True)


def ocr_page(settings, sessions):
    st.title("Nhận diện & Dịch")
    projects = list_projects(sessions)
    if not projects:
        st.info("Hãy tải một video ở mục Tải video trước khi nhận diện chữ.")
        return
    by_id = {p.id: p for p in projects}
    project_id = st.selectbox("Chọn video để OCR", list(by_id), format_func=lambda key: f"{by_id[key].original_filename} · {key[:8]}")
    st.caption("Chỉ nhận diện chữ trên hình. Bản gốc được giữ nguyên; chưa xóa chữ, lồng tiếng hoặc xuất video.")
    interval = st.number_input("Khoảng lấy mẫu (giây)", min_value=0.1, max_value=60.0,
                               value=float(settings.ocr_sample_interval_seconds), step=0.1)
    provider = st.selectbox("Cách dịch", ["manual", "argos"], index=1 if settings.translation_provider == "argos" else 0,
                            format_func=lambda value: "Nhập thủ công · Không dùng mô hình dịch" if value == "manual" else "Argos offline · Trung → Anh → Việt")
    st.caption("Argos dùng mô hình cài riêng, không gọi API. Cụm thời trang khớp chính xác dùng từ điển đã biên soạn; phần còn lại dịch bằng mô hình. Kết quả dịch trung gian cần kiểm tra lại tên thương hiệu, số liệu và ý nghĩa.")
    options = Settings.model_validate({**settings.model_dump(), "ocr_sample_interval_seconds": interval, "translation_provider": provider})
    job = latest_job(sessions, project_id)
    busy = bool(job and job.status in ACTIVE)
    supervisor = manager(settings.model_dump_json(), sessions)
    if job and job.status == "QUEUED":
        supervisor.launch(job)
    replacement = st.checkbox("Tôi hiểu OCR lại sẽ thay kết quả và các chỉnh sửa cũ khi hoàn tất thành công.", value=False)
    if st.button("Chạy OCR", type="primary", disabled=busy):
        try:
            job = queue_job(sessions, options, project_id, replace_existing=replacement)
            supervisor.launch(job)
            st.rerun()
        except UserError as exc:
            st.error(str(exc))
    job_status(sessions, project_id)
    if st.button("Tải lại kết quả"):
        st.rerun()
    try:
        if st.session_state.get(f"review_notice_{project_id}"):
            st.success(st.session_state.pop(f"review_notice_{project_id}"))
        selected = translation_editor(sessions, project_id, busy=busy, settings=options)
        if selected:
            job = queue_job(sessions, options, project_id, kind="translate", selected_ids=selected)
            supervisor.launch(job)
            st.rerun()
        with st.expander("Kiểm tra khung chữ OCR", expanded=False):
            diagnostic_preview(sessions, options, project_id)
    except UserError as exc:
        st.error(str(exc))
    except Exception as exc:
        log.error("review_ui_failed type=%s", type(exc).__name__)
        st.error("Không mở được kết quả OCR. Kiểm tra thư viện M1, mô hình và video gốc.")
