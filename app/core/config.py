"""Environment configuration; relative paths are anchored to project root."""
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field
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

    @property
    def max_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)
    values = {key: os.environ[key.upper()] for key in Settings.model_fields
              if key.upper() in os.environ}
    settings = Settings(**values)
    settings.storage_root = (ROOT / settings.storage_root).resolve()
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
