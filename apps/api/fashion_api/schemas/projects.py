"""Public W2 contract; internal file names and ORM state never cross the API."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Rights = Literal["unknown", "owned", "licensed", "permission_granted"]


class SourceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_url: HttpUrl | None = Field(default=None, max_length=2048)
    creator_name: str | None = Field(default=None, max_length=255)
    rights_status: Rights
    rights_notes: str | None = Field(default=None, max_length=4000)


class ProjectPatch(SourceMetadata):
    rights_status: Rights = "unknown"


class ProjectOut(SourceMetadata):
    id: str
    original_filename: str
    file_size: int
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    aspect_ratio: str
    status: str
    created_at: datetime
    updated_at: datetime
    revision: str
    processing_status: str = "idle"


class ProjectPage(BaseModel):
    items: list[ProjectOut]
    next_cursor: str | None
    total: int
    completed: int | None


class StorageDiagnostics(BaseModel):
    ready: bool
    profile_status: str
    writable: bool
    disk_free_bytes: int | None
    disk_total_bytes: int | None
    max_upload_bytes: int
    max_video_seconds: float
    checks: list[dict[str, str]]
