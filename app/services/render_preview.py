import hashlib
import json

import cv2
from PIL import Image

from app.services.frame_extractor import extract_frames,source_hash
from app.services.ocr_repository import project_source
from app.services.replacement_repository import snapshot_items
from app.services.storage_service import resolve_media
from app.services.text_compositor import compose


def preview_frame(sessions,settings,project_id,timestamp):
    project,path=project_source(sessions,project_id,settings)
    items=snapshot_items(sessions,project_id)
    # Same source display resolution as final composition; pixel cap applies.
    options=settings.model_copy(update={'ocr_max_side':max(project.width,project.height)})
    sample=next(extract_frames(path,project_id,project.duration,options,timestamps=[timestamp]))
    image=cv2.imread(str(sample.path))
    key=hashlib.sha256(json.dumps([source_hash(path),timestamp,items],sort_keys=True).encode()).hexdigest()
    folder=resolve_media(settings.storage_root,f'projects/{project_id}/preview/m2')
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{key}.png'
    output,warnings=compose(image,timestamp,items,strict=False)
    if not target.exists():
        temporary=target.with_suffix('.tmp.png')
        cv2.imwrite(str(temporary),output)
        temporary.replace(target)
    cached=sorted(folder.glob('*.png'),key=lambda p:p.stat().st_mtime)
    for old in cached[:-settings.preview_cache_entries]:
        if old!=target: old.unlink(missing_ok=True)
    return Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB)),Image.fromarray(cv2.cvtColor(output,cv2.COLOR_BGR2RGB)),warnings
