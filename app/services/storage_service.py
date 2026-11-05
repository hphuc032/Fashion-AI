"""Transactional local import; no user filename is used as a storage path."""
import logging
from pathlib import Path
from typing import BinaryIO
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.database.models import Project
from app.services.video_service import probe_video
from app.utils.validators import SourceInfo, UserError, validate_filename

log = logging.getLogger("fashion_ai.storage")


def list_projects(sessions: sessionmaker) -> list[Project]:
    with sessions() as session:
        return list(session.scalars(select(Project).order_by(Project.created_at.desc())))


def resolve_media(root: Path, relative: str) -> Path:
    root = root.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise UserError("Đường dẫn video không hợp lệ.")
    return path


def import_video(stream: BinaryIO, filename: str, source: SourceInfo, settings: Settings,
                 sessions: sessionmaker, upload_token: str) -> Project:
    """Retrying the same form submission token returns the existing project."""
    UUID(upload_token)
    with sessions() as session:
        existing = session.scalar(select(Project).where(Project.upload_token == upload_token))
        if existing:
            return existing
    project_id = str(uuid4())
    directory = settings.storage_root / "projects" / project_id / "source"
    target = None
    try:
        suffix = validate_filename(filename)
        directory.mkdir(parents=True, exist_ok=False)
        target = directory / f"{uuid4()}{suffix}"
        total = 0
        stream.seek(0)
        with target.open("xb") as output:
            while chunk := stream.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_bytes:
                    raise UserError(f"Video vượt giới hạn {settings.max_upload_size_mb} MB.")
                output.write(chunk)
        if total == 0:
            raise UserError("Tệp video rỗng.")
        metadata = probe_video(target, settings.ffprobe_path, suffix)
        if metadata.duration > settings.max_video_seconds:
            raise UserError(f"Video vượt giới hạn {settings.max_video_seconds:g} giây.")
        project = Project(
            id=project_id, upload_token=upload_token, original_filename=filename,
            stored_filename=target.name, file_path=target.relative_to(settings.storage_root).as_posix(),
            file_size=total, source_url=str(source.source_url) if source.source_url else None,
            creator_name=source.creator_name, rights_status=source.rights_status,
            rights_notes=source.rights_notes, status="imported", **metadata.model_dump(),
        )
        with sessions.begin() as session:
            session.add(project)
        log.info("upload_imported project_id=%s bytes=%d", project_id, total)
        return project
    except Exception as exc:
        # Only remove the specific new file and empty directories created by this attempt.
        if target is not None:
            target.unlink(missing_ok=True)
        if directory.exists():
            directory.rmdir()
            directory.parent.rmdir()
        if isinstance(exc, IntegrityError):
            with sessions() as session:
                winner = session.scalar(select(Project).where(Project.upload_token == upload_token))
                if winner:
                    return winner
        log.warning("upload_rejected project_id=%s type=%s", project_id, type(exc).__name__)
        raise
