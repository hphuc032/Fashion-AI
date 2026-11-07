# W1 — Local Web foundation

Status: implemented for owner review; final verification/publication ledger below. W1 only. Project CRUD, upload, AI inference, job management and database adoption are not implemented.

## Baseline and preservation

Branch `feature/web-foundation-w1` starts directly from freshly fetched remote develop `51f12832e8feb13b0db12374292e2d6d2284ae64`. W0 `7d8bce748127c46aaf205524f9e2e780d5d97b92` is the authoritative architecture, inspected through Git objects; no W0 commit was cherry-picked/merged. PR #10 (M5) and PR #11 (W0) remain separate OPEN/DRAFT/UNMERGED, with no requested metadata changes. Main/develop/release tags remain unchanged.

Root `app/`, existing Streamlit entrypoints/UI, engine requirements, old scripts/tests/CI and M5 implementation are unchanged. Only additive `.gitignore` patterns and a separate README Web section modify existing files. New API never imports the root engine package, instantiates providers, creates SQLAlchemy sessions or opens SQLite. Its lifespan owns in-memory access state and bounded optional executable diagnostics only. Profile validation creates nothing; explicit supervisor start creates only its runtime metadata subtree. No existing DB initialization/migration/write, media/model deletion/relocation or automatic storage adoption occurs.

## Implemented structure and boundaries

| Location | Responsibility |
|---|---|
| `apps/api/requirements.in`, `requirements.lock` | Exact independent Web Python packages and transitive SHA256 hashes |
| `apps/api/fashion_api/main.py`, `serve.py` | App factory/lifespan; private supervisor stdin handoff; fixed loopback Uvicorn |
| `apps/api/fashion_api/core/` | Read-only Web profile, sanitized errors, ASGI Host/Origin/session/CSRF boundary |
| `apps/api/fashion_api/api/v1/`, `schemas/` | W1 routes and explicit path-free DTOs |
| `apps/api/export_openapi.py`, `openapi.json` | Explicit build-time contract, no lifespan/DB access |
| `apps/api/tests/` | API, negative security and actual Windows lifecycle tests |
| `apps/web/src/app/` | Next App Router layout, Dashboard, unavailable Projects/Settings pages |
| `apps/web/src/components/` | Responsive sidebar, feedback placeholder, reusable native Button using shadcn-style configuration |
| `apps/web/src/features/dashboard/` | Real health/status, loading/offline/expiry/reconnect states |
| `apps/web/src/lib/`, `types/`, `stores/` | OpenAPI-derived typed client, TanStack Query server state, transient Zustand state |
| `apps/web/src/proxy.ts` | Actual frontend Host/Origin validation; forwarded headers never replace Host |
| `apps/web/e2e/` | Real production Next + FastAPI Chromium tests; no HTTP mocking |
| `scripts/start_web.ps1`, `stop_web.ps1`, `web_runtime.py` | Independent hidden-process supervisor/ownership/locks and lifecycle |
| `.github/workflows/web-foundation.yml` | Additional Windows W1 check, existing workflow untouched |

### Actual endpoints

| Method and URL | Access / response |
|---|---|
| GET `/api/v1/health` | Minimal public local identity: status, api_version, instance_id; Host/Origin guards still apply |
| GET `/api/v1/system/status` | Authenticated, redacted readiness/tools/DB-configured/schema/model status |
| POST `/api/v1/session/bootstrap` | Exact Origin + bounded JSON + one-use startup secret → session cookie/CSRF |
| GET `/api/v1/session` | Authenticated CSRF/expiry recovery on page reload |
| DELETE `/api/v1/session` | Session + exact Origin + CSRF; revocation |
| GET `/api/v1/openapi.json` | Authenticated public DTO contract; Swagger/ReDoc disabled |

Tool availability uses executable discovery, bounded `-version` checks and fixed FFmpeg subtitle-filter probe, never media input. Missing tools yield `degraded`. DB configured means an explicit absolute path was declared, not that it exists/works; `schema_status=not_inspected` is unconditional. Model status is honestly `not_inspected`: W1 has no selected model profile and never guesses from old storage. Online API does not imply AI readiness. No absolute paths, process commands/PIDs, env dumps, credentials, internal Settings or tracebacks are serialized.

## Security mechanisms

- Strict `127.0.0.1:8000` / `127.0.0.1:3000`; no LAN bind or automatic port change. API disables proxy-header trust and access logs. ASGI checks precede routes: one exact Host, reject forwarded authority, exact Origin when present on reads and mandatory on mutations, reject null/file/untrusted/ambiguous origins. Credentialed CORS allowlists origin/method/headers; preflight is not authorization.
- Supervisor generates 256 random bootstrap bits in memory. API receives secret through private stdin, never argv/env/status/log. Browser opens a fragment URL; client clears fragment before exchange and shares one initialization promise. Secret90s, one-use constant-time hash check with bounded attempts.
- Session cookie host-only/HttpOnly/SameSite=Strict/Path=/api/no Domain. Secure is deliberately not asserted over local HTTP. Session token hashes and CSRF values remain backend memory; frontend CSRF stays module memory, never localStorage. Expiry3600s, revoke and API restart invalidate sessions. Cookie host scope is not port isolation; Origin+CSRF remain mandatory.
- Mutations require exact Origin/current session/CSRF and bounded2048-byte JSON. Query parameters are rejected in W1; no secret query transport. Validation/errors never echo submitted input. No-store/nosniff/no-referrer and frame/CSP policies apply. Next permits its inline hydration scripts/styles but loads no external fonts/scripts/assets and renders no user HTML in W1.
- Next validates actual Host and Origin; internally generated forwarded headers cannot override authority, contradictory values are rejected. Same-account malware remains outside an OS isolation guarantee.

## Frontend behavior

Vietnamese dark workspace with sidebar, real backend connection/readiness, tool checks, unknown model/schema status and clear future-stage cards. No working project/upload/OCR/render buttons or fabricated AI statistics. Projects/Settings explicitly explain unavailability. Responsive layout and keyboard skip-link are tested.

Central typed client uses OpenAPI-generated DTOs, credentials/include, 5s timeout, AbortController, up to two attempts for network-failed GET only, no mutation retries, structured public errors and explicit session-expiry handling. Query polling30s; no focus refetch. Cached health is not presented as current after errors. Zustand only stores transient navigation state. Browser has no database, filesystem or model access.

## Windows runtime

Wrappers pass argument arrays to isolated Python3.11; supervisor directly launches hidden Python/Node children without cmd/npm shell concatenation. It checks runtimes, existing build, fixed ports and paths; startup never installs/builds/downloads. One profile byte-lock; private status binds PID/executable/creation time/exact argv. A launch ID handles Windows virtualenv redirectors. API readiness matches instance ID; frontend readiness additionally verifies the owned tree is listening on loopback3000, not merely any HTTP200.

Stop request is scoped to run ID, terminates only verified owned trees, waits for terminal status and lock release, and never kills by PID/port/name alone. Stale/unverifiable ownership fails safely. Startup timeout/service failure rolls back owned children. QA found/fixed Windows lock-byte read contention, redirector PID mismatch, status-read/exit race and FILE_SHARE_DELETE rename sharing violation. Atomic JSON uses unique staging and bounded2s rename retry, preserving old complete JSON while readers finish; a regression simulates transient sharing errors.

Metadata/logs contain no bootstrap/session secret. Runtime errors use fixed operator messages and sanitized source-frame names, not raw config/env/exception values. Default profile `%LOCALAPPDATA%\FashionAI`, metadata only in `web-runtime/`. `-NoBrowser` supports headless checks and intentionally prints/stores no reusable login link; stop/restart normally to open a fresh authenticated browser. Supported startup is the production wrapper, not direct Next development server.

## Exact dependencies / installation

Verified host: Python3.11.18, Node24.14.0, npm11.9.0. Frozen target: Python3.11.x, Node24.x/npm11.x, Windows10/11; not a claim of qualification on every Windows machine.

Backend direct pins: FastAPI0.162.0, Uvicorn0.54.0, Pydantic2.12.5, SQLAlchemy2.0.45, psutil7.2.2, httpx0.28.1, pytest9.2.0; resolved Starlette1.10.0. Every transitive pin/hash is in `requirements.lock`. pip-tools7.6.2 generated it; a second fresh environment installed it with hashes and passed pip check without pip-tools/engine packages preinstalled. SQLAlchemy remains compatible/available but no engine is constructed.

Frontend exact pins include Next16.4.5, React/DOM19.3.1, TypeScript5.9.3, Tailwind/PostCSS4.3.5, Query5.107.1, Zustand5.1.0, Playwright1.65.0 and Vitest5.1.0; complete pins/integrity in package.json/package-lock.json. Clean npm ci and npm ls --all passed without force/legacy-peer-deps. A scoped minimatch11.0.5 override fixes the typescript-estree advisory. ESLint10 violated actual plugin peers; compatible9.39.5 is pinned. Its upstream deprecation is a tooling-maintenance limitation. Starlette's pinned working httpx TestClient emits a deprecation warning; it is recorded, not suppressed.

Official references consulted: [Next CLI hostname/port/build/start](https://nextjs.org/docs/app/api-reference/cli/next), [FastAPI middleware boundaries](https://fastapi.tiangolo.com/advanced/middleware/). Actual tests below establish behavior; reading docs alone is not acceptance.

```powershell
# From repository root; do not replace the engine environment.
py -3.11 -m venv .venv-web
& .\.venv-web\Scripts\python.exe -m pip install --require-hashes -r apps/api/requirements.lock
& .\.venv-web\Scripts\python.exe -m pip check
Push-Location apps/web
npm ci
npm run build
Pop-Location
& .\scripts\start_web.ps1
# Later:
& .\scripts\stop_web.ps1
```

Python3.11 and Node24/npm11 must already be selected/installed; this host used its existing managed Python to create the new environment. Start refuses occupied3000/8000; it never kills their owner or changes ports. Existing Streamlit/portable launchers are untouched.

| Configuration | Meaning |
|---|---|
| FASHION_WEB_PROFILE / `-Profile` | Absolute dedicated profile; default AppData/FashionAI; reject source/root overlap, reparse ancestors and invalid paths |
| FASHION_WEB_DATABASE | Optional absolute declaration; never opened/created/inspected |
| FASHION_WEB_FFMPEG / FASHION_WEB_FFPROBE | Optional absolute executables, otherwise PATH discovery; fixed diagnostics only |
| `-PythonPath` | Isolated Web Python for wrapper/owned children |
| `-NoBrowser` | Headless lifecycle/health checks, no persisted login secret |
| `-Timeout` | Startup readiness1–120s per service, default45s |
| FASHION_WEB_PYTHON / FASHION_WEB_QA_ROOT | Browser test interpreter/staging only |

Existing `.env`, FASHION_AI settings and M5 startup behavior are not consumed/adopted. Profile validation does not create directories. Only explicit supervisor startup writes its metadata subtree; no database folder/file is created.

## Verification commands / evidence

Run lifecycle and E2E sequentially: both need the same fixed ports.

```powershell
$env:PYTHONPATH = Join-Path $PWD 'apps/api'
& .\.venv-web\Scripts\python.exe -B -m pytest -c apps/api/pytest.ini apps/api/tests -q -p no:cacheprovider
Push-Location apps/web
npm run types:api
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:e2e
npm audit
Pop-Location
# Legacy regression: set STORAGE_ROOT and DATABASE_URL to a disposable QA profile first.
& .\.venv-m1-clean\Scripts\python.exe -B -m pytest tests -q -p no:cacheprovider --ignore=tests/test_m1_real.py --ignore=tests/test_m2_real.py --ignore=tests/test_m3_real.py --ignore=tests/test_m4_real.py
```

Actual local verification uses a fresh explicit pytest basetemp outside the repository and authorized loopback access. Sandbox OS-temp initially failed directory/cleanup access; sandbox asyncio socketpair blocked. Tests were rerun with proper QA roots/network permission, not weakened. An initial browser keyboard test clicked under the focused skip-link; the corrected test activates Enter and verifies main focus before menu interaction. An accidentally concurrent lifecycle/E2E run contended for ports; those failed runs were rejected and rerun serially. Initial production races above were fixed with evidence, not excluded.

### Final result ledger

- **PASS:** independent hashed Python install, second clean hashed install and pip check.
- **PASS:** clean npm ci; npm ls --all has no invalid peers; npm audit0 advisories at dependency verification.
- **PASS:** 54 Python tests in42.38s, failures0/errors0/skips0; includes API, negative security, real Windows lifecycle through both PowerShell7 and Windows PowerShell5.1, restart, duplicate, occupied ports, ownership and partial failures. One TestClient deprecation warning.
- **PASS:** 215 existing deterministic M0–M4 tests in111.34s, failures0/errors0/skips0, explicitly separate disposable engine storage/database and unchanged engine environment.
- **PASS:** TypeScript, lint, production build; 8 frontend unit/component tests. Final browser/publication results are appended after execution.
- **PASS:** 6 real two-service Chromium tests in17.5s, failures0/skips0: authenticated dashboard/actual DTO, wrong Host/Origin/missing session, one-use replay, restart/session invalidation/reconnect/revoke, actual API disconnect/offline/recovery, mobile width and keyboard navigation. Screenshot visually inspected after fragment removal. No HTTP mocks or user profile used.
- **PASS:** protected storage readback:1074 hashed files unchanged,0 missing,0 added (exclusive live desktop.lock excluded); tracked old runtime/test/dependency/CI trees unchanged. Payload check applies to new files and added lines, preserving pre-existing README text.
- **NOT TESTED / OUT OF SCOPE:** new AI inference or Web AI workflow, user DB integrity scan/migration, W2–W7 functionality, clean-machine installer/portable qualification, every Windows version/machine, GPU/cloud providers and performance benchmarks.

Synthetic test DB writes stay in QA fixtures. “No database writes” here means no existing user DB or W1 startup DB writes, not a claim that legacy regression fixtures never create their own SQLite files.

## Data protection, limits and approval gate

Private before/after SHA inventory covers1074 readable existing storage files. One active M5 `desktop.lock` is exclusively locked and cannot be content-hashed; it is an explicit verification limitation, not a reason to stop/alter M5. No user DB was opened with SQLite by W1. File hash preservation is not a SQLite integrity audit.

Deferred: W2–W7 CRUD/uploads/media/jobs/WS/AI integration, model inventory, DB adoption/migration, M5 reuse and releases. W1 has no generic filesystem/SQL/provider-setting mutation endpoint. Local HTTP and same-account malware limits remain; ESLint/TestClient tooling warnings require future compatible upgrades. No merge/release/main/develop/PR10/PR11 change occurs. Stop after W1 for owner review.

## Changed-file manifest

Final manifest below lists every added/modified tracked path versus approved develop, excluding ignored dependencies/builds/logs/screenshots/QA state. No machine-specific absolute paths, secrets, media, databases or model weights belong in the commit.

The legacy `*.ts` ignore is for MPEG transport-stream videos and initially also hid TypeScript files. Narrow exceptions now track only Web source/config/test TypeScript; other transport-stream media remains ignored. All required TS files are explicitly tracked. Existing README absolute-path text is preserved from baseline; new files/added lines introduce no machine-specific absolute paths.

### Added and modified paths

- `.github/workflows/web-foundation.yml`
- `.gitignore`
- `README.md`
- `apps/api/export_openapi.py`
- `apps/api/fashion_api/__init__.py`
- `apps/api/fashion_api/api/__init__.py`
- `apps/api/fashion_api/api/v1/__init__.py`
- `apps/api/fashion_api/api/v1/health.py`
- `apps/api/fashion_api/api/v1/session.py`
- `apps/api/fashion_api/core/__init__.py`
- `apps/api/fashion_api/core/config.py`
- `apps/api/fashion_api/core/errors.py`
- `apps/api/fashion_api/core/security.py`
- `apps/api/fashion_api/main.py`
- `apps/api/fashion_api/schemas/__init__.py`
- `apps/api/fashion_api/schemas/system.py`
- `apps/api/fashion_api/serve.py`
- `apps/api/openapi.json`
- `apps/api/pytest.ini`
- `apps/api/requirements.in`
- `apps/api/requirements.lock`
- `apps/api/tests/conftest.py`
- `apps/api/tests/test_api.py`
- `apps/api/tests/test_runtime.py`
- `apps/api/tests/test_security.py`
- `apps/web/.npmrc`
- `apps/web/components.json`
- `apps/web/e2e/foundation.spec.ts`
- `apps/web/eslint.config.mjs`
- `apps/web/next-env.d.ts`
- `apps/web/next.config.ts`
- `apps/web/package-lock.json`
- `apps/web/package.json`
- `apps/web/playwright.config.ts`
- `apps/web/postcss.config.mjs`
- `apps/web/src/app/dashboard/page.tsx`
- `apps/web/src/app/globals.css`
- `apps/web/src/app/layout.tsx`
- `apps/web/src/app/page.tsx`
- `apps/web/src/app/projects/page.tsx`
- `apps/web/src/app/providers.tsx`
- `apps/web/src/app/settings/page.tsx`
- `apps/web/src/components/feedback/placeholder.tsx`
- `apps/web/src/components/layout/workspace.tsx`
- `apps/web/src/components/ui/button.tsx`
- `apps/web/src/features/dashboard/dashboard.test.tsx`
- `apps/web/src/features/dashboard/dashboard.tsx`
- `apps/web/src/lib/api-client.test.ts`
- `apps/web/src/lib/api-client.ts`
- `apps/web/src/lib/utils.ts`
- `apps/web/src/proxy.ts`
- `apps/web/src/stores/workspace.ts`
- `apps/web/src/test/setup.ts`
- `apps/web/src/types/api.generated.ts`
- `apps/web/tsconfig.json`
- `apps/web/vitest.config.ts`
- `docs/WEB_W1_IMPLEMENTATION_REPORT.md`
- `scripts/start_web.ps1`
- `scripts/stop_web.ps1`
- `scripts/web_runtime.py`
