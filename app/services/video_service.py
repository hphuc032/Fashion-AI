"""Bounded FFprobe execution and strict metadata normalization."""
import json
import logging
import math
import subprocess
from fractions import Fraction
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from app.utils.validators import UserError

log = logging.getLogger("fashion_ai.video")


class VideoMetadata(BaseModel):
    duration: float = Field(gt=0, allow_inf_nan=False)
    width: int = Field(gt=0, le=16384)
    height: int = Field(gt=0, le=16384)
    fps: float = Field(gt=0, le=1000, allow_inf_nan=False)
    video_codec: str = Field(min_length=1, max_length=64)
    audio_codec: str | None = Field(default=None, max_length=64)
    aspect_ratio: str


def parse_metadata(data: dict, suffix: str) -> VideoMetadata:
    try:
        fmt = data["format"]
        containers = set(fmt["format_name"].split(","))
        expected = {"matroska"} if suffix == ".mkv" else {"mov", "mp4"}
        if not containers.intersection(expected):
            raise ValueError("container mismatch")
        streams = data["streams"]
        video = next(s for s in streams if s.get("codec_type") == "video"
                     and not s.get("disposition", {}).get("attached_pic", 0))
        audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
        fps = None
        for key in ("avg_frame_rate", "r_frame_rate"):
            try:
                candidate = float(Fraction(video.get(key, "0/0")))
                if math.isfinite(candidate) and candidate > 0:
                    fps = candidate
                    break
            except (ValueError, ZeroDivisionError, TypeError):
                continue
        width, height = int(video["width"]), int(video["height"])
        divisor = math.gcd(width, height)
        # Prefer display aspect ratio (anamorphic sources), falling back to pixel ratio.
        aspect = video.get("display_aspect_ratio")
        try:
            ratio = Fraction(str(aspect).replace(":", "/"))
            if ratio <= 0:
                raise ValueError()
            aspect = f"{ratio.numerator}:{ratio.denominator}"
        except (ValueError, ZeroDivisionError):
            aspect = f"{width // divisor}:{height // divisor}"
        duration = fmt.get("duration") or video.get("duration")
        return VideoMetadata(duration=duration, width=width, height=height, fps=fps,
                             video_codec=video["codec_name"],
                             audio_codec=audio.get("codec_name") if audio else None,
                             aspect_ratio=aspect)
    except (KeyError, ValueError, TypeError, AttributeError, StopIteration, ZeroDivisionError, ValidationError) as exc:
        raise UserError("Video không hợp lệ, định dạng không khớp hoặc metadata bị thiếu/hỏng.") from exc


def probe_video(path: Path, executable: str, suffix: str) -> VideoMetadata:
    try:
        result = subprocess.run(
            [executable, "-v", "error", "-protocol_whitelist", "file", "-show_format",
             "-show_streams", "-of", "json", str(path.resolve())],
            shell=False, check=True, capture_output=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError as exc:
        log.warning("ffprobe_missing")
        raise UserError("Không tìm thấy FFprobe. Hãy cài FFmpeg hoặc cấu hình FFPROBE_PATH trong .env.") from exc
    except subprocess.TimeoutExpired as exc:
        log.warning("ffprobe_timeout")
        raise UserError("Kiểm tra video quá 30 giây. Hãy thử tệp ngắn hơn.") from exc
    except (subprocess.CalledProcessError, OSError) as exc:
        log.warning("ffprobe_failed type=%s", type(exc).__name__)
        raise UserError("FFprobe không đọc được video. Tệp có thể bị hỏng hoặc không được hỗ trợ.") from exc
    try:
        return parse_metadata(json.loads(result.stdout), suffix)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise UserError("FFprobe trả về metadata không hợp lệ.") from exc
