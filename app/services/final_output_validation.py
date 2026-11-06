"""Metadata plus decoded audio and sampled visual evidence, not exit-code success."""
import math
import json
import re
import struct
import subprocess
from fractions import Fraction
import numpy as np
import soundfile as sf
from PIL import Image
from app.services.audio_extractor import ffmpeg
from app.services.video_mux_service import probe_streams,geometry_filter,audio_graph
from app.utils.validators import UserError


def faststart(path):
    atoms=[]
    with path.open('rb') as stream:
        size=path.stat().st_size
        while stream.tell()+8<=size:
            offset=stream.tell();length,kind=struct.unpack('>I4s',stream.read(8))
            if length==1:length=struct.unpack('>Q',stream.read(8))[0]
            if length==0:length=size-offset
            if length<8 or offset+length>size:raise UserError('Container MP4 có atom hỏng.')
            atoms.append(kind)
            if b'moov' in atoms and b'mdat' in atoms:break
            stream.seek(offset+length)
    return b'moov' in atoms and b'mdat' in atoms and atoms.index(b'moov')<atoms.index(b'mdat')


def validate_metadata(path,options,mode,settings):
    if not path.is_file() or path.stat().st_size==0:raise UserError('Output MP4 trống hoặc bị thiếu.')
    raw=probe_streams(path,settings);streams=raw.get('streams',[])
    video=next((s for s in streams if s.get('codec_type')=='video'),None)
    audio=next((s for s in streams if s.get('codec_type')=='audio'),None)
    subtitles=[s for s in streams if s.get('codec_type')=='subtitle']
    try:
        duration=float(raw['format']['duration']);fps=Fraction(video['avg_frame_rate'])
        if not {'mov','mp4'}.intersection(raw['format']['format_name'].split(',')):raise ValueError()
        if video['codec_name']!='h264' or video['pix_fmt']!='yuv420p' or (video['width'],video['height'])!=(options['width'],options['height']):raise ValueError()
        if abs(float(fps)-float(Fraction(options['fps'])))>.001 or abs(duration-options['duration'])>max(.06,1/float(fps)+.025):raise ValueError()
        if audio['codec_name']!='aac' or int(audio['sample_rate'])!=48000 or audio['channels']!=1:raise ValueError()
        if abs(float(video.get('start_time',0)))>.05 or abs(float(audio.get('start_time',0)))>.05:raise ValueError()
        if mode=='soft' and (len(subtitles)!=1 or subtitles[0]['codec_name']!='mov_text' or subtitles[0].get('tags',{}).get('language')!='vie'):raise ValueError()
        if mode!='soft' and subtitles:raise ValueError()
        if not faststart(path):raise ValueError()
    except (KeyError,TypeError,ValueError,ZeroDivisionError) as exc:raise UserError('Output sai container/codec/kích thước/FPS/timeline/audio/phụ đề/faststart.') from exc
    return {'container':'mp4','video_codec':'h264','audio_codec':'aac','pixel_format':'yuv420p','width':video['width'],'height':video['height'],
            'aspect_ratio':f"{video['width']//math.gcd(video['width'],video['height'])}:{video['height']//math.gcd(video['width'],video['height'])}",
            'fps':str(fps),'duration':duration,'audio_sample_rate':48000,'audio_channels':1,'video_start':float(video.get('start_time',0)),
            'audio_start':float(audio.get('start_time',0)),'subtitle_codec':'mov_text' if mode=='soft' else None,'subtitle_language':'vie' if mode!='none' else None,'faststart':True}


def audio_evidence(output,reference,options,config,settings,background,check):
    folder=output.parent;decoded=folder/'validation-output.wav';expected=folder/'validation-reference.wav'
    try:
        ffmpeg(settings,['-i',output,'-map','0:a:0','-vn','-ar','24000','-ac','1','-c:a','pcm_s16le',decoded],check)
        args=[]
        if options['start']:args+=['-ss',options['start']]
        args+=['-i',reference]
        if background:
            if options['start']:args+=['-ss',options['start']]
            args+=['-i',background]
        ffmpeg(settings,[*args,'-filter_complex',audio_graph(options['duration'],config,voice_index=0,background_index=1 if background else None),'-map','[a]',
                         '-ar','24000','-ac','1','-c:a','pcm_s16le',expected],check)
        cross=aa=bb=0.;peak=0.;count=0
        with sf.SoundFile(decoded) as actual,sf.SoundFile(expected) as wanted:
            if abs(actual.frames-wanted.frames)>2400:raise UserError('Audio xuất lệch thời lượng so với timeline M3.')
            while True:
                check();a=actual.read(4096,dtype='float64');b=wanted.read(4096,dtype='float64')
                if not len(b):break
                if len(a)<len(b):raise UserError('Output bị mất phần cuối lời Việt.')
                a=a[:len(b)]
                peak=max(peak,float(np.max(np.abs(a),initial=0)))
                cross+=float(np.dot(a,b));aa+=float(np.dot(a,a));bb+=float(np.dot(b,b));count+=len(b)
        correlation=cross/math.sqrt(aa*bb) if aa*bb>1e-12 else 1. if aa+bb<1e-6 else 0.
        if correlation<.90 or peak>=.995:raise UserError('Audio output lệch/mất lời/clipping so với M3; không công bố.')
        return {'zero_lag_waveform_correlation':correlation,'decoded_peak':peak,'compared_samples_24k':count,'reference':'configured M3 dub + validated background only',
                'silence_policy':'M3 silence retained, not original dialogue','duration_difference_seconds':(sf.info(decoded).frames-sf.info(expected).frames)/24000}
    finally:decoded.unlink(missing_ok=True);expected.unlink(missing_ok=True)


def frame(path,timestamp,target,settings,check,vf=None):
    args=['-ss',str(max(0,timestamp)),'-i',path,'-map','0:v:0','-an','-frames:v','1']
    if vf:args+=['-vf',vf]
    ffmpeg(settings,[*args,target],check)
    with Image.open(target) as image:return np.array(image.convert('RGB'))


def visual_evidence(output,video,options,config,subtitle_report,settings,check):
    folder=output.parent;actual=folder/'validation-frame.png';reference=folder/'validation-reference.png'
    evidence=[]
    try:
        events=subtitle_report['events']
        samples=[((e['start']+e['end'])/2,e) for e in events[:3]] or [(min(options['duration']/2,max(0,options['duration']-.04)),None)]
        for timestamp,event in samples:
            check()
            shown=frame(output,timestamp,actual,settings,check)
            base=frame(video,timestamp+options['start'],reference,settings,check,geometry_filter(options['width'],options['height'],config.aspect_mode))
            if base.mean()>15 and shown.mean()<1:raise UserError('Phát hiện frame đen bất thường so với M2.')
            visible=None
            if config.subtitle_mode=='burn' and event:
                x1,y1,x2,y2=event['bbox'];diff=np.abs(shown[y1:y2,x1:x2].astype(float)-base[y1:y2,x1:x2].astype(float))
                changed=int((diff.max(axis=2)>20).sum()) if diff.size else 0
                if changed<10:raise UserError('Không xác nhận được phụ đề burn-in trong frame đại diện; kiểm tra font/vị trí.')
                visible={'changed_pixels':changed,'bbox':event['bbox'],'text':event['text']}
            evidence.append({'time':timestamp,'unexpected_black_change':False,'burned_subtitle':visible})
        return evidence
    finally:actual.unlink(missing_ok=True);reference.unlink(missing_ok=True)


def validate_output(output,video,audio,options,config,subtitle_report,settings,background=None,check=lambda:None):
    metadata=validate_metadata(output,options,config.subtitle_mode,settings)
    # Decode the complete video stream to detect malformed data, bounded by worker lease.
    ffmpeg(settings,['-err_detect','explode','-i',output,'-map','0:v:0','-an','-f','null','-'],check,timeout=settings.final_timeout_seconds)
    report={'metadata':metadata,'audio_sync':audio_evidence(output,audio,options,config,settings,background,check),
            'representative_frames':visual_evidence(output,video,options,config,subtitle_report,settings,check),'full_video_decode':True}
    if config.subtitle_mode=='soft':
        try:
            result=subprocess.run([settings.ffprobe_path,'-v','error','-select_streams','s:0','-show_packets','-show_data','-of','json',str(output)],check=True,capture_output=True,timeout=30)
            captions=[]
            for packet in json.loads(result.stdout).get('packets',[]):
                lines=[line.split(':',1)[1].strip().split('  ',1)[0].replace(' ','') for line in packet.get('data','').splitlines() if ':' in line]
                data=bytes.fromhex(''.join(lines))
                if len(data)>=2:
                    length=int.from_bytes(data[:2],'big');captions.append(data[2:2+length].decode('utf-8'))
            text=' '.join(captions).replace('\u2060','')
            normalized=lambda s:''.join(s.split())
            for event in subtitle_report['events']:
                if normalized(event['text']) not in normalized(text):raise UserError('Soft subtitle không giữ đủ nội dung tiếng Việt.')
            report['soft_subtitle_text_validated']=True
        except (OSError,ValueError,UnicodeError,subprocess.SubprocessError) as exc:raise UserError('Không giải mã được soft subtitle output.') from exc
    check();return report
