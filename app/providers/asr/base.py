from dataclasses import dataclass
from typing import Protocol


@dataclass
class SpeechPhrase:
    start:float
    end:float
    text:str
    confidence:float|None=None
    speaker:str='speaker_1'


class ASRProvider(Protocol):
    identity:str
    def transcribe(self,path,check)->list[SpeechPhrase]: ...


def make_asr(settings):
    if settings.asr_provider=='funasr':
        from .funasr_provider import FunASRProvider
        return FunASRProvider(settings)
    if settings.asr_provider=='whisper':
        from .whisper_provider import WhisperProvider
        return WhisperProvider(settings)
    from app.utils.validators import UserError
    raise UserError('Chọn FunASR hoặc faster-whisper.')
