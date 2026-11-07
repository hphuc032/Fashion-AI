from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"
    instance_id: str


class Tools(BaseModel):
    ffmpeg: bool
    ffprobe: bool
    subtitles: Literal["available", "unavailable", "not_inspected"]


class DatabaseStatus(BaseModel):
    configured: bool
    schema_status: Literal["not_inspected"] = "not_inspected"


class SystemStatus(BaseModel):
    api_version: Literal["v1"] = "v1"
    local_only: Literal[True] = True
    readiness: Literal["ready", "degraded"]
    tools: Tools
    database: DatabaseStatus
    models: Literal["not_inspected"] = "not_inspected"


class BootstrapIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bootstrap_secret: str = Field(min_length=43, max_length=128, repr=False)


class SessionOut(BaseModel):
    csrf_token: str
    expires_at: str
