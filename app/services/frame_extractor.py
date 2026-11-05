"""Incremental, bounded source-time sampling; original media is read-only."""
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from app.core.config import Settings
from app.services.storage_service import resolve_media
from app.utils.validators import UserError


class Cancelled(UserError):
    pass


def sample_times(duration: float, interval: float, maximum: int) -> list[float]:
    if not math.isfinite(duration) or duration <= 0 or not math.isfinite(interval) or interval < 0.1 or maximum < 1:
        raise UserError("Thời lượng hoặc cấu hình lấy mẫu không hợp lệ.")
    return [round(i * interval, 6) for i in range(min(maximum, math.ceil(duration / interval)))
            if i * interval < duration]


def source_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class SampledFrame:
    index: int  # Sample ordinal, not a guessed original frame number for VFR video.
    timestamp: float  # Requested source timestamp; actual image is next available decoded frame.
    path: Path
    original_width: int
    original_height: int
    width: int
    height: int


def display_dimensions(path: Path, settings: Settings) -> tuple[int, int]:
    try:
        result = subprocess.run(
            [settings.ffprobe_path, "-v", "error", "-protocol_whitelist", "file", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:stream_side_data=rotation", "-of", "json", str(path)],
            shell=False, check=True, capture_output=True, timeout=30,
        )
        stream = json.loads(result.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        rotation = next((float(s["rotation"]) for s in stream.get("side_data_list", []) if "rotation" in s), 0)
        if int(abs(rotation)) % 180 == 90:
            width, height = height, width
        if not 0 < width <= 16384 or not 0 < height <= 16384:
            raise ValueError()
        return width, height
    except (OSError, subprocess.SubprocessError, KeyError, ValueError, IndexError, TypeError) as exc:
        raise UserError("Không đọc được kích thước video. Kiểm tra FFprobe và tệp gốc.") from exc


def extract_frames(path: Path, project_id: str, duration: float, settings: Settings,
                   check_cancel: Callable[[], None] = lambda: None, timestamps: list[float] | None = None) -> Iterator[SampledFrame]:
    import cv2

    root = settings.storage_root.resolve()
    path = resolve_media(root, str(path))
    project_root = resolve_media(root, f"projects/{project_id}")
    if not path.is_relative_to(project_root / "source") or not path.is_file():
        raise UserError("Chỉ xử lý video gốc trong kho dự án.")
    check_cancel()
    fingerprint = source_hash(path)
    original_width, original_height = display_dimensions(path, settings)
    if original_width * original_height > settings.ocr_max_source_pixels:
        raise UserError("Độ phân giải video vượt giới hạn OCR. Hãy nhập bản có độ phân giải thấp hơn.")
    folder = resolve_media(root, str(project_root / "frames" / f"{fingerprint}-v1-{settings.ocr_max_side}"))
    folder.mkdir(parents=True, exist_ok=True)
    times = sample_times(duration, settings.ocr_sample_interval_seconds, settings.ocr_max_frames) if timestamps is None else timestamps
    if len(times) > settings.ocr_max_frames or any(not math.isfinite(t) or not 0 <= t < duration for t in times):
        raise UserError("Mốc khung hình không hợp lệ.")
    for index, timestamp in enumerate(times):
        check_cancel()
        target = folder / f"{round(timestamp * 1_000_000):012d}.png"
        image = cv2.imread(str(target)) if target.is_file() else None
        if image is not None and (max(image.shape[:2]) > settings.ocr_max_side or min(image.shape[:2]) < 1):
            image = None
        if image is None:
            partial = target.with_suffix(".tmp.png")
            try:
                subprocess.run(
                    [settings.ffmpeg_path, "-nostdin", "-y", "-v", "error", "-threads", "1", "-ss", str(timestamp),
                     "-protocol_whitelist", "file", "-i", str(path), "-frames:v", "1", "-an", "-vf",
                     f"scale=w='min(iw,{settings.ocr_max_side})':h='min(ih,{settings.ocr_max_side})':force_original_aspect_ratio=decrease",
                     "-threads", "1", str(partial)], shell=False, check=True, capture_output=True, timeout=30,
                )
                image = cv2.imread(str(partial)) if partial.is_file() else None
                if image is None or image.size == 0 or max(image.shape[:2]) > settings.ocr_max_side:
                    raise UserError("Không trích xuất được khung hình hợp lệ.")
                partial.replace(target)
            except (OSError, subprocess.SubprocessError) as exc:
                raise UserError("Không trích xuất được khung hình. Kiểm tra FFmpeg hoặc video bị hỏng.") from exc
            finally:
                partial.unlink(missing_ok=True)
        check_cancel()
        height, width = image.shape[:2]
        yield SampledFrame(index, timestamp, target, original_width, original_height, width, height)
