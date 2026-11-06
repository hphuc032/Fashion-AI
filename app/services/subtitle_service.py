"""UTF-8 ASS from approved speech; no OCR text or invented word alignment."""
import math
from html import escape
from decimal import Decimal,ROUND_HALF_UP
from pathlib import Path
from PIL import ImageColor
from app.services.text_layout import available_fonts,load_font,wrap_text
from app.services.final_render_config import SubtitleStyle
from app.utils.validators import UserError


def ass_time(seconds):
    if not math.isfinite(seconds) or seconds<0:raise UserError('Timestamp phụ đề không hợp lệ.')
    cs=int((Decimal(str(seconds))*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    hours,rest=divmod(cs,360000);minutes,rest=divmod(rest,6000);secs,centis=divmod(rest,100)
    return f'{hours}:{minutes:02}:{secs:02}.{centis:02}'


def escape_ass(text):
    # libass supports escaped braces; WORD JOINER prevents literal backslash+N/n/h
    # becoming an ASS escape while keeping the visible approved text unchanged.
    text=text.replace('\r\n','\n').replace('\r','\n')
    if any(ord(c)<32 and c not in '\n\t' for c in text):raise UserError('Lời chứa ký tự điều khiển không hỗ trợ.')
    return ''.join('\\\u2060' if c=='\\' else '\\{' if c=='{' else '\\}' if c=='}' else r'\N' if c=='\n' else ' ' if c=='\t' else c for c in text)


def ass_color(color,alpha=0):
    try:r,g,b=ImageColor.getrgb(color)
    except (ValueError,TypeError) as exc:raise UserError('Màu ASS không hợp lệ; dùng màu RGB.') from exc
    return f'&H{alpha:02X}{b:02X}{g:02X}{r:02X}'


def layout_caption(text,style,width,height):
    fonts=available_fonts()
    if not fonts:raise UserError('Không có font Việt. Cài Arial/Segoe UI/DejaVu Sans.')
    name=style.font if style.font in fonts else next(iter(fonts))
    scale=width/1080
    target=max(10,round(style.font_size*scale))
    margin=max(2,round(width*style.horizontal_margin))
    for size in range(target,max(9,round(20*scale))-1,-1):
        font=load_font(name,text,size)
        wrapped=wrap_text(text,font,width-2*margin,max(1,round(style.outline_width*scale)))
        lines=wrapped.split('\n')
        w=max(font.getlength(line) for line in lines)+2*style.outline_width*scale
        line_height=sum(font.getmetrics())+round(style.line_spacing*scale)
        total=line_height*len(lines)
        if len(lines)<=style.max_lines and w<=width-2*margin and total<height*(1-2*style.vertical_margin):
            family=font.getname()[0]
            if any(c in family for c in ',\r\n{}\\'):raise UserError('Tên font không an toàn cho ASS.')
            return {'font':name,'family':family,'font_path':str(fonts[name]),'font_size':size,'lines':lines,'line_height':line_height,'width':math.ceil(w),'height':total,'margin':margin}
    raise UserError('Phụ đề quá dài để vừa tối đa2 dòng. Chỉnh câu/style/vùng hiển thị; không tự cắt lời.')


def generate_ass(segments,path,width,height,duration,style=None,speaker_styles=None,window=None,readability_confirmed=False,soft=False):
    style=style or SubtitleStyle();speaker_styles=speaker_styles or {}
    if len(segments)>1000:raise UserError('Quá nhiều sự kiện phụ đề; giới hạn1000 đoạn.')
    if width<=0 or height<=0 or not math.isfinite(duration) or duration<=0:raise UserError('Kích thước/timeline ASS không hợp lệ.')
    begin,finish=window or (0.,duration)
    if not 0<=begin<finish<=duration:raise UserError('Khoảng preview phụ đề vượt timeline.')
    header=['[Script Info]','ScriptType: v4.00+',f'PlayResX: {width}',f'PlayResY: {height}','WrapStyle: 2','ScaledBorderAndShadow: yes','',
            '[V4+ Styles]','Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding']
    events=[];report=[];warnings=[];font_paths=set();active=[];seen=set()
    for index,s in enumerate(sorted(segments,key=lambda x:(x['start_time'],x['end_time'],x['id']))):
        start,end=float(s['start_time']),float(s['end_time']);text=s['translated_text'].strip()
        if s.get('review_status','approved')!='approved' or not text or len(text)>2000 or s['id'] in seen:raise UserError('Phụ đề chỉ dùng lời Việt đã duyệt, không trống/trùng.')
        seen.add(s['id'])
        if not all(math.isfinite(t) for t in (start,end)) or not 0<=start<end<=duration:raise UserError('Phụ đề ngoài timeline hoặc timestamp sai.')
        if end<=begin or start>=finish:continue
        if end-start<.3 or len(text)/(end-start)>30:
            warnings.append(f'Lời {index+1}: thời gian đọc ngắn/nhanh; chỉnh lời/timing hoặc xác nhận đã xem.')
            if not readability_confirmed:raise UserError(warnings[-1])
        cfg=speaker_styles.get(s.get('speaker_id'),style)
        if isinstance(cfg,dict):cfg=SubtitleStyle.model_validate(cfg)
        layout=layout_caption(text,cfg,width,height);font_paths.add(layout['font_path'])
        size=layout['font_size'];stroke=cfg.outline_width*width/1080;shadow=cfg.shadow*width/1080
        style_name=f'S{index}'
        header.append(f"Style: {style_name},{layout['family']},{size},{ass_color(cfg.primary_color)},{ass_color(cfg.primary_color)},{ass_color(cfg.outline_color)},{ass_color(cfg.background_color,120)},0,0,0,0,100,100,0,0,1,{stroke:.2f},{shadow:.2f},{cfg.alignment},{layout['margin']},{layout['margin']},{round(height*cfg.vertical_margin)},1")
        col=(cfg.alignment-1)%3
        x=layout['margin'] if col==0 else width-layout['margin'] if col==2 else width/2
        box_x=x if col==0 else x-layout['width'] if col==2 else x-layout['width']/2
        row=(cfg.alignment-1)//3
        y=height*(cfg.vertical_position if cfg.vertical_position is not None else 1-cfg.vertical_margin if row==0 else .5 if row==1 else cfg.vertical_margin)
        top=y-layout['height'] if row==0 else y-layout['height']/2 if row==1 else y
        active=[a for a in active if a['end']>start]
        while any(min(top+layout['height'],a['bottom'])>max(top,a['top']) and min(box_x+layout['width'],a['right'])>max(box_x,a['left']) for a in active):
            top-=layout['height']+max(4,round(size*.3))
        if top<0 or top+layout['height']>height:raise UserError('Phụ đề chồng nhau không còn vùng an toàn; chỉnh speaker/style/vị trí.')
        active.append({'end':end,'top':top,'bottom':top+layout['height'],'left':box_x,'right':box_x+layout['width']})
        a,b=max(start,begin)-begin,min(end,finish)-begin
        ta,tb=ass_time(a),ass_time(math.floor(b*100+1e-7)/100)
        if ta==tb:raise UserError('Lời ngắn hơn độ chính xác centisecond của ASS; chỉnh timeline.')
        if cfg.background and not soft:
            w,h=layout['width']+8,layout['height']+4
            tags=r'{\an7\pos('+f'{max(0,box_x-4):.1f},{max(0,top-2):.1f}'+r')\p1\bord0\shad0\1c'+ass_color(cfg.background_color)+r'&\1a&H60&}'
            events.append(f'Dialogue: 0,{ta},{tb},{style_name},,0,0,0,,{tags}m 0 0 l {w} 0 {w} {h} 0 {h}')
        if soft:
            lines=['\n'.join(layout['lines'])]
        else:lines=layout['lines']
        for line_index,line in enumerate(lines):
            anchor=7+col
            tags='{\\an'+str(anchor)+'\\pos('+f'{x:.1f},{top+line_index*layout["line_height"]:.1f}'+')}'
            events.append(f'Dialogue: 1,{ta},{tb},{style_name},,0,0,0,,{tags}{escape_ass(line)}')
        report.append({'id':s['id'],'speaker':s.get('speaker_id'),'source_start':start,'source_end':end,'start':a,'end':b,'text':text,'font':layout['family'],'font_size':size,
                       'wrapped':'\n'.join(layout['lines']),'ass_start':ta,'ass_end':tb,
                       'bbox':[max(0,int(box_x-size/2)),max(0,int(top-size/2)),min(width,int(box_x+layout['width']+size/2)),min(height,int(top+layout['height']+size/2))]})
    contents='\n'.join(header+['','[Events]','Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text',*events])+'\n'
    Path(path).write_text(contents,encoding='utf-8')
    return {'events':report,'dialogue_count':len(events),'warnings':warnings,'fonts':sorted(font_paths),'timing_tolerance_seconds':.01,'language':'vie','window':[begin,finish]}


def soft_text_bridge(report,path):
    """Portable plain-text bridge for mov_text; ASS style sidecar is retained.

    FFmpeg's ASS→mov_text converter preserves literal ASS brace escapes. SRT's
    plaintext decoder avoids leaking those escapes into the displayed track.
    All timing/wrapping comes from the already generated ASS report.
    """
    def stamp(value):
        hours,minutes,seconds=value.split(':');seconds,centis=seconds.split('.')
        return f'{int(hours):02}:{minutes}:{seconds},{centis}0'
    chunks=[]
    for i,event in enumerate(report['events']):
        text=escape(event['wrapped'].replace('\\','\\\u2060'),quote=False)
        chunks.append(f"{i+1}\n{stamp(event['ass_start'])} --> {stamp(event['ass_end'])}\n{text}\n")
    Path(path).write_text('\n'.join(chunks),encoding='utf-8')
