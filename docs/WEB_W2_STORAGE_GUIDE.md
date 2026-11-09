# W2 — Explicit database and managed video storage

W2 never searches for, selects, creates or upgrades a user's database. The runtime profile is separate from the engine data profile. An online dashboard without a selected database shows a configuration error, not a fake empty project library.

## Configure an existing approved profile

Set these private process variables in the PowerShell session used to start Web. Replace examples with the exact matching existing profile; do not point at an arbitrary first `.db` file. No example below provisions a database.

```powershell
$env:FASHION_WEB_PROFILE = 'D:\FashionAIWebRuntime'
$env:FASHION_WEB_DATABASE = 'D:\ApprovedFashionData\storage\fashion_ai.db'
$env:FASHION_WEB_STORAGE = 'D:\ApprovedFashionData\storage'
$env:FASHION_WEB_FFMPEG = 'D:\MediaTools\bin\ffmpeg.exe'
$env:FASHION_WEB_FFPROBE = 'D:\MediaTools\bin\ffprobe.exe'
# Optional limits may lower the existing defaults, never exceed them.
$env:FASHION_WEB_MAX_UPLOAD_MB = '500'
$env:FASHION_WEB_MAX_VIDEO_SECONDS = '180'
& .\scripts\start_web.ps1 -PythonPath .\.venv-web\Scripts\python.exe
# Stop only this owned runtime:
& .\scripts\stop_web.ps1 -PythonPath .\.venv-web\Scripts\python.exe
```

Use the startup browser link to authenticate; never put bootstrap/session secrets into URLs with query parameters, documentation or logs. `-NoBrowser` intentionally does not produce a reusable login URL. Startup still creates only its private runtime metadata; project endpoints inspect the explicitly configured existing data profile when requested. Root `.env`, M5 `config.env`, the newest demo database and `%LOCALAPPDATA%` databases are never automatically adopted. The Web adapter constructs engine Settings directly from validated Web configuration.

Install Web dependencies separately from the AI engine:

```powershell
py -3.11 -m venv .venv-web
& .\.venv-web\Scripts\python.exe -m pip install --require-hashes -r apps/api/requirements.lock
& .\.venv-web\Scripts\python.exe -m pip check
Push-Location apps/web
npm ci
npm run typecheck
npm run lint
npm test
npm run build
Pop-Location
```

No model/installer/AI dependency installation is necessary for W2. Python lock adds only engine-compatible dotenv and multipart packages; engine requirement pins remain unchanged. FFmpeg/FFprobe are explicitly installed operator tools; startup never downloads them.

## Layout and consistency

```text
<managed storage>/
  .web-uploads/upload-<random>/    request-local spool; removed on success/failure/disconnect
  projects/<existing-or-new-uuid>/source/<generated-uuid>.mp4|.mov|.mkv
```

Existing project IDs and relative file references remain authoritative. Original filenames, source URL (http/https metadata only), creator and rights are stored as metadata. File bytes are outside SQLite; URLs are never fetched automatically. Do not move databases/media, switch roots or run desktop migration maintenance while Web is operating.

Import streams at bounded chunk sizes through the existing service, validates FFprobe metadata before publication, atomically creates the final name without overwrite, then commits the Project. Handled failures remove only this attempt's owned `.part`/published file and empty owned directories. A repeated Idempotency-Key with matching filename/metadata/source SHA-256 returns the same Project, including after restart; a mismatch returns 409. Keep a retry's file, source fields and key unchanged. Metadata edits require the latest response revision via If-Match; stale edits are rejected instead of overwriting another update.

Limits: MP4/MOV/MKV containers, detected codecs h264/hevc/av1/vp8/vp9/mpeg4/mpeg2video/mjpeg/prores, positive finite duration/FPS and validated dimensions, maximum 500 MiB and 180 seconds by default. Container must match extension. Browser MIME is never authority. Native playback depends on the browser codec/container; H.264 MP4 is the tested path. Local NTFS/POSIX hard links are required for exclusive atomic final naming. Read-only/network/reparse profiles are unsupported; insufficient disk space is reported safely.

## Diagnostics, media access and recovery

Authenticated `/api/v1/system/diagnostics` returns readiness, free/total space, advisory write access and limits. It exposes no absolute paths and creates no missing user directory. Missing/unsupported profile is actionable; do not create an empty database to hide the error. W1 health/system status remain independent of DB adoption.

The native player reads `/api/v1/projects/{id}/source` with the local session. It supports single byte ranges (200/206/416), seeking, correct lengths and private no-store/nosniff headers. No browser-supplied file path is accepted. Media is never copied to Next `public/` or served anonymously.

Normal cancellation/failure removes request staging. If the process crashes and `.web-uploads` contains leftovers, the next upload returns `UPLOAD_RECOVERY_REQUIRED` rather than deleting unknown files or accumulating more uploads. Stop the owned runtime, preserve a private consistent backup, inspect the exact abandoned request directory and remove only confirmed abandoned staging. Never recursively remove `projects/`, source videos, databases, models or exports. An unreferenced generated source from a publication/commit power-loss gap requires separate reviewed recovery; W2 does not guess/delete it.

No Web-profile backup/restore UI or arbitrary-profile migration was added. M5's existing backup utility assumes its own `storage/fashion_ai.db` layout; do not treat it as a generic backup command for any configured Web DB. Use a SQLite-consistent backup and matching media snapshot under an approved maintenance procedure before adopting production data. All development/E2E fixtures are provisioned explicitly in disposable QA profiles, never through product startup.
