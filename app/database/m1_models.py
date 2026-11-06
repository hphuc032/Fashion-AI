"""Additive M1 tables; M0 projects are never altered or recreated."""
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, Float, ForeignKey, Index, Integer, JSON, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base, utc_now


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"
    version: Mapped[int] = mapped_column(primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(default=utc_now)


class OCRJob(Base):
    __tablename__ = "ocr_jobs"
    __table_args__ = (
        CheckConstraint("status IN ('QUEUED','PROCESSING','COMPLETED','FAILED','CANCELLED')"),
        CheckConstraint("kind IN ('ocr','translate')"),
        CheckConstraint("active_slot = 1"),
        CheckConstraint("completed_frames >= 0 AND total_frames >= completed_frames"),
        Index("uq_single_active_ocr", "active_slot", unique=True,
              sqlite_where=text("status IN ('QUEUED','PROCESSING')")),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="ocr")
    status: Mapped[str] = mapped_column(String(16), default="QUEUED")
    active_slot: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSON)
    completed_frames: Mapped[int] = mapped_column(default=0)
    total_frames: Mapped[int] = mapped_column(default=0)
    stage: Mapped[str] = mapped_column(String(32), default="queued")
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    pid: Mapped[int | None] = mapped_column(nullable=True)
    lease_expires: Mapped[float] = mapped_column(Float, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class OCRDetection(Base):
    __tablename__ = "ocr_detections"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        CheckConstraint("timestamp >= 0 AND frame_index >= 0 AND frame_width > 0 AND frame_height > 0"),
        CheckConstraint("json_array_length(bounding_box) = 4 AND json_extract(bounding_box,'$[0]') >= 0 AND json_extract(bounding_box,'$[1]') >= 0 AND json_extract(bounding_box,'$[2]') > 0 AND json_extract(bounding_box,'$[3]') > 0"),
        Index("ix_detection_project_time", "project_id", "timestamp"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("ocr_jobs.id"), index=True)
    segment_id: Mapped[str | None] = mapped_column(ForeignKey("text_segments.id"), nullable=True, index=True)
    frame_index: Mapped[int]
    timestamp: Mapped[float]
    frame_width: Mapped[int]
    frame_height: Mapped[int]
    source_text: Mapped[str] = mapped_column(Text)
    confidence: Mapped[float]
    bounding_box: Mapped[list] = mapped_column(JSON)
    polygon: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class TextSegment(Base):
    __tablename__ = "text_segments"
    __table_args__ = (
        CheckConstraint("review_status IN ('pending','approved','rejected')"),
        CheckConstraint("confidence >= 0 AND confidence <= 1"),
        CheckConstraint("start_time >= 0 AND end_time > start_time"),
        CheckConstraint("revision >= 0"),
        CheckConstraint("json_array_length(bounding_box) = 4 AND json_extract(bounding_box,'$[0]') >= 0 AND json_extract(bounding_box,'$[1]') >= 0 AND json_extract(bounding_box,'$[2]') > 0 AND json_extract(bounding_box,'$[3]') > 0"),
        Index("ix_segment_project_time", "project_id", "start_time"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    job_id: Mapped[str] = mapped_column(ForeignKey("ocr_jobs.id"))
    source_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str] = mapped_column(Text, default="")
    start_time: Mapped[float]
    end_time: Mapped[float]
    bounding_box: Mapped[list] = mapped_column(JSON)
    confidence: Mapped[float]
    detection_status: Mapped[str] = mapped_column(String(32), default="needs_review")
    translation_provider: Mapped[str] = mapped_column(String(255), default="manual")
    review_status: Mapped[str] = mapped_column(String(16), default="pending")
    translation_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)


class TranslationCache(Base):
    __tablename__ = "translation_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(255))
    translated_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
