"""Thin authenticated routes; admission before multipart parsing bounds spool/probe IO."""

import re
import errno
from tempfile import TemporaryDirectory
from starlette.formparsers import MultiPartException
from fashion_api.services.multipart import ManagedMultipart
from fastapi import APIRouter, Request, Query, Header
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from fashion_api.services import projects as service
from fashion_api.schemas.projects import (
    SourceMetadata,
    ProjectPatch,
    ProjectOut,
    ProjectPage,
    StorageDiagnostics,
)

router = APIRouter(prefix="/api/v1")


@router.get("/projects", response_model=ProjectPage)
def listing(
    request: Request,
    cursor: str | None = Query(None, max_length=2048),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query("", max_length=255),
):
    if not set(request.query_params).issubset({"cursor", "limit", "search"}) or any(
        len(request.query_params.getlist(k)) != 1 for k in request.query_params
    ):
        service.fail(
            422, "VALIDATION_ERROR", "Unsupported or repeated project query fields."
        )
    return service.page(request.app.state.config, cursor, limit, search)


@router.post(
    "/projects",
    response_model=ProjectOut,
    status_code=201,
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["video", "metadata"],
                        "properties": {
                            "video": {"type": "string", "format": "binary"},
                            "metadata": {
                                "type": "string",
                                "contentMediaType": "application/json",
                                "contentSchema": SourceMetadata.model_json_schema(),
                            },
                        },
                    }
                }
            },
        }
    },
)
async def upload(request: Request, idempotency_key: str = Header(..., max_length=36)):
    service.canonical_id(idempotency_key)
    gate = request.app.state.upload_gate
    if not gate.acquire(blocking=False):
        service.fail(
            409,
            "IMPORT_BUSY",
            "Another upload is being admitted. Retry with the same upload key.",
        )
    try:
        _, root = await run_in_threadpool(service.profile, request.app.state.config)
        staging = service.no_links(root / ".web-uploads")
        staging.mkdir(exist_ok=True)
        if any(staging.iterdir()):
            service.fail(
                409,
                "UPLOAD_RECOVERY_REQUIRED",
                "Unfinished upload staging requires operator review with the runtime stopped.",
            )
        try:
            with TemporaryDirectory(prefix="upload-", dir=staging) as directory:
                parser = ManagedMultipart(
                    request.headers,
                    request.stream(),
                    directory=directory,
                    max_files=1,
                    max_fields=1,
                    max_part_size=16384,
                )
                form = await parser.parse()
                try:
                    if (
                        set(form) != {"video", "metadata"}
                        or len(form.multi_items()) != 2
                        or not isinstance(form["video"], UploadFile)
                        or not isinstance(form["metadata"], str)
                    ):
                        service.fail(
                            422,
                            "VALIDATION_ERROR",
                            "Supply exactly one video and metadata object.",
                        )
                    try:
                        metadata = SourceMetadata.model_validate_json(form["metadata"])
                    except ValidationError:
                        service.fail(
                            422,
                            "VALIDATION_ERROR",
                            "Invalid source metadata or rights confirmation.",
                        )
                    item, created = await run_in_threadpool(
                        service.create,
                        request.app.state.config,
                        form["video"],
                        metadata,
                        idempotency_key,
                    )
                    return JSONResponse(
                        item.model_dump(mode="json"),
                        status_code=201 if created else 200,
                        headers={"ETag": '"' + item.revision + '"'},
                    )
                finally:
                    await form.close()
        except (HTTPException, MultiPartException):
            if getattr(request.state, "upload_too_large", False):
                service.fail(413, "UPLOAD_TOO_LARGE", "Video exceeds the upload limit.")
            service.fail(
                422, "VALIDATION_ERROR", "Invalid or excessive multipart fields."
            )
        except OSError as exc:
            if exc.errno in {errno.ENOSPC, errno.EDQUOT}:
                service.fail(507, "INSUFFICIENT_STORAGE", "Storage ran out of space.")
            service.fail(
                503, "STORAGE_UNAVAILABLE", "Storage cannot accept this upload."
            )
    finally:
        gate.release()


@router.get("/projects/{project_id}", response_model=ProjectOut)
def detail(request: Request, project_id: str):
    return service.detail(request.app.state.config, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
def patch(
    request: Request,
    project_id: str,
    data: ProjectPatch,
    if_match: str | None = Header(None, max_length=100),
):
    return service.patch(
        request.app.state.config,
        project_id,
        data,
        if_match.strip('"') if if_match else None,
    )


def byte_range(value, size):
    if value is None:
        return 0, size - 1, 200
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value)
    if not match or not any(match.groups()):
        raise ValueError()
    first, last = match.groups()
    if not first:
        count = int(last)
        if count <= 0:
            raise ValueError()
        return max(0, size - count), size - 1, 206
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError()
    return start, end, 206


@router.get("/projects/{project_id}/source")
def source(
    request: Request, project_id: str, range: str | None = Header(None, max_length=128)
):
    handle, size, suffix = service.open_source(request.app.state.config, project_id)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Disposition": 'inline; filename="source' + suffix + '"',
    }
    try:
        start, end, status = byte_range(range, size)
    except ValueError:
        handle.close()
        return Response(
            status_code=416, headers={**headers, "Content-Range": f"bytes */{size}"}
        )
    headers["Content-Length"] = str(end - start + 1)
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    def chunks():
        try:
            handle.seek(start)
            remaining = end - start + 1
            while remaining:
                block = handle.read(min(1024 * 1024, remaining))
                if not block:
                    break
                remaining -= len(block)
                yield block
        finally:
            handle.close()

    return StreamingResponse(
        chunks(),
        status_code=status,
        headers=headers,
        media_type={
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".mkv": "video/x-matroska",
        }.get(suffix, "application/octet-stream"),
    )


@router.get("/system/diagnostics", response_model=StorageDiagnostics)
def diagnostics(request: Request):
    return service.diagnostics(request.app.state.config)
