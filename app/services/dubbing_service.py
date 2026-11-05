"""Stage implementations used by the disposable speech worker."""
import hashlib
import json
from pathlib import Path
from uuid import uuid4
from sqlalchemy import delete,select
from app.database.speech_schema import SpeechSegment,DubbedAudioSegment
from app.providers.asr.base import make_asr
from app.providers.tts.base import make_tts,VoiceSettings
from app.services.audio_extractor import extract_audio,audio_info,ffmpeg
from app.services.audio_sync_service import synchronize,assemble_timeline
from app.services.speech_repository import fingerprint
from app.services.speech_segmentation import normalize_phrases
from app.services.translation_service import TranslationService
from app.services.translation_review_service import evaluate
from app.services.storage_service import resolve_media
from app.utils.validators import UserError

SPEECH_CONTEXT='Chinese spoken fashion dialogue to faithful concise conversational Vietnamese; preserve meaning, brands, numbers and product identifiers; do not invent claims.'


def transcribe(sessions,settings,project,folder,check,progress,provider_factory=make_asr):
    if settings.asr_provider=='funasr' and settings.funasr_speaker_dir and project.duration>settings.asr_chunk_seconds:
        raise UserError('Diarization chỉ được dùng trong một chunk để tránh nhầm speaker giữa chunk. Tăng chunk trong giới hạn hoặc dùng speaker chỉnh tay.')
    progress('EXTRACTING_AUDIO',.05)
    original,wav=extract_audio(sessions,settings,project.id,check)
    progress('TRANSCRIBING',.1)
    provider=provider_factory(settings)
    phrases=[]
    step=settings.asr_chunk_seconds-settings.asr_overlap_seconds
    offset=0.
    while offset<project.duration:
        check()
        length=min(settings.asr_chunk_seconds,project.duration-offset)
        chunk=folder/'chunk.wav'
        try:
            ffmpeg(settings,['-ss',offset,'-i',wav,'-t',length,'-ac','1','-ar','16000','-c:a','pcm_s16le',chunk],check)
            found=provider.transcribe(chunk,check)
            # Validate/clip local results before applying chunk offset.
            local=normalize_phrases(found,0,length)
            phrases=normalize_phrases(local,offset,project.duration,phrases)
            if len(phrases)>settings.dub_max_segments:raise UserError('Quá nhiều đoạn lời; giảm thời lượng/chỉnh chunk.')
        finally:chunk.unlink(missing_ok=True)
        progress('TRANSCRIBING',.1+.85*min(1,(offset+length)/project.duration))
        if offset+length>=project.duration:break
        offset+=step
    return phrases,provider.identity,str(original.relative_to(settings.storage_root))


def translate_speech(sessions,settings,items,check,progress,translator_factory=TranslationService):
    translator=translator_factory(settings,sessions,context=SPEECH_CONTEXT)
    results=[]
    for i,item in enumerate(items):
        check()
        text,identity=translator.translate(item['original_text'],check)
        if not text.strip():raise UserError('Chọn provider Argos hoặc nhập bản dịch; không có bản dịch để lưu.')
        flags=evaluate(item['original_text'],text,1.,settings=settings).reasons
        results.append((item,text,flags))
        progress('TRANSLATING',(i+1)/max(1,len(items))*.95)
    return results


def synthesize_cached(sessions,settings,project_id,text,voice,provider,check):
    if not text.strip() or len(text)>2000:raise UserError('Nội dung TTS trống/quá dài.')
    key=hashlib.sha256(json.dumps([provider.identity,text,voice.model_dump(exclude={'cloud_confirmed'})],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    root=resolve_media(settings.storage_root,f'projects/{project_id}/audio/tts-cache')
    root.mkdir(parents=True,exist_ok=True)
    target=root/f'{key}.wav'
    if target.is_file():
        info=audio_info(target,settings)
        if info and 0<info['duration']<=120:return target
    partial=root/f'{key}.partial.wav'
    try:
        provider.synthesize(text,voice,partial,check)
        info=audio_info(partial,settings)
        if not info or not 0<info['duration']<=120:raise UserError('TTS không trả audio hợp lệ hoặc đoạn quá dài.')
        check();partial.replace(target)
    finally:partial.unlink(missing_ok=True)
    return target


def generate_audio(sessions,settings,job,project,folder,items,check,progress,tts_factory=make_tts):
    voices={}
    providers={}
    records=[]
    assembled=[]
    for i,item in enumerate(items):
        voice=VoiceSettings.model_validate(item['voice'])
        identity=voice.provider
        if identity not in providers:providers[identity]=tts_factory(settings,voice)
        provider=providers[identity]
        progress('GENERATING_TTS',.05+.7*i/max(1,len(items)))
        raw=synthesize_cached(sessions,settings,project.id,item['translated_text'],voice,provider,check)
        check();info=audio_info(raw,settings)
        normalized=folder/f"{item['id']}.wav"
        progress('SYNCHRONIZING',.05+.7*(i+.5)/max(1,len(items)))
        metadata=synchronize(raw,normalized,item['end_time']-item['start_time'],voice,settings,check)
        records.append(dict(id=str(uuid4()),job_id=job.id,speech_segment_id=item['id'],audio_path=normalized.relative_to(settings.storage_root).as_posix(),
                            original_duration=item['end_time']-item['start_time'],generated_duration=metadata['generated_duration'],
                            final_duration=metadata['final_duration'],sync_factor=metadata['sync_factor'],metadata_json={**metadata,'raw_audio_path':raw.relative_to(settings.storage_root).as_posix(),'fingerprint':item['fingerprint'],'voice':item['voice']}))
        assembled.append(dict(start=item['start_time'],end=item['end_time'],path=normalized))
    if job.kind=='tts':return records,None
    progress('ASSEMBLING',.85)
    partial=folder/'dub.partial.wav'
    duration=assemble_timeline(assembled,partial,project.duration,check)
    info=audio_info(partial,settings)
    if not info or abs(info['duration']-project.duration)>1/24000 or info['sample_rate']!=24000:raise UserError('WAV master không đúng timeline.')
    return records,partial
