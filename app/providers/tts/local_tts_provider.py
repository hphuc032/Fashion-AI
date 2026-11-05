import hashlib
from importlib.metadata import version
from app.utils.validators import UserError


class LocalTTS:
    def __init__(self,settings):
        root=settings.tts_model_dir
        models=list(root.glob('*.onnx'))
        if len(models)!=1 or not (root/'tokens.txt').is_file() or not (root/'espeak-ng-data').is_dir():
            raise UserError('Thiếu model TTS Việt local. Chạy setup_m3_models.py --tts.')
        import sherpa_onnx
        manifest=root/'local-manifest.json'
        if not manifest.is_file():raise UserError('Cần cài model TTS bằng script để có manifest cache.')
        self.identity='sherpa-'+version('sherpa-onnx')+'-vais1000-'+hashlib.sha256(manifest.read_bytes()).hexdigest()
        config=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(
            vits=sherpa_onnx.OfflineTtsVitsModelConfig(model=str(models[0]),tokens=str(root/'tokens.txt'),data_dir=str(root/'espeak-ng-data')),
            num_threads=settings.ocr_cpu_threads,provider='cpu',debug=False),max_num_sentences=1)
        if not config.validate():raise UserError('Cấu hình model TTS local không hợp lệ.')
        self.engine=sherpa_onnx.OfflineTts(config)

    def voices(self):
        return [dict(id=f'vais1000:{i}',name=f'VAIS1000 · giọng Việt {i+1}',gender='không có metadata',pitch=False) for i in range(self.engine.num_speakers)]

    def synthesize(self,text,voice,output,check):
        if voice.voice not in {v['id'] for v in self.voices()}:raise UserError('Giọng không có trong model TTS đã cài.')
        if voice.pitch:raise UserError('TTS local này không hỗ trợ pitch; dùng0 hoặc chọn provider khác.')
        check()
        audio=self.engine.generate(text,sid=int(voice.voice.split(':')[1]),speed=voice.rate)
        check()
        if not len(audio.samples):raise UserError('TTS trả audio trống.')
        import soundfile as sf
        sf.write(str(output),audio.samples,audio.sample_rate,subtype='PCM_16')
