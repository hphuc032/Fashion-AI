"""Stream FFmpeg only from validated M2 video and M3 audio, never source dialogue."""
import json
import math
import shutil
import subprocess
import time
from fractions import Fraction
from pathlib import Path
from app.services.audio_extractor import audio_info
from app.services.final_render_config import dimensions
from app.services.subtitle_service import soft_text_bridge
from app.utils.validators import UserError


def probe_streams(path,settings):
    try:
        result=subprocess.run([settings.ffprobe_path,'-v','error','-protocol_whitelist','file','-show_streams','-show_format','-of','json',str(path)],capture_output=True,check=True,timeout=30)
        return json.loads(result.stdout)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:raise UserError('Không đọc được artifact video/audio bằng FFprobe.') from exc


def capabilities(settings):
    def names(option):
        try:
            result=subprocess.run([settings.ffmpeg_path,'-hide_banner',option],check=True,capture_output=True,timeout=15,text=True,errors='replace')
            return {p[1] for line in result.stdout.splitlines() if len(p:=line.split())>=2}
        except (OSError,subprocess.SubprocessError) as exc:raise UserError('Không kiểm tra được FFmpeg. Cài bản có libx264, AAC và libass.') from exc
    encoders,filters=names('-encoders'),names('-filters')
    encoder='libx264' if 'libx264' in encoders else 'libopenh264' if 'libopenh264' in encoders else None
    return {'video_encoder':encoder,'aac':'aac' in encoders,'ass_filter':'ass' if 'ass' in filters else 'subtitles' if 'subtitles' in filters else None,'mov_text':'mov_text' in encoders}


def geometry_filter(width,height,aspect_mode='fit'):
    if aspect_mode=='crop':return f'scale={width}:{height}:force_original_aspect_ratio=increase:force_divisible_by=2,crop={width}:{height},setsar=1'
    return f'scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1'


def audio_graph(span,config,voice_index=1,background_index=None):
    result=f'[{voice_index}:a:0]asetpts=PTS-STARTPTS,aresample=48000,apad,atrim=duration={span},volume={config.voice_volume}'
    if background_index is not None:
        result+='[voice];'+f'[{background_index}:a:0]asetpts=PTS-STARTPTS,aresample=48000,apad,atrim=duration={span},volume={config.background_volume}[bg];[voice][bg]amix=inputs=2:normalize=0'
    return result+',alimiter=limit=0.89:level=disabled:latency=1[a]'


def timeline_options(video,audio,project_duration,config,settings,is_preview=False):
    info=probe_streams(video,settings)
    v=next((s for s in info.get('streams',[]) if s.get('codec_type')=='video'),None)
    if not v:raise UserError('M2 không có video stream.')
    try:fps=Fraction(v['avg_frame_rate']) if config.output_fps=='source' else Fraction(config.output_fps)
    except (ValueError,KeyError,ZeroDivisionError) as exc:raise UserError('FPS đầu vào không hợp lệ.') from exc
    if not 0<fps<=settings.render_max_fps:raise UserError('FPS vượt giới hạn xuất.')
    tolerance=max(.12,2/float(fps))
    if not math.isfinite(project_duration) or project_duration<=0 or abs(float(info['format']['duration'])-project_duration)>tolerance:raise UserError('M2/timeline nguồn chênh quá mức; render lại M2.')
    audio_meta=audio_info(audio,settings)
    if not audio_meta:raise UserError('M3 không có audio stream.')
    if audio_meta['duration']>project_duration+.002:raise UserError('Lời Việt dài hơn video; chỉnh M3, không tự cắt lời.')
    width,height=dimensions(int(v['width']),int(v['height']),config,is_preview)
    if width%2 or height%2 or width*height>settings.final_max_pixels:raise UserError('Kích thước xuất cần chẵn và trong giới hạn pixel.')
    if config.aspect_mode=='crop' and abs(width/height-int(v['width'])/int(v['height']))>.01 and not config.crop_confirmed:raise UserError('Crop có thể mất nội dung/attribution; cần xác nhận rõ hoặc dùng fit padding.')
    start=config.preview_start if is_preview else 0.
    span=min(config.preview_seconds,settings.final_preview_max_seconds,project_duration-start) if is_preview else project_duration
    if not 0<=start<project_duration or span<=0:raise UserError('Khoảng preview ngoài video.')
    return {'width':width,'height':height,'fps':str(fps),'start':start,'duration':span,'source_duration':project_duration,
            'audio_padding_seconds':max(0,project_duration-audio_meta['duration']),'tolerance_seconds':tolerance,'aspect_mode':config.aspect_mode}


def run_mux(video,audio,ass_path,output,options,config,settings,subtitle_report,background=None,check=lambda:None,progress=lambda value:None):
    if output.exists() or output.resolve() in {Path(video).resolve(),Path(audio).resolve(),ass_path.resolve()}:
        raise UserError('Output phải là staging mới; không ghi đè đầu vào/bản xuất hợp lệ.')
    if ass_path.parent.resolve()!=output.parent.resolve():raise UserError('ASS phải thuộc staging của job đang render.')
    caps=capabilities(settings)
    source_info=probe_streams(video,settings)
    source_video=next(s for s in source_info['streams'] if s.get('codec_type')=='video')
    copy_video=(config.subtitle_mode!='burn' and config.output_fps=='source' and options['start']==0 and source_video.get('codec_name')=='h264' and source_video.get('pix_fmt')=='yuv420p'
                and (source_video['width'],source_video['height'])==(options['width'],options['height']) and abs(float(source_info['format']['duration'])-options['duration'])<1e-6)
    if (not copy_video and not caps['video_encoder']) or not caps['aac']:raise UserError('FFmpeg cần encoder CPU H.264 (libx264/libopenh264) và AAC.')
    if config.subtitle_mode=='burn' and not caps['ass_filter']:raise UserError('FFmpeg thiếu libass; cài bản có filter ass/subtitles.')
    if config.subtitle_mode=='soft' and (not config.soft_compatibility_confirmed or not caps['mov_text']):raise UserError('Soft MP4 cần xác nhận chuyển ASS→mov_text; style nâng cao/player không bảo đảm. ASS sidecar vẫn giữ.')
    folder=output.parent;folder.mkdir(parents=True,exist_ok=True)
    fonts=folder/'fonts';fonts.mkdir(exist_ok=True)
    for index,path in enumerate(subtitle_report.get('fonts',[])):shutil.copyfile(path,fonts/f'font-{index}{Path(path).suffix}')
    args=[settings.ffmpeg_path,'-nostdin','-y','-hide_banner','-v','error','-threads','2']
    if options['start']:args+=['-ss',str(options['start'])]
    args+=['-protocol_whitelist','file','-i',str(Path(video).resolve())]
    if options['start']:args+=['-ss',str(options['start'])]
    args+=['-protocol_whitelist','file','-i',str(Path(audio).resolve())]
    next_input=2
    if background:
        if options['start']:args+=['-ss',str(options['start'])]
        args+=['-protocol_whitelist','file','-i',str(Path(background).resolve())];next_input+=1
    bridge=folder/'soft-bridge.srt'
    if config.subtitle_mode=='soft':
        soft_text_bridge(subtitle_report,bridge);args+=['-i',bridge.name]
    span=options['duration'];width,height=options['width'],options['height']
    vf=f"[0:v:0]setpts=PTS-STARTPTS,{geometry_filter(width,height,config.aspect_mode)},fps={options['fps']},tpad=stop_mode=clone:stop_duration={options['tolerance_seconds']},trim=duration={span}"
    if config.subtitle_mode=='burn':vf+=f",{caps['ass_filter']}=filename={ass_path.name}:fontsdir=fonts"
    vf+='[v]'
    audio_filter=audio_graph(span,config,background_index=2 if background else None)
    args+=['-filter_complex',audio_filter if copy_video else vf+';'+audio_filter,'-map','0:v:0' if copy_video else '[v]','-map','[a]']
    if config.subtitle_mode=='soft':args+=['-map',f'{next_input}:s:0','-c:s','mov_text','-metadata:s:s:0','language=vie','-disposition:s:0','default']
    encoder='copy' if copy_video else caps['video_encoder'];args+=['-c:v',encoder]
    if encoder=='libx264':
        preset,crf={'fast':('veryfast','26'),'balanced':('fast','21'),'high':('medium','18')}[config.quality]
        args+=['-preset',preset,'-crf',crf]
    elif not copy_video:args+=['-b:v',str(max(300000,round(width*height*float(Fraction(options['fps']))*.12)))]
    args+=['-pix_fmt','yuv420p','-threads','2','-c:a','aac','-b:a','192k','-ar','48000','-ac','1','-t',str(span),
           '-map_metadata','0','-metadata:s:a:0','language=vie','-metadata:s:v:0','rotate=0','-movflags','+faststart','-progress','progress.txt','-nostats',output.name]
    process=None;success=False
    try:
        with (folder/'mux.log').open('wb') as errors:
            process=subprocess.Popen(args,cwd=folder,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=errors,shell=False)
            deadline=time.monotonic()+settings.final_timeout_seconds
            while process.poll() is None:
                check()
                if time.monotonic()>deadline:raise UserError('Final render quá thời gian; thử preview/chất lượng nhanh.')
                status=folder/'progress.txt'
                if status.is_file():
                    try:
                        times=[line.split('=',1)[1] for line in status.read_text(errors='replace').splitlines() if line.startswith('out_time_us=')]
                        if times and times[-1]!='N/A':progress(min(.99,max(0,float(times[-1])/1e6/span)))
                    except (OSError,ValueError):pass
                time.sleep(.1)
        check()
        if process.returncode:raise UserError('FFmpeg final render thất bại. Kiểm tra libass/font/codec/dung lượng; log riêng được giữ để chẩn đoán.')
        success=True
        return {'video_encoder':encoder,'video_stream_copied':copy_video,'audio_source':'M3 approved dubbed audio only' if not background else 'M3 voice + validated separated background','command_uses_shortest':False}
    except OSError as exc:raise UserError('Không khởi động được FFmpeg final render.') from exc
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:process.wait(timeout=3)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        for font in fonts.glob('*'):font.unlink(missing_ok=True)
        fonts.rmdir()
        bridge.unlink(missing_ok=True)
        if not success:output.unlink(missing_ok=True)
