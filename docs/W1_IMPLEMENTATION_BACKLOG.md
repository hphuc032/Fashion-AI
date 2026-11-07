# W0 — W1 implementation backlog and approval gate

All rows are **PROPOSED**, implementation **NOT STARTED**. W1 is foundation/health/security/runtime only. No project CRUD, upload, DB migration, OCR/model job, engine refactor, M5 merge or release belongs in W1.

| ID / objective | Likely files | Dependencies / implementation notes | Tests and acceptance criteria | Risks |
|---|---|---|---|---|
| W1-01 Resolve supported runtimes and frozen dependencies | `apps/web/package.json`, package-lock.json, API requirements/constraints, runtime notes | W0 approval; inspect latest develop; keep Python3.11 and existing engine pins. Resolve Next/React/TS/Tailwind/shadcn/Zustand/Query and FastAPI/Starlette/Uvicorn set in isolated env, record exact pins and Node engine | Frozen clean install, Python dependency check, no engine-pin changes, actual versions logged; no model install | Native AI NumPy/Arrow conflicts; don't casually upgrade |
| W1-02 API package and factory | `apps/api/fashion_api/{__init__,main}.py`, core/config.py, tests/conftest.py | 01; avoid nested package `app`; dependency-injected lifespan; default no live DB and no services imported for inference | Health unit test imports without Streamlit UI, no files/DB/model network writes; single factory owner | Import side effects from existing bootstrap |
| W1-03 Local profile validation | API core/config.py, schemas/system.py | 02; explicit Web env names, validated absolute paths; map to engine process env in later milestones, not source edits now | Default future AppData profile; invalid/overlap/missing directory diagnostics; no live schema/open/migrate; only authorized runtime metadata directory created | M5 path/default dotenv mismatch; accidentally adopt wrong DB |
| W1-04 API errors and public health | api/v1/health.py, core/errors.py | 02/03; GET health minimal identity; redacted system status with schema `not_inspected`; bounded executable preflight outside event loop | Health200 schema; missing FFmpeg yields degraded status, no internal paths/tracebacks; no model startup | Mistaking API health for all models ready |
| W1-05 Local access middleware | core/security.py, api/v1/session.py, security tests | 02/03; Host/Origin/CORS before routes; one-use memory bootstrap, host-only HttpOnly Strict cookie, CSRF, expiry; no query tokens | Wrong Host/port/forwarded authority, null/evil Origin, missing/expired session, missing/mismatched CSRF rejected without effects; valid exact-origin exchange/read/revoke passes | Loopback is not authentication; cross-port cookie scope; bootstrap leakage |
| W1-06 Next shell | `apps/web/src/app/{layout,page}.tsx`, globals.css, dashboard/page.tsx; components/layout | 01; dark sidebar, status placeholders; no fake working project/AI actions; App Router TS | Typecheck/lint, keyboard navigation, loading/offline/error/health states, no secrets/absolute profile paths bundled | UI suggesting unimplemented workflow is available |
| W1-07 Typed API client | web/src/lib/api-client.ts; types/api; Query provider | 04/05; generate/validate types against FastAPI OpenAPI; cookie credentials, CSRF in memory, finite retries for reads only; session reload endpoint | DTO contract match, timeout/offline/error mapping, abort stale requests; never auto-retry mutation; no window/file/SQL access | Broad raw response serialization, duplicate side effects |
| W1-08 Dashboard health integration | features/dashboard, dashboard/page.tsx | 06/07; display API identity/local-only/provider readiness truthfully, source/legacy stage absent | Component tests and browser verify real health from actual API; error reconnect; no mocked E2E completion claim | Repeated polling/oversharing diagnostics |
| W1-09 Windows lifecycle scripts | scripts/start_web.ps1, stop_web.ps1; Web-only check helper (do not overwrite M5 check_environment.ps1) | 03–05/08; one lock/profile, strict3000/8000, native hidden children, PID/exe/create-time identity, bootstrap fragment, readiness/startup rollback | Start in path with spaces; duplicate start; occupied port; backend/Next failure; timeout; Ctrl+C/stop removes only owned children; no live DB changes; preserves portable | PID reuse, implicit install, leaked bootstrap, accidental M5 changes |
| W1-10 Test scaffolding and regression gate | apps/api/tests, web test config, Playwright config; additive CI job | 02/06 can scaffold independently after01; actual tests finalize after05/09. Reuse legacy CI unchanged; new tests use disposable profile, no live DB | Backend/security, component/TS, real two-service Playwright health/restart tests; old 215 deterministic M0–M4 tests still pass; explicit skips separate from real models | CI media setup/network stalls, new package discovery clashes |
| W1-11 Documentation and review handoff | docs/WEB_*.md, WEB_W1_TEST_REPORT.md, README Web section | All preceding; exact commands/version/results; feature branch PR to freshly verified develop | Acceptance checklist complete, no source/model/media/DB secrets tracked; owner review; no merge/release without approval | Claiming Web MVP complete from foundation only |

## Dependency order and independent work

Sequential critical path: owner approval→01→02/03→04/05→07→08→09→10 acceptance→11. Next shell06 can proceed after01 while API02–05 progresses. Test scaffolds can be prepared against agreed contracts; execution with real server requires09. API middleware and frontend layout can be worked independently at code boundaries, but no parallel agents are implied or started in W0. Do not start health UI against fabricated API results and call it integrated.

## W1 acceptance checklist

- Exact runtime versions/lockfiles resolve without changing existing engine pins; supported Windows Node/Python documented.
- One command starts real frontend3000/backend8000; UI reads authenticated real health; both listeners restricted to127.0.0.1; API docs accessible only under same local session policy (or explicitly disabled outside dev).
- Host/DNS-rebinding/Origin/CORS/CSRF/session negative tests pass, including bootstrap replay/expiry and missing credentials. No raw environment/config/path/secret in frontend/OpenAPI examples/logs.
- No database initialization/migration, model inference/download, user media mutation or source path relocation on W1 startup. Existing fallback entrypoints and M5 branch/PR untouched.
- Duplicate start and stop/restart/partial-failure tests prove owned-process cleanup; no unrelated port process killed; browser fragment removed and not logged.
- New API/component/browser tests and preserved legacy deterministic suite pass; test counts/failures/skips clearly recorded. Actual AI E2E remains future W3–W7 work.
- Draft/feature PR includes implementation/test/limits; stop for owner approval before expanding scope.

## Outstanding decisions and recommended defaults

1. Approve `fashion_api` package name, retained engine and direct authenticated browser→API model: recommended.
2. Keep W1 DB-free health and defer data adoption to a separate copied-profile migration: recommended. Owner later selects M4/M5/other live profile; no default database guessing.
3. Keep M5 separate and use a Web-specific environment check helper. Reusing M5 code later requires its own reviewed dependency decision; don't modify its PR to enable W1.
4. Accept WS snapshot resynchronization (no durable event replay) initially; no Redis/Celery.
5. Reserve later v70 only after fresh schema audit; idempotency/retry and archive decisions are W2/W3 gates, not W1 blockers.

## W0 approval gate

W0 completion means source-backed documents and Draft PR are delivered, not that the architecture is implemented. Consistency: yes, the design follows actual services/tables and records deviations from the initial plan. M0–M4 preservation: no runtime changes in W0; runtime equivalence is established by unchanged Git trees, not a newly executed full AI suite. Database safety: no writes/migration in W0; proposed procedure requires explicit profile selection, backup, copy-first verification and rollback. W1 readiness: backlog is ready for owner review, execution waits for explicit approval. Required approvals: W0 architecture/W1 scope now; live-data profile/relocation, any M5 integration, future merge/release separately.
