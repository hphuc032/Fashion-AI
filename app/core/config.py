"""Environment configuration; relative paths are anchored to project root."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseModel):
    app_name: str = "Fashion AI Localizer"
    app_env: str = "local"
    storage_root: Path = ROOT / "storage"
    database_url: str = "sqlite:///./storage/fashion_ai.db"
    max_upload_size_mb: int = Field(default=500, gt=0)
    max_video_seconds: float = Field(default=180, gt=0)
    ffmpeg_path: str = "ffmpeg"
    ffprobe_path: str = "ffprobe"
    log_level: str = "INFO"
    ocr_sample_interval_seconds: float = Field(default=1.0, ge=0.1, le=60, allow_inf_nan=False)
    ocr_max_frames: int = Field(default=300, ge=1, le=1000)
    ocr_max_side: int = Field(default=1280, ge=320, le=1920)
    ocr_max_source_pixels: int = Field(default=16777216, ge=1000000, le=64000000)
    ocr_enable_gpu: bool = False
    ocr_cpu_threads: int = Field(default=2, ge=1, le=8)
    ocr_min_confidence: float = Field(default=0.4, ge=0, le=1, allow_inf_nan=False)
    ocr_similarity_threshold: float = Field(default=0.94, ge=0.8, le=1, allow_inf_nan=False)
    ocr_iou_threshold: float = Field(default=0.3, gt=0, le=1, allow_inf_nan=False)
    ocr_models_dir: Path | None = None
    job_timeout_seconds: int = Field(default=1800, ge=30, le=7200)
    translation_provider: str = "manual"
    translation_timeout_seconds: int = Field(default=60, ge=1, le=300)
    translation_retries: int = Field(default=2, ge=0, le=4)
    translation_max_characters: int = Field(default=10000, ge=100, le=100000)
    argos_models_dir: Path | None = None
    render_timeout_seconds: int = Field(default=1800,ge=30,le=7200)
    render_max_frames: int = Field(default=12000,ge=1,le=100000)
    render_max_fps: int = Field(default=60,ge=1,le=240)
    preview_cache_entries: int = Field(default=12,ge=1,le=100)
    asr_provider: str = 'funasr'
    asr_model_dir: Path = ROOT / 'storage/models/funasr'
    funasr_vad_dir: Path | None = None
    funasr_punc_dir: Path | None = None
    funasr_speaker_dir: Path | None = None
    whisper_model_dir: Path = ROOT / 'storage/models/whisper-base'
    asr_language: str = 'zh'
    asr_device: str = 'cpu'
    asr_chunk_seconds: float = Field(default=30.0,ge=5,le=120)
    asr_overlap_seconds: float = Field(default=2.0,ge=0,le=4)
    tts_provider: str = 'local'
    tts_model_dir: Path = ROOT / 'storage/models/vits-piper-vi_VN-vais1000-medium'
    dub_timeout_seconds: int = Field(default=1800,ge=30,le=7200)
    dub_max_segments: int = Field(default=300,ge=1,le=1000)
    sync_min_factor: float = Field(default=.85,ge=.5,le=1)
    sync_max_factor: float = Field(default=1.2,ge=1,le=1.5)
    auto_review_enabled: bool = True
    auto_review_ocr_high_threshold: float = Field(default=.95, ge=0, le=1)
    auto_review_ocr_low_threshold: float = Field(default=.80, ge=0, le=1)
    auto_review_max_batch_size: int = Field(default=100, ge=1, le=100)
    auto_review_require_translation_check: bool = True

    @model_validator(mode="after")
    def review_thresholds(self):
        if self.auto_review_ocr_low_threshold > self.auto_review_ocr_high_threshold:
            raise ValueError("Ngưỡng OCR thấp phải nhỏ hơn ngưỡng cao.")
        return self

    @property
    def max_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    values = {key: os.environ[key.upper()] for key in Settings.model_fields
              if key.upper() in os.environ}
    for key in ("ocr_models_dir", "argos_models_dir",'funasr_vad_dir','funasr_punc_dir','funasr_speaker_dir'):
        if not values.get(key):
            values.pop(key, None)
    settings = Settings(**values)
    for key in ('asr_model_dir','whisper_model_dir','tts_model_dir'):
        setattr(settings,key,(ROOT/getattr(settings,key)).resolve())
    for key in ('funasr_vad_dir','funasr_punc_dir','funasr_speaker_dir'):
        if getattr(settings,key):setattr(settings,key,(ROOT/getattr(settings,key)).resolve())
    settings.storage_root = (ROOT / settings.storage_root).resolve()
    settings.ocr_models_dir = (ROOT / settings.ocr_models_dir).resolve() if settings.ocr_models_dir else settings.storage_root / "models" / "paddle"
    settings.argos_models_dir = (ROOT / settings.argos_models_dir).resolve() if settings.argos_models_dir else settings.storage_root / "models" / "argos"
    for key in ("ffmpeg_path", "ffprobe_path"):
        value = getattr(settings, key)
        if "/" in value or "\\" in value:
            setattr(settings, key, str((ROOT / value).resolve()))
    url = make_url(settings.database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("DATABASE_URL phải trỏ đến một tệp SQLite.")
    db_path = (ROOT / url.database).resolve()
    settings.database_url = url.set(database=str(db_path)).render_as_string(hide_password=False)
    return settings
