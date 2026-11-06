"""Streaming CFR-normalized render with an exact rational presentation clock."""
import json
import math
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

from app.services.frame_extractor import display_dimensions
from app.services.text_compositor import compose
from app.services.video_service import probe_video
from app.utils.validators import UserError


def stream_info(path,settings):
    try:
        result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file','-show_format','-show_streams','-of','json',str(path)],
                              shell=False,check=True,capture_output=True,timeout=30)
        data=json.loads(result.stdout)
        video=next(s for s in data['streams'] if s.get('codec_type')=='video' and not s.get('disposition',{}).get('attached_pic'))
        rate=video.get('avg_frame_rate','0/0')
        if rate in ('0/0','0','N/A'):
            rate=video.get('r_frame_rate','0/0')
        fps=Fraction(rate)
        duration=float(data['format']['duration'])
        if not 0<fps<=settings.render_max_fps or not math.isfinite(duration) or not 0<duration<=settings.max_video_seconds:
            raise ValueError()
        return fps,duration,next((s for s in data['streams'] if s.get('codec_type')=='audio'),None)
    except (OSError,subprocess.SubprocessError,KeyError,ValueError,TypeError,StopIteration,ZeroDivisionError) as exc:
        raise UserError('Không đọc được timeline video hoặc vượt giới hạn FPS/thời lượng render.') from exc


def read_frame(pipe,size):
    chunks=[]
    remaining=size
    while remaining:
        block=pipe.read(remaining)
        if not block:
            if remaining==size:
                return None
            raise UserError('FFmpeg trả về khung hình không đầy đủ.')
        chunks.append(block)
        remaining-=len(block)
    return b''.join(chunks)


def stop_process(process):
    if process and process.poll() is None:
        process.terminate()
        try: process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def render_video(source,output,items,settings,quality='balanced',check=lambda:None,progress=lambda value:None):
    presets={'draft':('veryfast','26'),'balanced':('fast','21'),'high':('medium','18')}
    if quality not in presets:
        raise UserError('Chất lượng render không hợp lệ.')
    fps,duration,audio=stream_info(source,settings)
    width,height=display_dimensions(source,settings)
    if width%2 or height%2 or width*height>settings.ocr_max_source_pixels:
        raise UserError('Render H.264 4:2:0 cần kích thước chẵn và nằm trong giới hạn pixel.')
    expected=math.ceil(duration*float(fps))
    if expected>settings.render_max_frames:
        raise UserError('Video vượt giới hạn số khung render.')
    # Preflight every region key time before spending a full render.
    blank=np.zeros((height,width,3),np.uint8)
    times={i['start'] for i in items}|{max(i['start'],i['end']-1/float(fps)) for i in items}
    times|={d['time'] for i in items for d in i.get('detections',[]) if i['start']<=d['time']<i['end']}
    for timestamp in sorted(times):
        check()
        compose(blank,timestamp,items,strict=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    decoder=encoder=None
    count=0
    with output.with_suffix('.decode.log').open('wb') as decode_log,output.with_suffix('.encode.log').open('wb') as encode_log:
        try:
            rate=f'{fps.numerator}/{fps.denominator}'
            decoder=subprocess.Popen([settings.ffmpeg_path,'-nostdin','-v','error','-threads','1','-protocol_whitelist','file','-i',str(source),
                                      '-map','0:v:0','-an','-vf',f'fps=fps={rate}:start_time=0:round=near',
                                      '-pix_fmt','bgr24','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,stderr=decode_log,shell=False)
            preset,crf=presets[quality]
            args=[settings.ffmpeg_path,'-nostdin','-y','-v','error','-f','rawvideo','-pix_fmt','bgr24','-video_size',f'{width}x{height}',
                  '-framerate',rate,'-i','pipe:0','-protocol_whitelist','file','-i',str(source),'-map','0:v:0','-map','1:a:0?',
                  '-map_metadata','1','-c:v','libx264','-preset',preset,'-crf',crf,'-pix_fmt','yuv420p','-threads','2']
            args+=['-c:a','copy' if audio and audio.get('codec_name') in {'aac','mp3','alac'} else 'aac']
            args+=['-movflags','+faststart',str(output)]
            encoder=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=encode_log,shell=False)
            while True:
                check()
                raw=read_frame(decoder.stdout,width*height*3)
                if raw is None:
                    break
                if count>=settings.render_max_frames:
                    raise UserError('Đã chạm giới hạn khung render.')
                timestamp=float(Fraction(count,1)/fps)
                frame=np.frombuffer(raw,np.uint8).reshape(height,width,3)
                composed,_=compose(frame,timestamp,items,strict=True)
                encoder.stdin.write(composed.tobytes())
                count+=1
                if count%5==0:
                    progress(min(.95,count/max(1,expected)*.95))
            encoder.stdin.close()
            encoder.stdin=None
            if decoder.wait(timeout=30)!=0 or encoder.wait(timeout=120)!=0 or count==0:
                raise UserError('FFmpeg render thất bại. Kiểm tra video và thử lại.')
            check()
            metadata=probe_video(output,settings.ffprobe_path,'.mp4')
            tolerance=max(.12,2/float(fps))
            if (metadata.width,metadata.height)!=(width,height) or metadata.video_codec!='h264' or abs(metadata.duration-duration)>tolerance or bool(metadata.audio_codec)!=bool(audio):
                raise UserError('Video xuất không đạt kiểm tra kích thước/thời lượng/âm thanh.')
            progress(1)
            return dict(frames=count,fps=rate,duration=metadata.duration,audio_codec=metadata.audio_codec,
                        normalized_vfr=True,audio_copied=bool(audio and audio.get('codec_name') in {'aac','mp3','alac'}))
        except (OSError,subprocess.SubprocessError) as exc:
            raise UserError('Không chạy được FFmpeg hoặc render quá thời gian.') from exc
        finally:
            stop_process(decoder)
            stop_process(encoder)
            if decoder and decoder.stdout: decoder.stdout.close()
            if encoder and encoder.stdin: encoder.stdin.close()
