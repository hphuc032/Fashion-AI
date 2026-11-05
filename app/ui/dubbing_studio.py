import json
from uuid import uuid4
import pandas as pd
import streamlit as st
from app.core.config import Settings
from app.providers.tts.base import VoiceSettings
from app.services.storage_service import list_projects,resolve_media
from app.services.speech_repository import list_speech,save_speech,save_speaker
from app.services.dub_jobs import DubManager,queue_dub,history,cancel
from app.database.speech_schema import ACTIVE,DubbedAudioSegment
from app.services.dubbing_contract import approved_dub
from app.utils.validators import UserError
from sqlalchemy import select


@st.cache_resource
def manager(settings_json,_sessions):return DubManager(Settings.model_validate_json(settings_json),_sessions)


@st.fragment(run_every=2)
def status(sessions,project_id):
    jobs=history(sessions,project_id)
    if not jobs:return
    job=jobs[0]
    labels={'QUEUED':'Đang chờ','EXTRACTING_AUDIO':'Trích audio','TRANSCRIBING':'Nhận diện lời','TRANSLATING':'Dịch lời','GENERATING_TTS':'Tạo giọng Việt',
            'SYNCHRONIZING':'Căn thời lượng','ASSEMBLING':'Ghép timeline','COMPLETED':'Hoàn tất','FAILED':'Thất bại','CANCELLED':'Đã hủy'}
    st.write(f'Tác vụ audio: **{labels[job.status]}**');st.progress(job.progress)
    if job.error_message:st.error(job.error_message)
    if job.status in ACTIVE and st.button('Hủy tác vụ audio',key=f'cancel_dub_{job.id}'):cancel(sessions,job.id)


def dubbing_studio(settings,sessions):
    st.title('AI Dubbing Studio')
    st.caption('Audio lời Việt riêng cho bước xuất sau. Bản dịch cần kiểm tra trước khi duyệt; không sao chép giọng người gốc.')
    projects=list_projects(sessions)
    if not projects:st.info('Hãy tải video trước.');return
    key=st.selectbox('Dự án lồng tiếng',[p.id for p in projects],format_func=lambda v:next(p.original_filename for p in projects if p.id==v))
    project=next(p for p in projects if p.id==key)
    st.video(str(resolve_media(settings.storage_root,project.file_path)),width=240)
    st.caption('Bản gốc giữ nguyên. Audio gốc được trích khi chạy ASR; video im lặng sẽ được báo rõ.')
    options=settings.model_copy()
    options.asr_provider=st.selectbox('Nhận diện local',['funasr','whisper'],index=['funasr','whisper'].index(settings.asr_provider) if settings.asr_provider in ['funasr','whisper'] else 0)
    st.caption('FunASR cần model local timestamp-capable; Whisper dùng model đã cài. Không tải model khi mở trang.')
    options.asr_language=st.selectbox('Ngôn ngữ ASR',['zh','en'],index=0 if settings.asr_language=='zh' else 1,help='FunASR nhận ngôn ngữ theo model; Whisper dùng lựa chọn này.')
    options.asr_chunk_seconds=float(st.number_input('Độ dài chunk audio (giây)',min_value=5.,max_value=120.,value=float(settings.asr_chunk_seconds)))
    replace=st.checkbox('Xác nhận thay transcript khi ASR mới thành công')
    supervisor=manager(settings.model_dump_json(),sessions)
    jobs=history(sessions,key)
    if jobs and jobs[0].status=='QUEUED':supervisor.launch(jobs[0])
    def launch(kind,**kwargs):
        try:
            job=queue_dub(sessions,options,key,str(uuid4()),kind,**kwargs)
            supervisor.launch(job);st.rerun()
        except UserError as exc:st.error(str(exc))
    if st.button('Chạy ASR',disabled=bool(jobs and jobs[0].status in ACTIVE)):launch('asr',replace_existing=replace)
    status(sessions,key)
    if st.button('Nạp transcript và lịch sử'):st.rerun()
    rows=list_speech(sessions,key)
    selected=[]
    if rows:
        page=st.number_input('Trang lời (100 đoạn/trang)',min_value=1,max_value=max(1,(len(rows)+99)//100),value=1)
        visible=rows[(page-1)*100:page*100]
        frame=pd.DataFrame([dict(Chọn=False,id=s.id,revision=s.revision,Từ=s.start_time,Đến=s.end_time,Trung=s.original_text,Việt=s.translated_text,Speaker=s.speaker_id,Duyệt=s.review_status) for s in visible])
        edited=st.data_editor(frame,hide_index=True,disabled=['id','revision'],column_config={'id':None,'revision':None,'Duyệt':st.column_config.SelectboxColumn(options=['pending','approved','rejected'])},key=f'speech_editor_{key}_{page}',width='stretch')
        selected=edited.loc[edited['Chọn'],'id'].tolist()
        if st.button('Lưu sửa và duyệt lời',type='primary'):
            try:
                save_speech(sessions,key,[dict(id=r['id'],revision=r['revision'],start_time=r['Từ'],end_time=r['Đến'],original_text=r['Trung'],translated_text=r['Việt'],speaker_id=r['Speaker'],review_status=r['Duyệt']) for r in edited.to_dict('records')]);st.rerun()
            except (UserError,ValueError,TypeError) as exc:st.error(str(exc) if isinstance(exc,UserError) else 'Nội dung/timing không hợp lệ.')
        options.translation_provider=st.selectbox('Dịch lời',['manual','argos'],index=0 if settings.translation_provider=='manual' else 1)
        if st.button('Dịch lại các lời đã chọn'):launch('translate',selected_ids=selected)
        warnings=[f'{s.start_time:.2f}s: '+', '.join(s.warnings) for s in visible if s.warnings]
        if warnings:
            with st.expander('Cảnh báo bản dịch — cần người kiểm tra'):st.write('\n\n'.join(warnings))
    else:st.info('Chưa có lời. Chạy ASR trước; không tự tạo transcript giả.')
    st.subheader('Giọng tiếng Việt')
    provider=st.selectbox('TTS provider',['local','azure'],index=0 if settings.tts_provider=='local' else 1)
    cloud=False;voices=[]
    if provider=='local':
        st.caption('Local CPU · VAIS1000/Piper · không gửi chữ/audio ra ngoài. Chất lượng cần nghe thử; model có một giọng, không hỗ trợ pitch/gender tuỳ chọn.')
        catalog=settings.tts_model_dir/'voices.json'
        if catalog.is_file():voices=json.loads(catalog.read_text(encoding='utf-8'))['voices']
        else:st.warning('Chưa có danh sách giọng đã kiểm chứng. Chạy setup_m3_models.py --tts.')
    else:
        st.warning('Azure là cloud: gửi chữ Việt tới Microsoft khi preview/TTS; có thể tính phí. Không upload audio gốc.')
        cloud=st.checkbox('Tôi chọn Azure và đồng ý gửi nội dung chữ Việt tới Microsoft')
        if st.button('Lấy danh sách giọng Azure',disabled=not cloud):
            try:
                from app.providers.tts.azure_tts_provider import AzureTTS
                st.session_state[f'azure_voices_{key}']=AzureTTS(settings).voices()
            except UserError as exc:st.error(str(exc))
        voices=st.session_state.get(f'azure_voices_{key}',[])
    if provider=='azure' and voices:
        gender=st.selectbox('Loại giọng',['Tất cả',*sorted({v.get('gender') or 'Không rõ' for v in voices})])
        if gender!='Tất cả':voices=[v for v in voices if (v.get('gender') or 'Không rõ')==gender]
    voice_id=st.selectbox('Giọng đã có',[v['id'] for v in voices],format_func=lambda v:next(x['name'] for x in voices if x['id']==v)) if voices else ''
    rate=st.slider('Tốc độ giọng',.8,1.2,1.0,step=.05)
    pitch=st.slider('Pitch (%)',-10.,10.,0.,disabled=provider=='local')
    volume=st.slider('Âm lượng',.1,1.5,1.,step=.1)
    voice=VoiceSettings(provider=provider,voice=voice_id,rate=rate,pitch=pitch if provider=='azure' else 0.,volume=volume,cloud_confirmed=cloud)
    sample=st.text_input('Lời nghe thử',value='Xin chào, đây là giọng đọc tiếng Việt.',max_chars=200)
    if st.button('Nghe thử giọng',disabled=not voices or (provider=='azure' and not cloud)):launch('preview',voice=voice,preview_text=sample)
    if rows:
        labels=sorted({s.speaker_id for s in rows})
        override=st.selectbox('Áp dụng cấu hình giọng',['Tất cả speaker',*labels])
        if st.button('Lưu cấu hình speaker',disabled=not voices):
            for label in labels if override=='Tất cả speaker' else [override]:save_speaker(sessions,key,label,voice)
            st.success('Đã lưu cấu hình giọng. Tác vụ mới dùng cấu hình này; tác vụ đang chạy giữ snapshot.')
        if st.button('Tạo lại TTS các lời đã chọn',disabled=not voices):launch('tts',selected_ids=selected,voice=voice)
    st.selectbox('Chế độ audio',['A · Chỉ giọng Việt, im lặng giữa lời'],disabled=True)
    st.caption('Mode B chưa bật: FFmpeg đơn giản không tách sạch thoại Trung khỏi nhạc/hiệu ứng. Không trộn thoại gốc vào dub.')
    rights=st.checkbox('Tôi xác nhận quyền dùng nguồn/âm thanh để xuất bản lồng tiếng')
    if project.rights_status=='unknown':st.warning('Quyền nguồn chưa xác định. Cập nhật quyền tại Text Replacement Studio trước khi xuất.')
    if st.button('Ghép toàn bộ audio Việt',type='primary',disabled=not voices):launch('assemble',voice=voice,rights_confirmed=rights)
    # History is reloaded explicitly; periodic status polling never starts jobs.
    for job in jobs[:10]:
        st.caption(f'{job.kind} · {job.status} · {job.id[:8]}')
        if job.status=='COMPLETED':
            with sessions() as db:parts=list(db.scalars(select(DubbedAudioSegment).where(DubbedAudioSegment.job_id==job.id)))
            if parts:
                st.dataframe([{'Lời':i+1,'Khung (s)':p.original_duration,'TTS (s)':p.generated_duration,'Sau sync (s)':p.final_duration,'Tốc độ':p.sync_factor,'Lưu ý':p.metadata_json.get('warning','')} for i,p in enumerate(parts)],hide_index=True)
                part=st.selectbox('Nghe đoạn',[p.audio_path for p in parts],format_func=lambda value:f"Lời {next(i+1 for i,p in enumerate(parts) if p.audio_path==value)}",key=f'part_{job.id}')
                if resolve_media(settings.storage_root,part).is_file():st.audio(str(resolve_media(settings.storage_root,part)))
            if job.output_path:
                path=resolve_media(settings.storage_root,job.output_path)
                if path.is_file():
                    st.audio(str(path));st.download_button('Tải audio WAV',path.read_bytes(),file_name=path.name,mime='audio/wav',key=f'dub_download_{job.id}')
    originals=sorted((settings.storage_root/f'projects/{key}/audio').glob('*/asr-16k.wav'))
    if originals:
        st.caption('Nghe nội dung nguồn · bản mono16k phục vụ ASR. Stream gốc được giữ riêng trong original.mka.');st.audio(str(originals[-1]))
    if st.button('Kiểm tra audio đã duyệt cho M4'):
        try:
            contract=approved_dub(sessions,settings,key);st.success(f"Audio sẵn sàng: {contract['duration']:.3f} giây. Chưa mux video.")
        except UserError as exc:st.error(str(exc))
