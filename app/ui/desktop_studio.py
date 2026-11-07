import json
import os
from pathlib import Path
import streamlit as st
from sqlalchemy import update
from app.database.desktop_schema import ModelDownloadJob
from app.desktop.model_manager import inventory,queue_download,history,recover_downloads
from app.version import __version__
from app.utils.validators import UserError


@st.fragment(run_every=2)
def download_status(sessions):
    recover_downloads(sessions)
    for row in history(sessions)[:5]:
        st.write(f'{row.group}: **{row.status}**');st.progress(row.progress)
        if row.error:st.error(row.error)
        if row.status in {'QUEUED','RUNNING'} and st.button('Hủy tải model',key='cancel_model_'+row.id):
            with sessions.begin() as db:db.execute(update(ModelDownloadJob).where(ModelDownloadJob.id==row.id).values(cancel_requested=True))


def desktop_studio(settings,sessions):
    st.title('Desktop & Models');st.caption('v'+__version__+' · CPU local · tải model chỉ khi bạn yêu cầu')
    data=Path(os.environ.get('FASHION_AI_DATA_DIR',str(settings.storage_root.parent)))
    root=Path(os.environ.get('FASHION_AI_MODELS_DIR',str(settings.storage_root/'models')))
    st.write('Dữ liệu:',str(data));st.write('Model ngoài executable:',str(root));st.write('Log:',str(data/'logs'))
    status=data/'desktop-status.json'
    if status.is_file():
        try:st.write('Trạng thái launcher:',json.loads(status.read_text()).get('state','unknown'))
        except (OSError,ValueError):st.warning('Không đọc được trạng thái launcher.')
    st.info('Khuyến nghị CPU/16 GB RAM, giữ nhiều GB trống cho runtime/model và thêm dung lượng video. Không bundle model vào executable. Model ASR/dịch vẫn cần duyệt; không bảo đảm mọi giọng/nội dung.')
    verify=st.button('Kiểm tra SHA-256 các model đã cài')
    with st.spinner('Kiểm tra model local...'):rows=inventory(root,verify)
    st.dataframe(rows,hide_index=True)
    st.caption('installed (hash not checked) chỉ xác nhận có file. Nhấn kiểm tra SHA để xác minh nội dung theo catalog đã pin; catalog hash không phải chữ ký upstream.')
    group=st.selectbox('Nhóm model CPU',['ocr','translation','asr','tts'])
    ack=st.checkbox('Tôi chọn tải model qua mạng và đã đọc nguồn/giấy phép hiển thị')
    if st.button('Tải nhóm model đã chọn',disabled=not ack):
        try:queue_download(sessions,root,group);st.rerun()
        except UserError as exc:st.error(str(exc))
    download_status(sessions)
    st.caption('Không tự tải khi startup. Model hỏng không bị tự ghi đè. FunASR tùy chọn cài thủ công; CPU Whisper base/VAIS1000 là đường đã kiểm chứng.')
    st.subheader('Nâng cấp / sao lưu / dọn tạm')
    st.write('Dừng ứng dụng rồi dùng launcher --backup tới thư mục mới ngoài data. --restore chỉ vào data mới trống. --clean-temp --confirm chỉ xóa file .part/.tmp ở storage/temp quá24h; giữ nguyên video/model/export. Xem WINDOWS_INSTALLATION.md.')
