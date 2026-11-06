"""Time-aware region masking and identical preview/render composition."""
from typing import Literal

import cv2
import numpy as np
from PIL import Image,ImageColor
from pydantic import BaseModel,Field

from app.services.text_layout import TextStyle,text_layer
from app.services.inpainting_provider import InpaintingProvider,OpenCVInpainting
from app.utils.validators import UserError


class ReplacementSettings(BaseModel):
    removal_mode: Literal['solid','blur','inpaint','overlay'] = 'solid'
    box_override: list[int] | None = None
    text_box: list[int] | None = None
    fixed_box: bool = False
    padding: int = Field(default=4,ge=0,le=100)
    opacity: float = Field(default=1.0,ge=0,le=1,allow_inf_nan=False)
    mask_color: str = '#182235'
    inpaint_radius: int = Field(default=3,ge=1,le=15)
    style: TextStyle = Field(default_factory=TextStyle)
    text_override: str | None = Field(default=None,max_length=2000)
    override_reviewed: bool = False
    allow_pending: bool = False
    acknowledge_tracking: bool = False
    start_time: float | None = Field(default=None,ge=0,allow_inf_nan=False)
    end_time: float | None = Field(default=None,gt=0,allow_inf_nan=False)


def valid_box(box,width,height):
    if len(box)!=4 or any(not isinstance(v,(int,float)) or not np.isfinite(v) or int(v)!=v for v in box):
        raise UserError('Khung chữ cần [x,y,rộng,cao] nguyên hợp lệ.')
    x,y,w,h=map(int,box)
    if x<0 or y<0 or w<=0 or h<=0 or x+w>width or y+h>height:
        raise UserError('Khung chữ vượt kích thước video hoặc có diện tích rỗng.')
    return [x,y,w,h]


def region_at(item,t,width,height):
    config=ReplacementSettings.model_validate(item['settings'])
    if config.box_override is not None:
        return valid_box(config.box_override,width,height),False
    samples=item.get('detections',[])
    if config.fixed_box:
        return valid_box(item['box'],width,height),False
    ordered=sorted(samples,key=lambda d:d['time'])
    if not ordered:
        return valid_box(item['box'],width,height),True
    before=max((s for s in ordered if s['time']<=t),key=lambda d:d['time'],default=ordered[0])
    after=min((s for s in ordered if s['time']>=t),key=lambda d:d['time'],default=ordered[-1])
    gap=after['time']-before['time']
    limit=item.get('tracking_gap',1.1)
    uncertain=abs(t-before['time'])>limit or gap>limit or min(before.get('confidence',0),after.get('confidence',0))<.8
    if gap>0 and gap<=limit:
        weight=(t-before['time'])/gap
        box=[round(a+(b-a)*weight) for a,b in zip(before['box'],after['box'])]
    else:
        box=before['box']
    return valid_box(box,width,height),uncertain


def overlaps(a,b):
    return min(a[0]+a[2],b[0]+b[2])>max(a[0],b[0]) and min(a[1]+a[3],b[1]+b[3])>max(a[1],b[1])


def compose(frame,t,items,strict=True,inpainting_provider: InpaintingProvider | None=None):
    height,width=frame.shape[:2]
    layers=[]
    warnings=[]
    removal=[]
    for item in items:
        if not item['start']<=t<item['end']:
            continue
        config=ReplacementSettings.model_validate(item['settings'])
        box,uncertain=region_at(item,t,width,height)
        if uncertain:
            warnings.append('Theo dõi vùng chữ chưa chắc chắn; cần chỉnh tay hoặc xác nhận kiểm tra.')
            if strict and not config.acknowledge_tracking:
                raise UserError(warnings[-1])
        target=valid_box(config.text_box or box,width,height)
        if any(overlaps(target,previous[0]) for previous in layers):
            raise UserError('Các bản dịch đang chồng lấn. Điều chỉnh vị trí trước khi xuất.')
        if config.text_override is not None and not config.override_reviewed:
            raise UserError('Bản sửa riêng cho render chưa được xác nhận kiểm tra.')
        layer,_=text_layer(config.text_override if config.text_override is not None else item['text'],target,config.style)
        layers.append((target,layer))
        x,y,w,h=box
        padded=[max(0,x-config.padding),max(0,y-config.padding),min(width,x+w+config.padding),min(height,y+h+config.padding)]
        removal.append((padded,config))
    result=frame.copy()
    # Always sample removal pixels from the unchanged frame; overlapping masks do
    # not blur/inpaint translated glyphs from earlier segments.
    for (x1,y1,x2,y2),config in removal:
        if config.removal_mode=='overlay':
            continue
        original=frame[y1:y2,x1:x2]
        if original.size==0:
            raise UserError('Mask rỗng.')
        if config.removal_mode=='solid':
            try: color=ImageColor.getrgb(config.mask_color)
            except ValueError as exc: raise UserError('Màu mask không hợp lệ.') from exc
            changed=np.full_like(original,color[::-1])
        elif config.removal_mode=='blur':
            changed=cv2.GaussianBlur(original,(0,0),sigmaX=max(3,min(original.shape[:2])/3))
        else:
            # Inpaint a local ROI plus context to avoid full-frame work.
            pad=12
            ax,ay,bx,by=max(0,x1-pad),max(0,y1-pad),min(width,x2+pad),min(height,y2+pad)
            roi=frame[ay:by,ax:bx]
            mask=np.zeros(roi.shape[:2],np.uint8)
            mask[y1-ay:y2-ay,x1-ax:x2-ax]=255
            restored=(inpainting_provider or OpenCVInpainting()).apply(roi,mask,config.inpaint_radius)
            if restored.shape!=roi.shape or restored.dtype!=roi.dtype:
                raise UserError('Provider inpaint trả về frame không hợp lệ.')
            changed=restored[y1-ay:y2-ay,x1-ax:x2-ax]
            warnings.append('Inpaint cơ bản có thể tạo vệt trên nền phức tạp; cần xem trước.')
        result[y1:y2,x1:x2]=cv2.addWeighted(original,1-config.opacity,changed,config.opacity,0)
    if not layers:
        return result,warnings
    image=Image.fromarray(cv2.cvtColor(result,cv2.COLOR_BGR2RGB)).convert('RGBA')
    for (x,y,w,h),layer in layers:
        image.alpha_composite(layer,(x,y))
    return cv2.cvtColor(np.asarray(image.convert('RGB')),cv2.COLOR_RGB2BGR),warnings
