# W2 — Project management and storage integration

Baseline: approved develop `49c2b3605f67e53c315b883fc857d0184ff8690b` (W0 #11, W1 #12 and M5 #10 merged). Branch: `feature/web-project-management-w2`. W2 only; Draft PR, no merge/release or W3 authorization.

## Audit and decisions

Inspected the W0 architecture, API contract, database migration plan, service reuse matrix, threat model, repository audit, W1 report and merged implementation. Root `app/` remains the engine. M0–M5 use specialized tables, synchronous SQLAlchemy sessions and bounded subprocesses. `create_database()` immediately migrates and must never be used by the Web lifecycle or adoption adapter. Independent legacy/M5/demo profiles exist; none was selected as the user's Web database.

The existing Project table has indexed `created_at`, UUID primary key, unique `upload_token`, source/rights metadata and `updated_at`. No new schema, table, column, index or migration is needed. Durable upload retry uses the existing unique token, plus comparison of original filename, normalized source metadata and source SHA-256. The identity survives API restart. A changed payload returns 409. This is not frontend-only or in-memory idempotency. Metadata PATCH uses an If-Match digest of existing timestamp/metadata/status, checked under `BEGIN IMMEDIATE`; stale changes return 409, active project jobs block editing. No timestamp precision or new revision-column assumption is needed.

W0 differences/additions: W1 previously rejected every query and accepted tiny JSON only. W2 allows only bounded projects cursor/limit/search parameters, multipart only on POST projects, PATCH plus allowlisted preflight headers. W1 health/system status remain DB-free and honestly `not_inspected`; authenticated storage diagnostics perform explicit read-only profile inspection on demand. Project DTO adds a path-free revision and read-only processing status. Page adds actual totals and an optional count of projects with recorded non-trashed exports; absent export schema returns null rather than an invented completed count. Upload requestBody is documented as bounded multipart with JSON SourceMetadata. Existing W0 documentation is preserved.

## Implemented routes

| Method | Path | Behavior |
|---|---|---|
| GET | `/api/v1/projects` | Limit 20/max100, `(created_at,id)` descending keyset cursor, filename/creator search with literal LIKE escaping, DB-side totals |
| POST | `/api/v1/projects` | One video + metadata, canonical Idempotency-Key, rights enum required, 201 new / 200 replay, 409 mismatch/busy |
| GET | `/api/v1/projects/{id}` | Explicit DTO, existing ID, safe source metadata and revision |
| PATCH | `/api/v1/projects/{id}` | Source URL/creator/rights fields only, If-Match, short locked transaction |
| GET | `/api/v1/projects/{id}/source` | Authenticated managed handle, bounded bytes, 200/206/416 single ranges |
| GET | `/api/v1/system/diagnostics` | Profile readiness, advisory write access, free/total bytes, configured upload/duration limits; no paths |

Frontend: real dashboard data; `/projects` library/search/previous-next navigation; `/projects/new` file picker/drop, local preview, source/rights confirmation, XHR progress/cancel/error/retry and leave warning; `/projects/[id]` native authenticated source player, metadata editing and unavailable W3/W4/W5/W6 stages. TanStack Query owns server data with stable keys/invalidation; Zustand remains navigation-only. No OCR/model/render controls claim functionality. Thumbnails are deferred: no authoritative existing thumbnail asset field was found.

## Reused services and adapters

- Existing SQLAlchemy `Project` model and IDs; request-scoped engine/session factory opened in SQLite `mode=rw`, foreign keys on. No migration-capable factory or journal-mode change.
- Existing `Settings` defaults (500 MiB, 180 seconds), `SourceInfo` and `validate_filename`; explicit Web settings are constructed directly without dotenv discovery.
- Existing `probe_video` and `parse_metadata`: local-protocol-only FFprobe argument array, 30-second timeout, container match, duration, dimensions, frame rate and codecs. W2 codec admission adds an allowlist through an optional import callback; no second probe/import implementation.
- Existing `storage_service.import_video`: still owns copy/probe/Project transaction and token uniqueness. Minimal shared change stages `.part` bytes, calls optional metadata validation, publishes complete bytes atomically with exclusive hard-link creation, and cleans only files/directories actually created by that attempt. Existing callers need no signature changes. Collision and commit-failure tests protect earlier files. Local NTFS/POSIX hard-link support is required; unsupported filesystems fail closed.
- New API profile, pagination, concurrency, multipart spool and authenticated Range adapters. No ORM/provider/UI objects are returned to the browser.

## Data and resource safety

See [storage guide](WEB_W2_STORAGE_GUIDE.md). Startup, health, contract export and system status do not open/create/migrate SQLite. Explicit existing DB + matching managed storage are required before project requests. Profile inspection uses SQLite read-only mode and rejects missing columns, missing full unique upload-token constraint, links/reparse points and unknown schema versions. Versions 1/20/30/40/50/60 and legacy projects-only schema are recognized; no automatic upgrade occurs.

One admitted upload per API process bounds spool/probe work; standard Web supervisor owns one fixed-port instance. Authentication/Origin/CSRF precede body consumption. Actual request bytes are capped, including absent Content-Length; files spool at 1 MiB to a private request directory under managed storage. Multipart fields/files are bounded. Disk errors map to 507; unsupported filename/codec to 415, malformed/container/duration failures to 422, oversize to 413. Blocking import/probe/digest/DB work runs outside the event loop. Reads/search never materialize all projects. Search uses DB-side bounded queries; substring search may scan the filename/creator columns because no unapproved search index is added.

Original names are metadata; source authority is generated UUID identity. Source reads verify project association, root containment, every ancestor for reparse links, file size/inode, and the final opened handle path (Windows GetFinalPathNameByHandleW / Linux proc fd). Single ranges include open-ended/suffix forms; invalid/multiple ranges return 416 with total size. Media stays private/no-store/nosniff with safe disposition; CORS exposes only required range/revision headers. No static storage mount or Next public media.

## Limits and deferred work

No live user profile was opened through SQL, changed, migrated or relocated. Only disposable test profiles were written. Video validation is bounded metadata/container admission, not a full hostile-parser sandbox or every-frame integrity guarantee. MOV/MKV or some accepted codecs may not play in a given browser; UI reports this clearly. No video transcoding is added to W2. Free space/write permission diagnostics are advisory snapshots; actual I/O errors remain authoritative.

Cancellation before full receipt cleans staging; after all bytes are admitted, an import may commit despite a disconnected browser. UI explains this and retries retain the same key. A process/power crash between filesystem publication and SQLite commit can leave an unreferenced generated source; W2 never deletes unknown originals automatically. Leftover multipart staging blocks further imports with 409 pending stopped-runtime operator review, bounding repeated crash accumulation. No crash-resume/garbage collection is promised. Existing M5 backup/restore is regression-tested for its supported layout; arbitrary Web-profile backup/restore/migration UI is deferred.

Not implemented: project archive/delete (needs separate schema decision), generic assets, arbitrary settings, model downloads, OCR/translation/jobs/WS, video text replacement, dubbing, final rendering, cloud upload or publishing. W3–W7 remain separate approvals. Main/tags and merged PRs #10/#11/#12 remain untouched by W2.

Exact verification/publication evidence: [test report](WEB_W2_TEST_REPORT.md).
