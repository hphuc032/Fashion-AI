from typing import Literal
from pydantic import BaseModel,Field


class SubtitleStyle(BaseModel):
    font:str='Arial'
    font_size:int=Field(default=48,ge=12,le=120)
    primary_color:str='#ffffff'
    outline_color:str='#000000'
    outline_width:float=Field(default=2.0,ge=0,le=8,allow_inf_nan=False)
    shadow:float=Field(default=1.0,ge=0,le=5,allow_inf_nan=False)
    background:bool=False
    background_color:str='#101820'
    alignment:int=Field(default=2,ge=1,le=9)
    horizontal_margin:float=Field(default=.06,ge=.01,le=.3,allow_inf_nan=False)
    vertical_margin:float=Field(default=.10,ge=.01,le=.3,allow_inf_nan=False)
    vertical_position:float|None=Field(default=None,ge=.05,le=.95,allow_inf_nan=False)
    line_spacing:int=Field(default=4,ge=0,le=30)
    max_lines:int=Field(default=2,ge=1,le=2)


class FinalRenderConfig(BaseModel):
    preset:Literal['original','tiktok','compact']='original'
    tiktok_resolution:Literal['1080x1920','720x1280']='1080x1920'
    aspect_mode:Literal['fit','crop']='fit'
    crop_confirmed:bool=False
    quality:Literal['fast','balanced','high']='balanced'
    output_fps:Literal['source','24','25','30','60']='source'
    subtitle_mode:Literal['burn','soft','none']='burn'
    soft_compatibility_confirmed:bool=False
    style:SubtitleStyle=Field(default_factory=SubtitleStyle)
    speaker_styles:dict[str,SubtitleStyle]=Field(default_factory=dict)
    readability_confirmed:bool=False
    voice_volume:float=Field(default=1.0,ge=0,le=1.5,allow_inf_nan=False)
    background_path:str|None=None
    background_volume:float=Field(default=.2,ge=0,le=1,allow_inf_nan=False)
    preview_start:float=Field(default=0.,ge=0,allow_inf_nan=False)
    preview_seconds:float=Field(default=5.,gt=0,le=30,allow_inf_nan=False)


def dimensions(width,height,config,is_preview=False):
    if config.preset=='tiktok':result=tuple(map(int,config.tiktok_resolution.split('x')))
    elif config.preset=='compact':
        ratio=min(1,640/max(width,height));result=(max(2,round(width*ratio/2)*2),max(2,round(height*ratio/2)*2))
    else:result=(width,height)
    if is_preview:
        ratio=min(1,640/max(result));result=tuple(max(2,round(v*ratio/2)*2) for v in result)
    return result
