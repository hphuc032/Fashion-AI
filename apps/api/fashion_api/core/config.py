"""Read-only profile configuration: validation never creates or opens a database."""
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WebConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: Path
    runtime_dir: Path
    repository: Path
    database_path: Path | None = None
    ffmpeg: str = "ffmpeg"
    ffprobe: str = "ffprobe"
    frontend_origin: str = "http://127.0.0.1:3000"
    backend_host: str = "127.0.0.1:8000"
    bootstrap_ttl: int = Field(default=90, ge=1, le=120)
    session_ttl: int = Field(default=3600, ge=1, le=86400)

    @model_validator(mode="after")
    def validate_profile(self):
        if self.frontend_origin != "http://127.0.0.1:3000" or self.backend_host != "127.0.0.1:8000":
            raise ValueError("W1 requires the fixed loopback origins")
        for p in (self.profile, self.runtime_dir, self.repository, self.database_path):
            if p is not None and not p.is_absolute():
                raise ValueError("Profile paths must be absolute")
            if p is not None and str(p).startswith(("\\\\", "//")):
                raise ValueError("Network profiles are not supported")
        profile, runtime, repo = (p.resolve() for p in (self.profile, self.runtime_dir, self.repository))
        if profile == Path(profile.anchor) or runtime == Path(runtime.anchor):
            raise ValueError("A filesystem root is not a profile")
        if profile.is_relative_to(repo) or repo.is_relative_to(profile):
            raise ValueError("Profile must not overlap the source repository")
        if runtime == profile or not runtime.is_relative_to(profile):
            raise ValueError("Runtime metadata must be a separate child of the profile")
        for root in (profile, runtime):
            for parent in (root, *root.parents):
                reparse = parent.exists() and bool(getattr(parent.lstat(), "st_file_attributes", 0) & 0x400)
                if parent.is_symlink() or reparse:
                    raise ValueError("Profile must not traverse filesystem links")
            if root.exists() and not root.is_dir():
                raise ValueError("Profile location must be a directory")
        if self.database_path:
            db = self.database_path.resolve()
            if db.is_relative_to(runtime) or runtime.is_relative_to(db):
                raise ValueError("Database must not overlap runtime metadata")
        for executable in (self.ffmpeg, self.ffprobe):
            if not executable.strip() or any(c in executable for c in "\r\n\x00"):
                raise ValueError("Invalid executable configuration")
            if any(c in executable for c in ("/", "\\")) and not Path(executable).is_absolute():
                raise ValueError("Configured executable paths must be absolute")
        return self

    @classmethod
    def from_env(cls):
        repo = Path(__file__).resolve().parents[4]
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local/share")))
        profile = Path(os.environ.get("FASHION_WEB_PROFILE", str(base / "FashionAI")))
        return cls(profile=profile, runtime_dir=profile / "web-runtime", repository=repo,
                   database_path=Path(os.environ["FASHION_WEB_DATABASE"]) if os.environ.get("FASHION_WEB_DATABASE") else None,
                   ffmpeg=os.environ.get("FASHION_WEB_FFMPEG", "ffmpeg"),
                   ffprobe=os.environ.get("FASHION_WEB_FFPROBE", "ffprobe"))
