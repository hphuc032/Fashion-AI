from datetime import datetime

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models import Base, utc_now


class ReviewState(Base):
    __tablename__ = "segment_reviews"
    __table_args__ = {"info": {"schema_version": 20}}
    segment_id: Mapped[str] = mapped_column(ForeignKey("text_segments.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(16))
    score: Mapped[float]
    reasons: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    reviewed_at: Mapped[datetime] = mapped_column(default=utc_now)


class ReviewEvent(Base):
    __tablename__ = "review_events"
    __table_args__ = {"info": {"schema_version": 20}}
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    segment_id: Mapped[str | None] = mapped_column(ForeignKey("text_segments.id", ondelete="SET NULL"), nullable=True)
    segment_key: Mapped[str] = mapped_column(String(36))
    state: Mapped[str] = mapped_column(String(32))
    mode: Mapped[str] = mapped_column(String(32))
    method: Mapped[str] = mapped_column(String(16))
    score: Mapped[float]
    reasons: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=utc_now)
