# W2 — Verification ledger

Date: 2026-11-09. Baseline `49c2b3605f67e53c315b883fc857d0184ff8690b`; branch `feature/web-project-management-w2`. All runtime writes below use explicit disposable QA profiles. No user database was used for SQL tests or migrated.

## Local results

| Verification | Actual result |
|---|---|
| Fresh `.venv-web-w2`, hashed Python installation + pip check | PASS; no engine/model/development tools preinstalled |
| W1 + W2 Python API/security/Windows lifecycle | **76 passed, 0 failures/errors/skips, 37.79 s** |
| Existing M0–M5 deterministic regression | **241 passed, 0 failures/errors/skips, 64.21 s** |
| Frontend component/client tests | **15 passed, 0 failures/skips**, 3 files, 2.65 s |
| TypeScript + ESLint | PASS |
| Production build | PASS; projects/new and dynamic project detail included |
| Real two-service Playwright, final production build + fresh frozen Python | **7 passed, 0 failures/skips, 19.3 s** |
| Existing storage SHA-256 before/after | **1,075 files identical** |
| Tracked forbidden payload/size + changed-content credential signature audit | PASS; no DB/media/model/secret env/binary payload or tracked file >1 MiB |
| Diff whitespace / schema and runtime preservation | PASS; no schema/migration/provider/engine config/runtime-script changes |

76 Python cases include the existing 56 W1 cases and 20 W2 cases: real SQLite import/detail/search/keyset pages, durable replay and payload mismatch, optimistic metadata conflict, actual FFprobe metadata/container checks, full/partial/suffix source ranges and 416, safe filename handling, invalid media, byte/duration limits, disk admission and actual injected publication ENOSPC, collision preservation, SQL failure after publication cleanup, missing/unknown DB profile, session/CSRF/Host/Origin/expiry, cross-project file association, actual symlink or Windows junction escape, managed parser disconnect cleanup, interrupted staging admission, unsupported codec rollback and bounded concurrent import rejection. Synthetic fault injection is not represented as real disk exhaustion or malicious native-code exploitation.

15 frontend cases include W1 state/client behavior plus library search/pagination, real-DTO empty/error/diagnostics, rights confirmation, progress, retained retry key, invalid file selection, authenticated player/error state, cancellation and internal-link leave warning. These are component tests, not proof of actual media transport.

Real browser E2E independently starts FastAPI and production Next, authenticates via the real one-use bootstrap cookie/CSRF workflow, verifies the empty library/dashboard, selects a generated authorized H.264 MP4, confirms rights, observes the progress element, creates the project, renders details, plays and seeks to 7 seconds, verifies an actual authenticated 206 byte response against the fixture bytes, edits source metadata, searches the library, restarts the API, authenticates again, verifies persisted project/source playback and SHA-256 identity. All six W1 browser security/restart/offline/mobile cases also pass. No HTTP mocks establish upload/streaming acceptance. Screenshot `.web-local/w2-project-detail.png` was visually inspected; it is ignored QA output, not a committed user asset.

## Commands used

From repository root in PowerShell (tool paths resolved explicitly; `$qa` is a new disposable directory for each run):

```powershell
& .\.venv-web-rebase\Scripts\python.exe -m venv .venv-web-w2
& .\.venv-web-w2\Scripts\python.exe -m pip install --require-hashes -r apps/api/requirements.lock --quiet
& .\.venv-web-w2\Scripts\python.exe -m pip check
$env:PYTHONPATH = Join-Path $PWD 'apps/api'
$env:TEMP = $qa
$env:TMP = $qa
$env:FASHION_WEB_FFMPEG = $ffmpeg
$env:FASHION_WEB_FFPROBE = $ffprobe
& .\.venv-web-w2\Scripts\python.exe -B -m pytest -c apps/api/pytest.ini apps/api/tests -q -p no:cacheprovider --basetemp "$qa/pytest" --tb=short --junitxml=.web-local/w2-api.junit.xml

# Separate engine environment and separate fresh QA profile:
$env:STORAGE_ROOT = Join-Path $qa 'storage'
$env:DATABASE_URL = 'sqlite:///' + (Join-Path $qa 'test.db')
$env:FFMPEG_PATH = $ffmpeg
$env:FFPROBE_PATH = $ffprobe
& .\.venv-m1-clean\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider --ignore=tests/test_m1_real.py --ignore=tests/test_m2_real.py --ignore=tests/test_m3_real.py --ignore=tests/test_m4_real.py --ignore=tests/test_m5_real.py --basetemp "$qa/pytest" --junitxml=.web-local/w2-engine.junit.xml --tb=short

Push-Location apps/web
npm run types:api
npm run typecheck
npm run lint
npm test
npm run build
$env:FASHION_WEB_PYTHON = (Resolve-Path '../../.venv-web-w2/Scripts/python.exe').Path
$env:FASHION_WEB_QA_ROOT = $qaParent
npm run test:e2e
Pop-Location
git diff --check
```

Local media tools were FFmpeg/FFprobe 9.0.2, Python 3.11.18, Node 24.14.0/npm11.9.0. API JUnit and engine JUnit remain ignored under `.web-local/`. Hosted Windows CI installs the hashed Web lock and `npm ci`, verifies actual media executables, runs the same types/lint/unit/build/API/E2E gates and rejects Python skips. The six legacy hosted milestone gates remain intact.

## Failures found and corrected

Initial 11-case W2 run: 2 failed/9 passed. Revision hashing differed between in-memory UTC and SQLite-naive datetimes; fixed by canonical UTC normalization. Multipart library intentionally strips legacy Windows client drive-path prefixes; test now verifies the safe basename and no filesystem authority rather than asserting an unobservable original header value. Later Python runs pass all cases.

First combined browser run: 6 passed/1 failed at rights selector lookup; the select's accessible name included its option text. Added an explicit accessible label; subsequent actual upload/playback/restart runs pass. Type generation initially exposed a missing standalone SourceMetadata component: frontend now uses a generated Project DTO field projection; multipart OpenAPI explicitly documents the JSON metadata schema. ESLint found state assignment inside object-URL effect; moved creation into file selection with effect cleanup. No failure was suppressed or converted into a passing collection result.

One upstream Starlette httpx TestClient deprecation warning remains in the pinned working stack. It does not affect current passing integration. No dependencies were upgraded to hide it.

First hosted head `e425766` passed all six legacy jobs, frozen installs, type/lint/build, 15 frontend tests and all 76 Python cases (33.81 s). Hosted browser run passed six W1 cases and progressed through the real W2 upload/metadata/player/Range flow, then failed at the post-restart dashboard: the test reloaded a full-navigation bootstrap page immediately, potentially aborting the one-use exchange after fragment removal. Corrected the test to wait for the authenticated online state before reload, then assert online/persistence again. This preserves real authentication and all restart assertions; no timeout extension, mock or automatic test retry was added. Final-head hosted evidence is recorded in PR metadata/final handoff.

## Not tested / approval boundary

Not tested: new AI inference, OCR/translation, cloud/GPU providers, long-video throughput/RAM benchmark, every supported codec/player/Windows version, complete hostile-parser sandboxing, every-frame corruption detection, power-loss recovery, arbitrary Web-profile backup/restore UI and installer/signing qualification. M5 backup/restore tests are part of the 241 existing regression cases in their supported disposable layout; no production backup or restore was performed. See implementation report/storage guide for cancellation/crash limitations and explicit live-profile adoption.

Hosted checks and Draft PR URL are recorded in PR metadata/final handoff after publication. W2 is not declared complete until the final pushed head has green hosted gates. Do not merge the Draft PR or start W3 without owner approval.
