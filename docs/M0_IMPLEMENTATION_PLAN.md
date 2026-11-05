# M0 implementation plan

Scope: foundation only. Latest user task overrides the parent specification: MP4/MOV/MKV, default 500 MiB; retain configurable 180-second duration bound. No OCR, translation, speech, subtitles or exports.

Architecture: local Streamlit dashboard → upload/storage and FFprobe services → SQLAlchemy 2 SQLite. Pydantic validates settings, source fields and metadata. Media stored below storage/projects/<UUID>/source; DB stores relative paths. Original bytes remain unchanged.

Modules: app/core/{config,logger}.py; app/database/{models,session}.py; app/services/{video_service,storage_service}.py; app/utils/validators.py; app/ui/{dashboard,components}.py; app/main.py. Supporting requirements, theme, environment template, README, tests, fixture generator and implementation log.

Order: configuration/database → bounded chunked import and real metadata probing → dashboard/preview/recent list → unit, service integration, Streamlit smoke checks → documentation and acceptance audit.

Dependencies: Python 3.11, Streamlit, SQLAlchemy 2, Pydantic 2, python-dotenv, pytest; external FFmpeg/FFprobe. Pin versions after checking official package metadata. No paid API or AI dependency.

Tests: valid/malformed/no-audio metadata, unsupported extension/container, upload byte limit, duration, missing executable, unsafe filenames, unique IDs, transaction cleanup, restart persistence, rerun idempotency; real synthetic FFmpeg→FFprobe→import test when binaries available; Streamlit AppTest and server health check.

Risks: machine currently has Python 3.14.2 only and no FFmpeg/FFprobe on PATH. Browser playback depends on codec (prefer MP4/H.264/AAC); M0 never transcodes. FFprobe validates metadata, not every decoded frame. Streamlit buffers uploads before service-level chunked copy. Interrupted imports may leave orphan directories; no automatic deletion of user media. Local trusted single-user deployment only.

Outcome: implemented M0 only. Provisioned isolated Python 3.11.18 and portable FFmpeg 9.0.2; all 26 tests passed. Browser upload, preview playback and server-restart persistence verified. See IMPLEMENTATION_LOG.md and M0_ACCEPTANCE.md for actual evidence and untested scenarios. No next milestone started.
