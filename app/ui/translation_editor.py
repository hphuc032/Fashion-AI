"""Human edits and review status; provider details never parsed in the UI."""
import hashlib

import streamlit as st

from app.services.ocr_repository import list_segments, save_reviews

REVIEWS = {"pending": "Chờ duyệt", "approved": "Đã duyệt", "rejected": "Loại bỏ"}


def translation_editor(sessions, project_id, busy=False):
    segments = list_segments(sessions, project_id)
    if not segments:
        st.info("Chưa có đoạn chữ Trung để dịch. Hãy chạy OCR; chữ chỉ gồm tiếng Anh hoặc số sẽ không được đưa vào danh sách dịch.")
        return []
    st.warning("Bản dịch cần được kiểm tra trước khi xuất")
    st.caption("Thời gian là ước lượng theo nhịp lấy mẫu. Khung chữ dùng tọa độ pixel của video gốc đã xoay đúng chiều. Duyệt từng đoạn sau khi kiểm tra ý nghĩa và thông tin sản phẩm.")
    pages = max(1, (len(segments) + 99) // 100)
    page = int(st.number_input("Trang kết quả (100 đoạn/trang)", min_value=1, max_value=pages, value=1, key=f"segment_page_{project_id}"))
    segments = segments[(page - 1) * 100:page * 100]
    rows = [{"id": s.id, "revision": s.revision, "selected": False, "start_time": s.start_time,
             "end_time": s.end_time, "source_text": s.source_text, "translated_text": s.translated_text,
             "confidence": round(s.confidence, 4), "review": REVIEWS[s.review_status],
             "x": s.bounding_box[0], "y": s.bounding_box[1], "w": s.bounding_box[2], "h": s.bounding_box[3],
             "provider": s.translation_provider} for s in segments]
    fingerprint = hashlib.sha256(str([(s.id, s.revision) for s in segments]).encode()).hexdigest()[:12]
    with st.form(f"review_form_{project_id}_{page}_{fingerprint}"):
        edited = st.data_editor(rows, key=f"review_{project_id}_{fingerprint}", hide_index=True,
                               disabled=["confidence", "provider"] if not busy else True,
                               column_order=["selected", "start_time", "end_time", "source_text", "translated_text", "confidence", "review", "x", "y", "w", "h", "provider"],
                               column_config={
                                   "selected": st.column_config.CheckboxColumn("Chọn dịch"),
                                   "start_time": st.column_config.NumberColumn("Bắt đầu (s)", min_value=0, format="%.2f"),
                                   "end_time": st.column_config.NumberColumn("Kết thúc (s)", min_value=0, format="%.2f"),
                                   "source_text": st.column_config.TextColumn("Chữ Trung", max_chars=1000),
                                   "translated_text": st.column_config.TextColumn("Tiếng Việt", max_chars=2000),
                                   "confidence": st.column_config.NumberColumn("Độ tin cậy", format="%.3f"),
                                   "review": st.column_config.SelectboxColumn("Duyệt", options=list(REVIEWS.values()), required=True),
                                   "x": st.column_config.NumberColumn("X", min_value=0, step=1),
                                   "y": st.column_config.NumberColumn("Y", min_value=0, step=1),
                                   "w": st.column_config.NumberColumn("Rộng", min_value=1, step=1),
                                   "h": st.column_config.NumberColumn("Cao", min_value=1, step=1),
                                   "provider": st.column_config.TextColumn("Nguồn bản dịch"),
                               }, width="stretch")
        saved = st.form_submit_button("Lưu chỉnh sửa", disabled=busy, type="primary")
        translated = st.form_submit_button("Dịch các đoạn đã chọn", disabled=busy)
    if saved or translated:
        edits = [{"id": row["id"], "revision": row["revision"], "source_text": row["source_text"],
                  "translated_text": row["translated_text"], "start_time": row["start_time"], "end_time": row["end_time"],
                  "review_status": next(key for key, value in REVIEWS.items() if value == row["review"]),
                  "bounding_box": [row["x"], row["y"], row["w"], row["h"]]} for row in edited]
        save_reviews(sessions, project_id, edits)
        if translated:
            ids = [row["id"] for row in edited if row["selected"]]
            if not ids:
                st.warning("Hãy chọn ít nhất một đoạn chưa duyệt để dịch.")
            return ids
        st.success("Đã lưu bản dịch và trạng thái duyệt.")
        st.rerun()
    return []
