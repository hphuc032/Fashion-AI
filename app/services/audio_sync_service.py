"""Conservative, pitch-preserving alignment and block-wise WAV assembly."""
import math
import numpy as np
import soundfile as sf
from app.services.audio_extractor import audio_info,ffmpeg
from app.utils.validators import UserError

RATE=24000


def atempo_chain(factor):
    if not math.isfinite(factor) or not .125<=factor<=8:raise UserError('Hệ số atempo không hợp lệ.')
    values=[]
    while factor>2:values.append(2.);factor/=2
    while factor<.5:values.append(.5);factor/=.5
    values.append(factor)
    return ','.join(f'atempo={x:.10f}' for x in values)


def synchronize(source,output,available,voice,settings,check=lambda:None):
    info=audio_info(source,settings)
    if not info or not math.isfinite(available) or available<=0:raise UserError('Khoảng lời/audio không hợp lệ.')
    ratio=info['duration']/available
    # Short speech stays natural with trailing silence. Only gentle mismatch stretches.
    factor=ratio if ratio>1 or settings.sync_min_factor<=ratio<1 else 1.
    if factor>settings.sync_max_factor:
        raise UserError(f'Lời Việt quá dài ({ratio:.2f}× khung). Rút gọn bản dịch hoặc chỉnh timing rồi tạo lại; không ép tốc độ cực đoan.')
    filters=[atempo_chain(factor),'loudnorm=I=-20:TP=-2:LRA=7',f'volume={voice.volume}','aresample=24000','alimiter=limit=0.89:level=disabled']
    try:
        ffmpeg(settings,['-i',source,'-af',','.join(filters),'-ac','1','-ar',RATE,'-c:a','pcm_s16le',output],check)
        final=audio_info(output,settings)
        if not final or final['duration']>available+.035:raise UserError('Audio sau sync vượt khung; cần chỉnh timing.')
        return {'generated_duration':info['duration'],'final_duration':final['duration'],'sync_factor':factor,
                'duration_ratio':ratio,'warning':'Lời ngắn: giữ tốc độ tự nhiên, phần còn lại im lặng.' if ratio<settings.sync_min_factor else 'Đã chỉnh nhẹ tốc độ.' if abs(factor-1)>.01 else ''}
    except Exception:
        output.unlink(missing_ok=True);raise


def assemble_timeline(segments,output,duration,check=lambda:None):
    if not math.isfinite(duration) or duration<=0:raise UserError('Timeline audio không hợp lệ.')
    total=round(duration*RATE)
    position=0
    try:
        with sf.SoundFile(str(output),'w',samplerate=RATE,channels=1,subtype='PCM_16') as target:
            for segment in sorted(segments,key=lambda s:s['start']):
                check()
                start,end=round(segment['start']*RATE),round(segment['end']*RATE)
                if start<position or end>total or end<=start:raise UserError('Các đoạn lời bị chồng hoặc vượt timeline. Chỉnh tay trước khi ghép.')
                remaining=start-position
                while remaining:
                    check();n=min(4096,remaining);target.write(np.zeros(n,dtype=np.float32));remaining-=n
                position=start
                with sf.SoundFile(str(segment['path'])) as source:
                    if source.samplerate!=RATE or source.channels!=1 or source.frames>end-start+round(.035*RATE):raise UserError('Audio đoạn chưa chuẩn hóa hoặc vượt khung.')
                    for block in source.blocks(blocksize=4096,dtype='float32'):
                        check()
                        if not np.isfinite(block).all() or np.max(np.abs(block),initial=0)>.99:raise UserError('Audio bị clipping/không hợp lệ; cần tạo lại.')
                        if position+len(block)>total:raise UserError('Audio đoạn vượt timeline.')
                        target.write(block);position+=len(block)
            while position<total:
                check();n=min(4096,total-position);target.write(np.zeros(n,dtype=np.float32));position+=n
    except Exception:
        output.unlink(missing_ok=True);raise
    return total/RATE
