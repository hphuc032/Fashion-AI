"""Original Mandarin synthetic fixture; local AISHELL3 TTS model, no network."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def generate(path,root):
    import sherpa_onnx
    import soundfile as sf
    root=Path(root);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    config=sherpa_onnx.OfflineTtsConfig(model=sherpa_onnx.OfflineTtsModelConfig(vits=sherpa_onnx.OfflineTtsVitsModelConfig(
        model=str(root/'model.onnx'),lexicon=str(root/'lexicon.txt'),tokens=str(root/'tokens.txt'),noise_scale=0.,noise_scale_w=0.),
        num_threads=2,provider='cpu'),max_num_sentences=1)
    if not config.validate():raise RuntimeError('Install the explicit AISHELL3 fixture model first')
    engine=sherpa_onnx.OfflineTts(config)
    audio=engine.generate('我喜欢这件衣服。',sid=21,speed=.9)
    sf.write(str(path),audio.samples,audio.sample_rate,subtype='PCM_16')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',default='storage/temp/m3-chinese-source.wav');parser.add_argument('--model-dir',default='storage/models/vits-icefall-zh-aishell3')
    args=parser.parse_args();print(generate(args.output,args.model_dir))
