"""Optional explicit cloud text-only synthesis; credentials never in snapshots."""
import os
import re
from xml.sax.saxutils import escape
import requests
from app.utils.validators import UserError


class AzureTTS:
    def __init__(self,settings):
        self.key=os.getenv('AZURE_SPEECH_KEY','')
        region=os.getenv('AZURE_SPEECH_REGION','')
        if not self.key or not re.fullmatch('[a-z0-9-]{2,40}',region):raise UserError('Thiếu cấu hình Azure Speech trong môi trường.')
        self.base=f'https://{region}.tts.speech.microsoft.com/cognitiveservices'
        self.identity=f'azure-speech-{region}-wav-v1'
        self.headers={'Ocp-Apim-Subscription-Key':self.key}
        self._voices=None

    def voices(self):
        if self._voices is None:
            try:
                result=requests.get(self.base+'/voices/list',headers=self.headers,timeout=20)
                result.raise_for_status()
                self._voices=[dict(id=v['ShortName'],name=v['DisplayName'],gender=v.get('Gender'),pitch=True) for v in result.json() if v.get('Locale')=='vi-VN']
            except (requests.RequestException,ValueError,KeyError) as exc:raise UserError('Không lấy được danh sách giọng Azure Việt. Kiểm tra cấu hình/kết nối.') from exc
        return self._voices

    def synthesize(self,text,voice,output,check):
        if voice.voice not in {v['id'] for v in self.voices()}:raise UserError('Giọng chưa được Azure xác nhận khả dụng.')
        payload=f'<speak version="1.0" xml:lang="vi-VN"><voice name="{escape(voice.voice)}"><prosody rate="{(voice.rate-1)*100:+.0f}%" pitch="{voice.pitch:+.0f}%">{escape(text)}</prosody></voice></speak>'
        for attempt in range(3):
            check()
            try:
                result=requests.post(self.base+'/v1',headers={**self.headers,'Content-Type':'application/ssml+xml','X-Microsoft-OutputFormat':'riff-24000hz-16bit-mono-pcm'},data=payload.encode(),timeout=45)
                if result.status_code==429 or result.status_code>=500:
                    if attempt<2:continue
                result.raise_for_status()
                check();output.write_bytes(result.content);return
            except requests.RequestException as exc:
                if attempt==2:raise UserError('Azure TTS lỗi sau các lần thử; không tạo audio thay thế.') from exc
