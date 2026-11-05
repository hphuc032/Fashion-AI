from app.utils.validators import UserError
from .base import SpeechPhrase


def parse_funasr(results):
    output=[]
    for row in results:
        sentences=row.get('sentence_info') or []
        if sentences:
            for s in sentences:
                output.append(SpeechPhrase(float(s['start'])/1000,float(s['end'])/1000,s.get('sentence',s.get('text','')),
                                           None,f"speaker_{s['spk']}" if 'spk' in s else 'speaker_1'))
        elif row.get('text'):
            times=row.get('timestamp',[])
            if not times:raise UserError('Model FunASR không trả timestamp; chọn model timestamp-capable hoặc Whisper.')
            output.append(SpeechPhrase(float(times[0][0])/1000,float(times[-1][1])/1000,row['text']))
    return output


class FunASRProvider:
    identity='funasr-local'
    def __init__(self,settings):
        if not (settings.asr_model_dir/'config.yaml').is_file():raise UserError('Thiếu model FunASR local timestamp-capable. Cài theo README hoặc chọn Whisper.')
        try:
            from funasr import AutoModel
        except ImportError as exc:raise UserError('Cài requirements-m3-funasr.txt để dùng FunASR.') from exc
        extras={}
        for field,target in [('funasr_vad_dir','vad_model'),('funasr_punc_dir','punc_model'),('funasr_speaker_dir','spk_model')]:
            path=getattr(settings,field)
            if path:
                if not (path/'config.yaml').is_file():raise UserError('Thiếu model phụ FunASR local đã cấu hình.')
                extras[target]=str(path)
        if settings.funasr_speaker_dir and not settings.funasr_vad_dir:raise UserError('Diarization FunASR cần VAD local; mặc định dùng speaker thủ công.')
        self.model=AutoModel(model=str(settings.asr_model_dir),device=settings.asr_device,ncpu=settings.ocr_cpu_threads,disable_update=True,trust_remote_code=False,disable_pbar=True,**extras)

    def transcribe(self,path,check):
        check()
        results=self.model.generate(input=str(path),sentence_timestamp=True,batch_size=1)
        check()
        return parse_funasr(results)
