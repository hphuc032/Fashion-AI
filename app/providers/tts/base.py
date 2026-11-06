from typing import Literal,Protocol
from pydantic import BaseModel,Field
from app.utils.validators import UserError


class VoiceSettings(BaseModel):
    provider:Literal['local','azure']='local'
    voice:str='vais1000:0'
    rate:float=Field(default=1.0,ge=.8,le=1.2,allow_inf_nan=False)
    pitch:float=Field(default=0.,ge=-10,le=10,allow_inf_nan=False)
    volume:float=Field(default=1.0,ge=.1,le=1.5,allow_inf_nan=False)
    cloud_confirmed:bool=False


class TTSProvider(Protocol):
    identity:str
    def voices(self)->list[dict]: ...
    def synthesize(self,text,voice,output,check): ...


def make_tts(settings,voice):
    if voice.provider=='local':
        from .local_tts_provider import LocalTTS
        return LocalTTS(settings)
    if not voice.cloud_confirmed:raise UserError('Azure gửi nội dung chữ tới dịch vụ ngoài; cần xác nhận rõ trước khi dùng.')
    from .azure_tts_provider import AzureTTS
    return AzureTTS(settings)
