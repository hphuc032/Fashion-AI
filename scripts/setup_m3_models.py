"""Explicit downloads only; never called by the application."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import load_settings
from scripts.setup_m1_models import download,install_archive


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--whisper',action='store_true')
    parser.add_argument('--whisper-size',choices=['tiny','base','small'],default='base',help='Stored at configured WHISPER_MODEL_DIR; default CPU base')
    parser.add_argument('--tts',action='store_true')
    parser.add_argument('--fixture-chinese',action='store_true',help='Optional AISHELL3 synthesis model for original Mandarin tests only')
    args=parser.parse_args()
    if not args.whisper and not args.tts and not args.fixture_chinese:parser.error('Choose --whisper, --tts and/or --fixture-chinese')
    settings=load_settings()
    if args.whisper:
        from huggingface_hub import snapshot_download
        snapshot_download(f'Systran/faster-whisper-{args.whisper_size}',local_dir=settings.whisper_model_dir,
                          allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'])
        manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in settings.whisper_model_dir.iterdir() if p.is_file() and p.name!='local-manifest.json'}
        (settings.whisper_model_dir/'local-manifest.json').write_text(json.dumps(manifest,sort_keys=True),encoding='utf-8')
    if args.tts:
        name='vits-piper-vi_VN-vais1000-medium'
        archive=settings.storage_root/'models/downloads'/f'{name}.tar.bz2'
        archive.parent.mkdir(parents=True,exist_ok=True)
        download(f'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{name}.tar.bz2',archive)
        if not settings.tts_model_dir.is_dir():install_archive(archive,settings.tts_model_dir.parent,settings.tts_model_dir.name)
        from app.providers.tts.local_tts_provider import LocalTTS
        provider=LocalTTS(settings)
        (settings.tts_model_dir/'voices.json').write_text(json.dumps({'identity':provider.identity,'voices':provider.voices()},ensure_ascii=False),encoding='utf-8')
    if args.fixture_chinese:
        name='vits-icefall-zh-aishell3'
        archive=settings.storage_root/'models/downloads'/f'{name}.tar.bz2'
        archive.parent.mkdir(parents=True,exist_ok=True)
        download(f'https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/{name}.tar.bz2',archive)
        if not (settings.storage_root/'models'/name).is_dir():install_archive(archive,settings.storage_root/'models',name)
    print('Explicit local model setup complete. No application-start downloads.')


if __name__=='__main__':main()
