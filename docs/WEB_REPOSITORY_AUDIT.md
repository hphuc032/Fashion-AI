# W0 — Repository audit

Audit date: 2026-11-07. Repository: `hphuc032/Fashion-AI`. Scope: architecture and documentation only. Source of truth: inspected Git trees and read-only SQLite metadata, not historical milestone claims.

## Evidence vocabulary

- **VERIFIED**: observed in source, a command result, or GitHub API during W0.
- **INFERRED**: reasoned consequence of inspected implementation; not runtime proof.
- **PROPOSED**: future design; not implemented.
- **NOT FOUND**: absent from the inspected tracked source, not a claim about every installed dependency.
- **NOT TESTED**: behavior not exercised in W0. Historical tests are explicitly identified as historical.

## Git and workspace snapshot — VERIFIED

| Item | Observed state |
|---|---|
| Directory | `D:\tiktok\Fashion-AI` |
| Starting branch | `feature/m5-windows-packaging`, clean, head `8ac209c995b60a962bb595efec808cc887f3d2ee` |
| Origin fetch/push URL | `https://github.com/hphuc032/Fashion-AI.git` |
| Remote main | `9c13cb0fc26cbdb43e9bb21e31a58dbb330ec9d3` |
| Remote develop | `51f12832e8feb13b0db12374292e2d6d2284ae64` |
| Local main / develop before W0 | `a3d2e63` / `bb4b94a`; behind origin by 52 / 42 commits; neither moved |
| Stable release | Annotated `v1.0.0`; M0–M4 source release; no new release in W0 |
| Existing open PRs before W0 | GitHub search returned only [M5 #10](https://github.com/hphuc032/Fashion-AI/pull/10) |
| M5 #10 | OPEN, DRAFT, unmerged, base develop `51f1283`, head `8ac209c`; 7 commits, 28 files; no new head since previous report |
| W0 branch existence before creation | Neither local ref nor remote head existed |
| W0 branch and base | `feature/web-migration-w0`, created directly from verified `origin/develop` at `51f1283` |

Initial sandboxed `git fetch origin` failed (`getaddrinfo() thread failed to start`); approved network retry succeeded. Direct remote heads via `git ls-remote --heads origin` independently matched the fetched refs. GitHub PR metadata independently confirmed the M5 base/head. No M5 changes were copied, cherry-picked or merged into W0. PR #10 metadata was read only.

Remote feature heads: M0 `a222f96`, M1 `cf95ca5`, M2 `d62665a`, M3 `1e6085b`, M4 `67b8ffb`, M5 `8ac209c`, Smart Review `40a4881`; release branch `e2e148a`. Recent integration: PR #6 M4 merge `ce1df24`, release metadata PR #7 `fafcf56`, history reconciliation PR #9 `51f1283`, release PR #8 main `9c13cb0`.

## Source and dependency findings — VERIFIED

Streamlit entry is `app/main.py::bootstrap`; UI is in `app/ui/`. Services/providers do not import Streamlit (source search). This is an effective reuse boundary: preserve the root `app` package during incremental Web integration. The proposed nested `apps/api/app` would collide with that package; use `apps/api/fashion_api` instead.

| Milestone | Actual implementation | Tests |
|---|---|---|
| M0 | `app/core/{config,logger}.py`, `app/database/{models,session,migrations}.py`, `app/services/{storage_service,video_service}.py`, `app/utils/validators.py` | `tests/test_m0.py`, `test_dashboard.py` |
| M1 + review | `frame_extractor`, `ocr_service`, `ocr_repository`, `text_tracker`, `translation_service`, `translation_review_service`, `job_manager`; Paddle and Argos providers | frame/OCR/tracking/translation/job/integration/UI/review test modules; `test_m1_real.py` |
| M2 | `replacement_repository`, `replacement_contract`, `text_compositor`, `text_layout`, `inpainting_provider`, `render_preview`, `render_jobs`, `video_renderer`; `app/render_worker.py` | `test_m2.py`, `test_m2_real.py` |
| M3 | `audio_extractor`, ASR/TTS providers, `speech_segmentation`, `speech_repository`, `dubbing_service`, `dub_jobs`, `audio_sync_service`, `dubbing_contract`; `app/dub_worker.py` | `test_m3.py`, `test_m3_real.py` |
| M4 | `final_render_config`, `subtitle_service`, `video_mux_service`, `final_output_validation`, `final_render_service`, `final_job_manager`; `app/final_worker.py` | `test_m4.py`, `test_m4_real.py` |
| M5, branch only | `app/desktop/{launcher,runtime,model_manager}.py`, `models.json`, `desktop_schema.py`, `desktop_studio.py`, `scripts/build_windows.py`, Windows wrappers | `test_m5.py`, `test_m5_real.py`; not on W0 base |

Full callable/source inventory and contracts: [reuse matrix](WEB_SERVICE_REUSE_MATRIX.md). Actual table definitions and schema variants: [database audit](WEB_DATABASE_MIGRATION_PLAN.md).

Dependency chain: `requirements-m4.txt` → M3 → M2 → M1 → base. Python used locally is 3.11.18. Base pins Streamlit 1.66.1, SQLAlchemy 2.0.45, Pydantic 2.12.5, python-dotenv 1.2.2, pytest 9.2.0. M1 pins NumPy 1.26.4, PyArrow 19.0.1, pandas 3.0.6, OpenCV-contrib 4.10.0.84, PaddlePaddle 3.2.2, PaddleOCR 3.3.2, PaddleX OCR-core 3.3.13, CTranslate2 4.8.5, SentencePiece 0.2.2, psutil 7.2.2. M2 adds fonttools 4.63.0; M3 faster-whisper 1.2.1, sherpa-onnx 1.13.8, soundfile 0.13.1. Optional FunASR 1.4.21 is isolated in `requirements-m3-funasr.txt`. M5 build-only PyInstaller 6.22.0 is not a Web runtime requirement.

Node `v24.14.0` and npm `11.9.0` were found on PATH; GitHub CLI was NOT FOUND on PATH. Next.js project/package lock, FastAPI routes, WebSocket API, browser session/CSRF middleware and Playwright suite were NOT FOUND in tracked product source. Transitive package installation does not establish an implemented API. Do not upgrade the working Python AI stack to start W1.

## Data and operational discrepancies

1. **VERIFIED:** several independent SQLite databases coexist; the name `m4-demo` does not imply schema 50. Its current database has versions 1/20/30/40/50/60 and 18 tables. Default source DB has version 1 and 6 tables. Never infer the active DB from folder names or silently open it through the migration-capable factory during audit.
2. **VERIFIED:** source storage defaults to repository `storage`; M5 defaults to `%LOCALAPPDATA%\FashionAILocalizer\storage` with models outside that storage folder. Proposed `%LOCALAPPDATA%\FashionAI` differs from both. Root switching is a future opt-in migration, not a W1 startup side effect.
3. **VERIFIED:** no general `jobs`, `job_events`, `video_assets`, `app_settings` tables. There are specialized job tables, and a Project is created together with its source video. Draft-project CRUD and generic retry/idempotency are new application capabilities.
4. **VERIFIED:** generic OCR queue has no request-token argument; M2/M3/M4 queues do. A uniform HTTP Idempotency-Key requires a durable adapter; it cannot be promised by passing a token to the current OCR queue.
5. **VERIFIED:** migration uses metadata `create_all` plus version records; it is additive table creation, not an Alembic column-alteration system. Future column changes require explicit forward migration handling.
6. **VERIFIED:** M4 requires current M2 and approved assembled M3 artifacts; final export also requires matching completed preview. Do not substitute the original video/audio when these contracts fail.
7. **VERIFIED:** Smart Review's semantic certification is deliberately limited to a small verified glossary; structural checks do not certify general neural translation quality.
8. **VERIFIED:** no automatic speech/music separation pipeline. M4 accepts a validated, separately supplied background manifest. Soft MP4 subtitles are mov_text; original ASS sidecar retains styling.
9. **VERIFIED:** prior cleanup removed obsolete environments/build ZIPs; `.venv-m1-clean`, portable extracted app, models, projects and exports remain. Old README commands referencing removed environments are historical, not a reliable current launcher. W0 performs no additional deletion.
10. **VERIFIED:** approved develop always loads ROOT/.env with override=False. Only M5 adds FASHION_AI_ENV_FILE selection. W1 must set validated engine process environment explicitly and must not assume M5 configuration behavior is already integrated.

## M5 interaction

**INFERRED:** no fundamental architecture conflict: model catalog/integrity, runtime ownership, backup/restore and external storage concepts are reusable. Launcher is Streamlit-specific, backup hardcodes `storage/fashion_ai.db`, model-download jobs live in schema 60 and in-process threads; these need explicit adapters or future refactoring. W1 cannot import `app.desktop` from approved develop. Preserve M5 branch, PR and portable application, and decide any later selective integration in its own reviewed change. Do not silently make merging M5 a dependency of W1 health-only work.

## Verification ledger

Executed in W0: `Get-Content` plan/spec/dependencies/source/tests/scripts; `rg --files` and callable/import searches; `git status --short --branch`, `remote -v`, `fetch origin` (retry successful), `branch -a -vv`, `log --oneline --all -12`, `ls-remote --heads origin`, `tag -n`, `show-ref --verify` (expected missing W0 ref), `diff origin/develop...feature/m5-windows-packaging --stat`, `switch -c feature/web-migration-w0 origin/develop`; GitHub read-only PR #10 and open-PR search; `node --version`, `npm --version`; Python `-B` AST and file-size inspection; SQLite URI `mode=ro` + `PRAGMA query_only=ON` for table/version metadata. No application bootstrap or migration function was invoked against user data.

W0 test result and final publication evidence are recorded in the completion section below. Prior 219 M0–M4 / 244 M5 real-model results are historical evidence in milestone reports, not newly executed W0 tests. Frontend/API E2E, new security controls, migration execution, performance benchmarks and clean-Windows qualification are NOT TESTED in W0.

### W0 verification completion

Executed `python -B -m pytest --collect-only -q -p no:cacheprovider` with explicit ignores for the four `test_m*_real.py` files: **215 tests collected**, exit0, 1.07s on the final retry. No test function/inference/render was executed. First collection exited0 but an interpreter finalizer emitted a sandbox OS-temp PermissionError; retry with TEMP/TMP pointing to existing ignored `storage/temp` completed cleanly. This is collection evidence only, not “215 tests passed”.

Offline ORM DDL compilation covered **17 approved tables plus the separate eighteenth M5 table**; AST extraction recorded callable signatures/line numbers from immutable refs without running their functions. Read-only PRAGMA table_info/foreign_key_list/index_list verified four existing profiles; approved-table column-name sets match source in each (zero mismatches). This does not prove full data integrity or migration compatibility.

Documentation checks verify all eight required files, internal document links, source-path/callable inventory anchors, no binary/private payloads and whitespace; runtime tracked trees are identical to approved develop. Publication uses a single docs-only Conventional Commit and a Draft PR to verified develop. Actual commit/PR IDs are returned in the final handoff and PR metadata rather than embedding a self-referential commit SHA in its own content.

## Navigation

- [Architecture](WEB_ARCHITECTURE.md)
- [Implementation plan](WEB_IMPLEMENTATION_PLAN.md)
- [Service reuse matrix](WEB_SERVICE_REUSE_MATRIX.md)
- [API contract](WEB_API_CONTRACT.md)
- [Security threat model](WEB_SECURITY_THREAT_MODEL.md)
- [Database and storage migration](WEB_DATABASE_MIGRATION_PLAN.md)
- [W1 backlog and approval gate](W1_IMPLEMENTATION_BACKLOG.md)
