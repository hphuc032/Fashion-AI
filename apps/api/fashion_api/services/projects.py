"""Explicit-profile adapter. No migration factory, provider or startup DB access."""

import base64
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import stat
import sys
from uuid import UUID

from fashion_api.schemas.projects import ProjectOut, ProjectPage, StorageDiagnostics


class ProjectError(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


def fail(status, code, message):
    raise ProjectError(status, code, message)


def no_links(path):
    path = Path(path)
    for item in (path, *path.parents):
        if item.is_symlink() or (
            item.exists() and getattr(item.lstat(), "st_file_attributes", 0) & 0x400
        ):
            fail(
                409,
                "PROFILE_UNSAFE",
                "The configured profile contains filesystem links.",
            )
    return path.resolve()


def profile(config):
    if not config.database_path or not config.storage_root:
        fail(
            503,
            "PROFILE_REQUIRED",
            "Configure an existing database and its managed storage explicitly.",
        )
    db, root = no_links(config.database_path), no_links(config.storage_root)
    if not db.is_file() or not root.is_dir():
        fail(
            503,
            "PROFILE_UNAVAILABLE",
            "The configured database or storage is unavailable.",
        )
    if (
        root == Path(root.anchor)
        or root.is_relative_to(config.repository)
        and root == config.repository
    ):
        fail(409, "PROFILE_UNSAFE", "Storage must be a dedicated managed directory.")
    if root.is_relative_to(config.runtime_dir) or config.runtime_dir.is_relative_to(
        root
    ):
        fail(409, "PROFILE_UNSAFE", "Storage must not overlap runtime metadata.")
    # URI mode=ro prevents accidental creation; never change journal mode or schema.
    try:
        with closing(
            sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=2)
        ) as connection:
            connection.execute("PRAGMA query_only=ON")
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(projects)")
            }
            required = {
                "id",
                "upload_token",
                "original_filename",
                "stored_filename",
                "file_path",
                "file_size",
                "source_url",
                "creator_name",
                "rights_status",
                "rights_notes",
                "duration",
                "width",
                "height",
                "fps",
                "video_codec",
                "audio_codec",
                "aspect_ratio",
                "status",
                "created_at",
                "updated_at",
            }
            if not required.issubset(columns):
                fail(
                    409,
                    "SCHEMA_UNSUPPORTED",
                    "Existing project schema is unsupported; no migration was run.",
                )
            tables = {
                r[0]
                for r in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "schema_migrations" in tables:
                versions = {
                    r[0]
                    for r in connection.execute("SELECT version FROM schema_migrations")
                }
                if not versions.issubset({1, 20, 30, 40, 50, 60}):
                    fail(
                        409,
                        "SCHEMA_UNSUPPORTED",
                        "Unknown schema version; no migration was run.",
                    )
            unique = [
                row
                for row in connection.execute("PRAGMA index_list(projects)")
                if row[2] and not row[4]
            ]
            if not any(
                [
                    r[2]
                    for r in connection.execute(
                        'PRAGMA index_info("' + row[1].replace('"', '""') + '")'
                    )
                ]
                == ["upload_token"]
                for row in unique
            ):
                fail(
                    409,
                    "SCHEMA_UNSUPPORTED",
                    "Durable upload identity constraint is missing.",
                )
    except sqlite3.Error:
        fail(503, "PROFILE_UNAVAILABLE", "The configured database cannot be read.")
    return db, root


@contextmanager
def sessions(config):
    db, root = profile(config)
    # Lazy imports preserve DB-free W1 health/startup and avoid any model load.
    if str(config.repository) not in sys.path:
        sys.path.insert(0, str(config.repository))
    from sqlalchemy import create_engine, event
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(
        "sqlite:///" + db.as_uri() + "?mode=rw&uri=true",
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    @event.listens_for(engine, "connect")
    def options(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    try:
        yield sessionmaker(engine, expire_on_commit=False), root
    finally:
        engine.dispose()


def canonical_id(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError()
    except (ValueError, TypeError, AttributeError):
        fail(422, "VALIDATION_ERROR", "A canonical UUID is required.")
    return value


def revision(project):
    fields = [
        "updated_at",
        "source_url",
        "creator_name",
        "rights_status",
        "rights_notes",
        "status",
    ]
    values = [getattr(project, f) for f in fields]
    values[0] = values[0].replace(tzinfo=timezone.utc).isoformat()
    return hashlib.sha256(
        json.dumps([str(v) for v in values], ensure_ascii=False).encode()
    ).hexdigest()


def dto(project, session=None):
    fields = set(ProjectOut.model_fields) - {"revision", "processing_status"}
    values = {f: getattr(project, f) for f in fields}
    for f in ("created_at", "updated_at"):
        values[f] = (
            values[f].replace(tzinfo=timezone.utc)
            if values[f].tzinfo is None
            else values[f]
        )
    processing = "idle"
    if session is not None:
        from sqlalchemy import inspect, text

        tables = set(inspect(session.bind).get_table_names())
        for table in ("ocr_jobs", "render_jobs", "dub_jobs", "final_render_jobs"):
            if (
                table in tables
                and session.execute(
                    text(
                        f"SELECT 1 FROM {table} WHERE project_id=:id AND status NOT IN ('COMPLETED','FAILED','CANCELLED') LIMIT 1"
                    ),
                    {"id": project.id},
                ).first()
            ):
                processing = "processing"
                break
    return ProjectOut(
        **values, revision=revision(project), processing_status=processing
    )


def get(session, project_id):
    from app.database.models import Project

    item = session.get(Project, canonical_id(project_id))
    if not item:
        fail(404, "NOT_FOUND", "Project not found.")
    return item


def page(config, cursor=None, limit=20, search=""):
    with sessions(config) as (factory, _), factory() as session:
        from sqlalchemy import select, func, or_, and_, inspect, text
        from app.database.models import Project

        query = select(Project)
        if search:
            escaped = (
                search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            )
            query = query.where(
                or_(
                    Project.original_filename.ilike("%" + escaped + "%", escape="\\"),
                    Project.creator_name.ilike("%" + escaped + "%", escape="\\"),
                )
            )
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        # Project.status remains 'imported' in the legacy engine. Count actual
        # persisted non-trashed exports if that approved optional table exists.
        completed = (
            session.scalar(
                text(
                    "SELECT count(DISTINCT project_id) FROM final_exports WHERE deleted_at IS NULL"
                )
            )
            if "final_exports" in inspect(session.bind).get_table_names()
            else None
        )
        if cursor:
            try:
                value = json.loads(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                )
                if set(value) != {"at", "id", "search"} or value["search"] != search:
                    raise ValueError()
                at = datetime.fromisoformat(value["at"])
                canonical_id(value["id"])
                query = query.where(
                    or_(
                        Project.created_at < at,
                        and_(Project.created_at == at, Project.id < value["id"]),
                    )
                )
            except Exception:
                fail(422, "INVALID_CURSOR", "Invalid project page cursor.")
        rows = list(
            session.scalars(
                query.order_by(Project.created_at.desc(), Project.id.desc()).limit(
                    limit + 1
                )
            )
        )
        more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if more:
            next_cursor = (
                base64.urlsafe_b64encode(
                    json.dumps(
                        {
                            "at": rows[-1].created_at.isoformat(),
                            "id": rows[-1].id,
                            "search": search,
                        }
                    ).encode()
                )
                .decode()
                .rstrip("=")
            )
        return ProjectPage(
            items=[dto(p, session) for p in rows],
            next_cursor=next_cursor,
            total=total,
            completed=completed,
        )


def detail(config, project_id):
    with sessions(config) as (factory, _), factory() as session:
        return dto(get(session, project_id), session)


def patch(config, project_id, data, expected):
    with sessions(config) as (factory, _), factory() as session:
        from sqlalchemy import text, inspect

        session.execute(text("BEGIN IMMEDIATE"))
        project = get(session, project_id)
        if not expected or expected != revision(project):
            fail(409, "REVISION_CONFLICT", "Project changed. Reload before editing.")
        tables = set(inspect(session.bind).get_table_names())
        for table in ("ocr_jobs", "render_jobs", "dub_jobs", "final_render_jobs"):
            if (
                table in tables
                and session.execute(
                    text(
                        f"SELECT 1 FROM {table} WHERE project_id=:id AND status NOT IN ('COMPLETED','FAILED','CANCELLED') LIMIT 1"
                    ),
                    {"id": project_id},
                ).first()
            ):
                fail(
                    409,
                    "JOB_BUSY",
                    "Wait for project processing before changing metadata.",
                )
        for key, value in data.model_dump(mode="json", exclude_unset=True).items():
            setattr(project, key, value)
        session.commit()
        return dto(project)


def source_path(root, item):
    # Association is authoritative, not a browser file parameter.
    relative = Path(item.file_path)
    expected = (
        Path("projects") / canonical_id(item.id) / "source" / item.stored_filename
    )
    if relative != expected or Path(item.stored_filename).name != item.stored_filename:
        fail(404, "NOT_FOUND", "Managed source not found.")
    path = no_links(root / relative)
    if relative.suffix.lower() not in {".mp4", ".mov", ".mkv"}:
        fail(404, "NOT_FOUND", "Managed source type is unsupported.")
    if not path.is_relative_to(root) or not path.is_file():
        fail(404, "NOT_FOUND", "Managed source not found.")
    return path


def open_source(config, project_id):
    with sessions(config) as (factory, root), factory() as session:
        item = get(session, project_id)
        path = source_path(root, item)
        handle = path.open("rb")
        # Bind the opened handle to the verified file and expected immutable size.
        try:
            current = path.stat()
            opened = os.fstat(handle.fileno())
            final = opened_path(handle)
            if (
                not final.is_relative_to(root)
                or final != path
                or not stat.S_ISREG(opened.st_mode)
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (current.st_dev, current.st_ino, item.file_size)
            ):
                fail(409, "STALE_ARTIFACT", "Source identity changed.")
            return handle, opened.st_size, path.suffix.lower()
        except BaseException:
            handle.close()
            raise


def opened_path(handle):
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        import msvcrt

        call = ctypes.windll.kernel32.GetFinalPathNameByHandleW
        call.argtypes = [
            wintypes.HANDLE,
            wintypes.LPWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        call.restype = wintypes.DWORD
        buffer = ctypes.create_unicode_buffer(32768)
        length = call(msvcrt.get_osfhandle(handle.fileno()), buffer, len(buffer), 0)
        if not length or length >= len(buffer):
            fail(503, "STORAGE_UNAVAILABLE", "Cannot verify the opened media handle.")
        name = buffer.value
        if name.startswith("\\\\?\\"):
            name = name[4:]
        return Path(name).resolve()
    final = Path("/proc/self/fd") / str(handle.fileno())
    if not final.exists():
        fail(
            503,
            "STORAGE_UNAVAILABLE",
            "Opened media verification is unavailable on this platform.",
        )
    return final.resolve()


def digest(stream):
    stream.seek(0)
    h = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        h.update(block)
    stream.seek(0)
    return h.digest()


def validate_codec(metadata):
    if metadata.video_codec not in {
        "h264",
        "hevc",
        "av1",
        "vp8",
        "vp9",
        "mpeg4",
        "mpeg2video",
        "mjpeg",
        "prores",
    }:
        fail(415, "UNSUPPORTED_MEDIA", "The detected video codec is not supported.")


def create(config, upload, metadata, token):
    canonical_id(token)
    with sessions(config) as (factory, root):
        from app.database.models import Project
        from app.core.config import Settings
        from app.utils.validators import SourceInfo, UserError, validate_filename
        from app.services.storage_service import import_video
        from sqlalchemy import select
        from sqlalchemy.exc import OperationalError, IntegrityError

        filename = upload.filename or ""
        try:
            validate_filename(filename)
        except UserError:
            fail(415, "UNSUPPORTED_MEDIA", "Use a safe MP4, MOV or MKV filename.")
        with factory() as session:
            existing = session.scalar(
                select(Project).where(Project.upload_token == token)
            )
            if existing:
                old = dto(existing)
                matches = old.original_filename == filename and all(
                    getattr(old, k) == v for k, v in metadata.model_dump().items()
                )
                with source_path(root, existing).open("rb") as saved:
                    matches = matches and digest(saved) == digest(upload.file)
                if not matches:
                    fail(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Upload key is already bound to different content or metadata.",
                    )
                return old, False
        if upload.size is None or upload.size > config.max_upload_size_mb * 1024 * 1024:
            fail(413, "UPLOAD_TOO_LARGE", "Video exceeds the configured upload limit.")
        if not shutil.which(config.ffprobe):
            fail(
                503,
                "DEPENDENCY_UNAVAILABLE",
                "FFprobe is unavailable in the configured runtime.",
            )
        if shutil.disk_usage(root).free < upload.size + 16 * 1024 * 1024:
            fail(
                507,
                "INSUFFICIENT_STORAGE",
                "Insufficient free storage for this upload.",
            )
        no_links(root / "projects")
        settings = Settings(
            storage_root=root,
            database_url="sqlite:///" + str(config.database_path),
            ffprobe_path=config.ffprobe,
            ffmpeg_path=config.ffmpeg,
            max_upload_size_mb=config.max_upload_size_mb,
            max_video_seconds=config.max_video_seconds,
        )
        try:
            item = import_video(
                upload.file,
                filename,
                SourceInfo(**metadata.model_dump()),
                settings,
                factory,
                token,
                validate_metadata=validate_codec,
            )
            # Another client (for example Streamlit) may win the same durable
            # unique token after our first read. Verify its payload too.
            returned = dto(item)
            if returned.original_filename != filename or any(
                getattr(returned, k) != v for k, v in metadata.model_dump().items()
            ):
                fail(
                    409,
                    "IDEMPOTENCY_CONFLICT",
                    "Upload key is already bound to different metadata.",
                )
            with source_path(root, item).open("rb") as saved:
                if digest(saved) != digest(upload.file):
                    fail(
                        409,
                        "IDEMPOTENCY_CONFLICT",
                        "Upload key is already bound to different content.",
                    )
            return returned, True
        except UserError:
            fail(
                422,
                "VALIDATION_ERROR",
                "Video is empty, corrupt, mismatched, or exceeds the duration limit.",
            )
        except (OperationalError, IntegrityError):
            fail(
                409,
                "IMPORT_CONFLICT",
                "Database is busy or the import conflicts with current state. Retry with the same key.",
            )
        except OSError as exc:
            if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
                fail(507, "INSUFFICIENT_STORAGE", "Storage ran out of space.")
            fail(503, "STORAGE_UNAVAILABLE", "Storage cannot complete this upload.")


def diagnostics(config):
    status = "ready"
    free = total = None
    writable = False
    try:
        _, root = profile(config)
        usage = shutil.disk_usage(root)
        free, total = usage.free, usage.total
        writable = os.access(root, os.W_OK) and os.access(config.database_path, os.W_OK)
        if not writable:
            status = "not_writable"
    except ProjectError as exc:
        status = exc.code.lower()
    return StorageDiagnostics(
        ready=status == "ready",
        profile_status=status,
        writable=writable,
        disk_free_bytes=free,
        disk_total_bytes=total,
        max_upload_bytes=config.max_upload_size_mb * 1024 * 1024,
        max_video_seconds=config.max_video_seconds,
        checks=[
            {
                "name": "managed_profile",
                "status": status,
                "message": "Explicit existing profile required; no automatic initialization.",
            }
        ],
    )
