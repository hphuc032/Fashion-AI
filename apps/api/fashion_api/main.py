"""DB-free FastAPI factory. No root app imports, providers or bootstrap calls."""
from contextlib import asynccontextmanager
import secrets
import shutil
import subprocess
from uuid import uuid4

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException

from fashion_api.api.v1 import health, session
from fashion_api.core.config import WebConfig
from fashion_api.core.errors import error
from fashion_api.core.security import AccessState, LocalBoundary
from fashion_api.schemas.system import DatabaseStatus, SystemStatus, Tools


def diagnostics(config):
    ffmpeg, ffprobe = shutil.which(config.ffmpeg), shutil.which(config.ffprobe)
    def works(executable):
        if not executable:
            return False
        try:
            result = subprocess.run([executable, "-version"], capture_output=True, timeout=5,
                shell=False, creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0)
            return result.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False
    ffmpeg = ffmpeg if works(ffmpeg) else None
    ffprobe = ffprobe if works(ffprobe) else None
    subtitles = "unavailable"
    if ffmpeg:
        try:
            result = subprocess.run([ffmpeg, "-hide_banner", "-filters"], capture_output=True,
                timeout=5, text=True, errors="replace", shell=False,
                creationflags=subprocess.CREATE_NO_WINDOW if __import__('os').name == 'nt' else 0)
            subtitles = "available" if result.returncode == 0 and any(
                len(parts := line.split()) > 1 and parts[1] in {"ass", "subtitles"}
                for line in result.stdout.splitlines()) else "unavailable"
        except (OSError, subprocess.SubprocessError):
            subtitles = "unavailable"
    return SystemStatus(readiness="ready" if ffmpeg and ffprobe and subtitles == "available" else "degraded",
        tools=Tools(ffmpeg=bool(ffmpeg), ffprobe=bool(ffprobe), subtitles=subtitles),
        database=DatabaseStatus(configured=config.database_path is not None))


def create_app(config: WebConfig | None = None, *, bootstrap_secret: str | None = None, instance_id: str | None = None, clock=None,
               diagnostics_provider=diagnostics):
    config = config or WebConfig.from_env()
    access = AccessState(bootstrap_secret or secrets.token_urlsafe(32), config.bootstrap_ttl,
                         config.session_ttl, **({"clock": clock} if clock else {}))

    @asynccontextmanager
    async def lifespan(app):
        # Probe only tools, off the event loop. No directory creation/DB connection.
        from starlette.concurrency import run_in_threadpool
        app.state.diagnostics = await run_in_threadpool(diagnostics_provider, config)
        try:
            yield
        finally:
            access.clear()

    app = FastAPI(title="Fashion AI Local Web", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config, app.state.access, app.state.instance_id = config, access, instance_id or str(uuid4())
    import threading
    app.state.upload_gate = threading.Lock()
    app.add_middleware(LocalBoundary, config=config, access=access)
    app.include_router(health.router)
    app.include_router(session.router)
    from fashion_api.api.v1 import projects
    from fashion_api.services.projects import ProjectError
    app.include_router(projects.router)

    @app.exception_handler(ProjectError)
    async def project_error(_request, exc):
        return error(exc.status, exc.code, exc.message)

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def openapi():
        return app.openapi()

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _exc):
        return error(422, "VALIDATION_ERROR", "Invalid request fields.")

    @app.exception_handler(HTTPException)
    async def http_error(_request, exc):
        return error(exc.status_code, "NOT_FOUND" if exc.status_code == 404 else "REQUEST_REJECTED", "Request is not available.")

    @app.exception_handler(Exception)
    async def unexpected(_request, _exc):
        return error(500, "INTERNAL_ERROR", "The local API could not complete the request.")

    return app
