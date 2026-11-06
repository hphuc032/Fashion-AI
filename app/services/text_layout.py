"""Unicode layout constrained to a rectangle, with verified system glyphs."""
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from typing import Literal

from app.utils.validators import UserError


class TextStyle(BaseModel):
    font: str = 'Arial'
    size: int = Field(default=32,ge=12,le=200)
    minimum_size: int = Field(default=12,ge=8,le=100)
    color: str = '#ffffff'
    outline_color: str = '#000000'
    outline_width: int = Field(default=2,ge=0,le=10)
    shadow: bool = False
    background: str | None = None
    align: Literal['left','center','right'] = 'center'
    line_spacing: int = Field(default=4,ge=0,le=30)
    safe_margin: int = Field(default=3,ge=0,le=100)


@lru_cache(maxsize=1)
def available_fonts():
    fonts = {}
    root = Path(os.environ.get('WINDIR','')) / 'Fonts'
    for name,filename in [('Arial','arial.ttf'),('Segoe UI','segoeui.ttf')]:
        if (root/filename).is_file():
            fonts[name]=root/filename
    try:
        fonts['DejaVu Sans']=Path(ImageFont.truetype('DejaVuSans.ttf',12).path)
    except OSError:
        pass
    return fonts


@lru_cache(maxsize=16)
def glyphs(path):
    from fontTools.ttLib import TTFont
    with TTFont(path,lazy=True) as font:
        return frozenset((font.getBestCmap() or {}).keys())


def load_font(name,text,size):
    fonts=available_fonts()
    if not fonts:
        raise UserError('Không tìm thấy font hỗ trợ. Cài Arial/Segoe UI hoặc DejaVu Sans trên hệ thống.')
    path=fonts.get(name,next(iter(fonts.values())))
    if any(ord(c) not in glyphs(str(path)) for c in text if not c.isspace()):
        raise UserError('Font thiếu glyph của bản dịch. Chọn font khác hoặc sửa ký tự; không xuất chữ bị mất dấu.')
    return ImageFont.truetype(str(path),size)


def wrap_text(text,font,width,stroke):
    lines=[]
    for paragraph in text.split('\n'):
        line=''
        for word in paragraph.split():
            candidate=f'{line} {word}'.strip()
            if font.getlength(candidate)+stroke*2 <= width:
                line=candidate
                continue
            if line:
                lines.append(line)
                line=''
            for char in word:
                if font.getlength(line+char)+stroke*2 > width and line:
                    lines.append(line)
                    line=''
                line+=char
        lines.append(line)
    return '\n'.join(lines)


def text_layer(text,box,style:TextStyle):
    _,_,width,height=box
    margin=style.safe_margin
    usable=(width-2*margin,height-2*margin)
    if min(usable)<=0 or not text.strip():
        raise UserError('Vùng đặt chữ rỗng hoặc quá nhỏ.')
    for color in [style.color,style.outline_color,style.background]:
        if color is not None:
            try: ImageColor.getrgb(color)
            except ValueError as exc: raise UserError('Màu chữ/nền không hợp lệ.') from exc
    canvas=Image.new('RGBA',(width,height),(0,0,0,0))
    draw=ImageDraw.Draw(canvas)
    for size in range(style.size,style.minimum_size-1,-1):
        font=load_font(style.font,text,size)
        wrapped=wrap_text(text,font,usable[0],style.outline_width)
        bounds=draw.multiline_textbbox((0,0),wrapped,font=font,spacing=style.line_spacing,stroke_width=style.outline_width,align=style.align)
        w,h=bounds[2]-bounds[0],bounds[3]-bounds[1]
        if w<=usable[0] and h<=usable[1]:
            if style.background:
                draw.rectangle((0,0,width,height),fill=style.background)
            left=margin if style.align=='left' else width-margin-w if style.align=='right' else (width-w)/2
            position=(left-bounds[0],(height-h)/2-bounds[1])
            if style.shadow:
                draw.multiline_text((position[0]+2,position[1]+2),wrapped,font=font,fill='#000000',spacing=style.line_spacing,align=style.align)
            draw.multiline_text(position,wrapped,font=font,fill=style.color,stroke_fill=style.outline_color,
                                stroke_width=style.outline_width,spacing=style.line_spacing,align=style.align)
            return canvas,{'font_size':size,'lines':wrapped.count('\n')+1,'wrapped':wrapped}
    raise UserError('Bản dịch không vừa vùng chữ ở cỡ tối thiểu. Tăng vùng hoặc chỉnh nội dung; không cắt bớt chữ tự động.')
