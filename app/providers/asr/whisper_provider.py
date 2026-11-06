from app.utils.validators import UserError
from .base import SpeechPhrase


class WhisperProvider:
    identity='faster-whisper-local'
    def __init__(self,settings):
        path=settings.whisper_model_dir
        if not (path/'model.bin').is_file():raise UserError('Thiếu model Whisper local. Chạy setup_m3_models.py --whisper (base CPU).')
        try:
            from faster_whisper import WhisperModel
            self.model=WhisperModel(str(path),device=settings.asr_device,compute_type='int8' if settings.asr_device=='cpu' else 'float16',cpu_threads=settings.ocr_cpu_threads,num_workers=1,local_files_only=True)
        except ImportError as exc:raise UserError('Cài requirements-m3.txt để dùng faster-whisper.') from exc
        self.language=settings.asr_language

    def transcribe(self,path,check):
        segments,_=self.model.transcribe(str(path),language=self.language,beam_size=5,condition_on_previous_text=False,vad_filter=False,word_timestamps=True)
        result=[]
        for s in segments:
            check()
            if s.no_speech_prob>.6:continue
            # log probability/no-speech probability is not a calibrated confidence.
            result.append(SpeechPhrase(s.start,s.end,s.text.strip()))
        return result
