from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base, utc_now


class ReplacementConfig(Base):
    __tablename__ = "text_replacement_configs"
    __table_args__ = (UniqueConstraint('project_id','segment_id'),{'info':{'schema_version':30}})
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'),index=True)
    segment_id: Mapped[str] = mapped_column(ForeignKey('text_segments.id',ondelete='CASCADE'))
    settings: Mapped[dict] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean,default=True)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now,onupdate=utc_now)


class RenderJob(Base):
    __tablename__ = "render_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED','PROCESSING','COMPLETED','FAILED','CANCELLED')"),
        CheckConstraint('active_slot=1'),
        Index('uq_single_active_render','active_slot',unique=True,sqlite_where=text("status IN ('QUEUED','PROCESSING')")),
        {'info':{'schema_version':30}},
    )
    id: Mapped[str] = mapped_column(String(36),primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey('projects.id'),index=True)
    request_token: Mapped[str] = mapped_column(String(36),unique=True)
    active_slot: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(16),default='QUEUED')
    progress: Mapped[float] = mapped_column(default=0)
    config_snapshot: Mapped[dict] = mapped_column(JSON)
    output_path: Mapped[str | None] = mapped_column(Text,nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text,nullable=True)
    pid: Mapped[int | None] = mapped_column(nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean,default=False)
    lease_expires: Mapped[float]
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
