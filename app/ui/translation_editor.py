"""Human edits and review status; provider details never parsed in the UI."""
import hashlib

import streamlit as st

from app.services.ocr_repository import list_segments, save_reviews
from app.core.config import Settings
from app.database.review_schema import ReviewState
from app.services.translation_review_service import effective_state, evaluate, review_batch

REVIEWS = {"pending": "Chờ duyệt", "approved": "Đã duyệt", "rejected": "Loại bỏ"}


def translation_editor(sessions, project_id, busy=False, settings=None):
    settings = settings or Settings()
    segments = list_segments(sessions, project_id)
    if not segments:
        st.info("Chưa có đoạn chữ Trung để dịch. Hãy chạy OCR; chữ chỉ gồm tiếng Anh hoặc số sẽ không được đưa vào danh sách dịch.")
        return []
    st.warning("Bản dịch cần được kiểm tra trước khi xuất")
    with sessions() as session:
        states = {s.id: session.get(ReviewState,s.id) for s in segments}
    effective = {s.id: effective_state(s,states[s.id]) for s in segments}
    cols = st.columns(5)
    for col,label,value in zip(cols,["Tổng đoạn","Tự động duyệt","Cần kiểm tra","Duyệt thủ công","Loại bỏ"],
                               [len(segments),sum(v=='AUTO_APPROVED' for v in effective.values()),sum(v in {'PENDING','NEEDS_REVIEW'} for v in effective.values()),sum(v=='MANUALLY_APPROVED' for v in effective.values()),sum(v=='REJECTED' for v in effective.values())]):
        col.metric(label,value)
    mode = st.selectbox("Chế độ duyệt",["Thủ công","Smart Auto Review (Khuyên dùng)","Auto Approve All"], key=f"mode_{project_id}")
    st.caption("Điểm duyệt chỉ là heuristic, không phải xác suất bản dịch đúng. Smart chỉ tự duyệt bản khớp thuật ngữ có đối chiếu; câu neural chưa xác định nghĩa vẫn cần kiểm tra.")
    if mode == "Auto Approve All":
        st.warning("Duyệt tất cả bỏ qua kiểm tra chất lượng. Không áp dụng cho đoạn bị loại hoặc bản dịch trống.")
    only_pending = st.checkbox("Chỉ hiện đoạn cần kiểm tra", key=f"pending_{project_id}")
    status_filter = st.selectbox("Lọc trạng thái",["Tất cả",*REVIEWS.values()],key=f"filter_{project_id}")
    segments = [s for s in segments if (not only_pending or effective[s.id] in {'PENDING','NEEDS_REVIEW'})
                and (status_filter == "Tất cả" or REVIEWS[s.review_status] == status_filter)]
    if not segments:
        st.info("Không có đoạn phù hợp bộ lọc.")
        return []
    st.caption("Thời gian là ước lượng theo nhịp lấy mẫu. Khung chữ dùng tọa độ pixel của video gốc đã xoay đúng chiều. Duyệt từng đoạn sau khi kiểm tra ý nghĩa và thông tin sản phẩm.")
    pages = max(1, (len(segments) + 99) // 100)
    page = int(st.number_input("Trang kết quả (100 đoạn/trang)", min_value=1, max_value=pages, value=1, key=f"segment_page_{project_id}"))
    segments = segments[(page - 1) * 100:page * 100]
    rows = [{"id": s.id, "revision": s.revision, "selected": False, "start_time": s.start_time,
             "end_time": s.end_time, "source_text": s.source_text, "translated_text": s.translated_text,
             "confidence": round(s.confidence, 4), "review": REVIEWS[s.review_status],
             "x": s.bounding_box[0], "y": s.bounding_box[1], "w": s.bounding_box[2], "h": s.bounding_box[3],
             "provider": s.translation_provider,
             "review_score": evaluate(s.source_text,s.translated_text,s.confidence,s.translation_error,settings).score,
             "review_reason": "; ".join(evaluate(s.source_text,s.translated_text,s.confidence,s.translation_error,settings).reasons)} for s in segments]
    fingerprint = hashlib.sha256(str([(s.id, s.revision) for s in segments]).encode()).hexdigest()[:12]
    with st.form(f"review_form_{project_id}_{page}_{fingerprint}"):
        edited = st.data_editor(rows, key=f"review_{project_id}_{fingerprint}", hide_index=True,
                               disabled=["confidence", "provider","review_score","review_reason"] if not busy else True,
                               column_order=["selected", "start_time", "end_time", "source_text", "translated_text", "confidence", "review", "review_score","review_reason", "x", "y", "w", "h", "provider"],
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
                                   "review_score": st.column_config.NumberColumn("Điểm duyệt"),
                                   "review_reason": st.column_config.TextColumn("Lý do kiểm tra"),
                               }, width="stretch")
        saved = st.form_submit_button("Lưu chỉnh sửa", disabled=busy, type="primary")
        translated = st.form_submit_button("Dịch các đoạn đã chọn", disabled=busy)
        confirmed = st.checkbox("Tôi xác nhận duyệt hàng loạt và hiểu việc bỏ qua kiểm tra chất lượng.")
        smart = st.form_submit_button("Tự động duyệt đoạn đạt chuẩn",disabled=busy or mode!='Smart Auto Review (Khuyên dùng)')
        approve_all = st.form_submit_button("Duyệt tất cả",disabled=busy or mode!='Auto Approve All')
        approve_selected = st.form_submit_button("Duyệt các đoạn đã chọn",disabled=busy)
        revert = st.form_submit_button("Chuyển về chờ duyệt",disabled=busy)
    if saved or translated or smart or approve_all or approve_selected or revert:
        if (approve_all or approve_selected) and not confirmed:
            from app.utils.validators import UserError
            raise UserError("Cần xác nhận trước khi duyệt hàng loạt.")
        edits = [{"id": row["id"], "revision": row["revision"], "source_text": row["source_text"],
                  "translated_text": row["translated_text"], "start_time": row["start_time"], "end_time": row["end_time"],
                  "review_status": next(key for key, value in REVIEWS.items() if value == row["review"]),
                  "bounding_box": [row["x"], row["y"], row["w"], row["h"]]} for row in edited]
        save_reviews(sessions, project_id, edits)
        if smart or approve_all or approve_selected or revert:
            ids = [r['id'] for r in edited if smart or approve_all or r['selected']]
            fresh = {s.id:s for s in list_segments(sessions,project_id)}
            bar=st.progress(0.0)
            counts=review_batch(sessions,project_id,[{'id':key,'revision':fresh[key].revision} for key in ids],
                               'smart' if smart else 'approve_all' if approve_all else 'approve_selected' if approve_selected else 'revert',settings,confirmed,
                               progress=lambda done,total:bar.progress(done/max(1,total)))
            st.session_state[f"review_notice_{project_id}"]=f"Đã đổi {counts['changed']}, giữ nguyên {counts['unchanged']}, cần tải lại {counts['failed']} đoạn."
            st.rerun()
        if translated:
            ids = [row["id"] for row in edited if row["selected"]]
            if not ids:
                st.warning("Hãy chọn ít nhất một đoạn chưa duyệt để dịch.")
            return ids
        st.success("Đã lưu bản dịch và trạng thái duyệt.")
        st.rerun()
    return []
