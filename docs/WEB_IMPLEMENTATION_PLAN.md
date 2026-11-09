# W0 — Incremental Web implementation plan

Status: **PROPOSED**. W0 delivers documentation only. Source findings and actual command evidence: [repository audit](WEB_REPOSITORY_AUDIT.md). W1 coding requires explicit owner approval; no milestone estimate is an implementation result.

## Sequenced roadmap

| Milestone | Scope and reuse | Dependency / exit gate |
|---|---|---|
| W0 | Eight documents, exact Git/schema/service audit, API/threat/storage design | Owner approves architecture and W1 backlog; no runtime changes |
| W1 | Next/FastAPI foundations, typed health client, local session/CSRF/Host/CORS, Windows lifecycle, isolated tests | Both services loopback-only; health shown; bad Origin/Host/session rejected; no DB migration or AI jobs |
| W2 | Paginated project metadata, atomic source import, managed streaming preview, rights data, safe archive semantics | Project persists after restart; source SHA unchanged; duplicate upload safe; copied legacy DB compatible |
| W3 | OCR/Argos/manual review, durable idempotency seam, job facade, WS/polling, recovery/cancel/retry | Real local OCR/translation through API; revisions/conflicts preserved; two-click/restart/cancel tests |
| W4 | ReplacementSettings/editor, same compositor preview, render queue and M2 contracts | Actual localized MP4; no source mutation; stale review/tracking gates enforced |
| W5 | Speech editing, speaker voices, ASR/translation/local TTS/assemble and audio preview | Real local ASR/TTS; timeline and full listening review; explicit Azure consent if used |
| W6 | Existing ASS/final mux/validation/export history, matching preview gate, range/download | Actual H.264/AAC MP4 and ASS; plays, downloads, persists after restart; all current artifact contracts enforced |
| W7 | Complete Playwright E2E, adversarial API suite, copied-data migration/backup/recovery, resource measurement and Windows qualification | All legacy+Web gates pass, owner acceptance, separate release approval |

M5 remains separate. W1 works from approved M0–M4 without depending on PR #10. Later reuse of M5 model management/backup needs a reviewed integration decision and v60 compatibility tests, not a silent merge. Keep Streamlit and the existing portable app usable until Web acceptance.

## Differences from initial plan and resolutions

- Root `app` is a working engine package; retain it, name API package `fashion_api`. No mass move to `engine`.
- Actual DB has specialized jobs and schema versions 1/20/30/40/50, with optional 60 in M5. Normalize in DTOs, preserve native state CHECKs and IDs.
- Import creates Project and source atomically. Don't create empty projects against current non-null model. W2 uses multipart POST projects; add drafts only if a later concrete UX requirement warrants a migration.
- Actual speech and OCR segments are distinct entities and review workflows. API has separate resources, never translates one into the other's table.
- Current APIs are Python callables, not REST endpoints. Authentication/CSRF/Host middleware, pagination, idempotency map, uniform retry, opaque media routing and browser E2E are new work.
- `%LOCALAPPDATA%\FashionAI` is a new profile layout, not the M5 current path. W1 only validates configuration; real relocation is explicit copied-data work after approval.
- Background separation, arbitrary translation semantic certification and universal soft-subtitle styling are not supported capabilities. Expose limits; don't market them as Web improvements.

## Change and release discipline

W0 branch starts at verified remote develop `51f1283`; commits include only the eight requested Markdown documents. Push normally and open a Draft PR to develop; do not merge. Before each future milestone, re-fetch and inspect develop and M5 PR, do not assume the W0 snapshot remains current. Keep feature PRs small and Conventional Commits; preserve branch history; never force-push shared refs or write directly to main/develop. Releases and merges require owner approval.

W1 begins on a separate feature branch after W0 approval. Prefer merging approved W0 docs before that branch, or explicitly select the documented baseline. Re-run baseline regression after dependency or application changes; docs-only W0 does not require generating new AI/media outputs. W0 verifies documentation, source/schema evidence and unchanged runtime tree.

## Test strategy and evidence rules

Legacy suite commands (PowerShell, from repository root; select `.venv-m1-clean\Scripts\python.exe` on this machine):

```powershell
& .\.venv-m1-clean\Scripts\python.exe -m pytest tests/test_m0.py tests/test_dashboard.py -q
& .\.venv-m1-clean\Scripts\python.exe -m pytest tests/test_m2.py -q
& .\.venv-m1-clean\Scripts\python.exe -m pytest tests/test_m3.py -q
& .\.venv-m1-clean\Scripts\python.exe -m pytest tests/test_m4.py -q
# Full deterministic suite: exclude tests/test_m*_real.py explicitly.
& .\.venv-m1-clean\Scripts\python.exe -m pytest -q --ignore=tests/test_m1_real.py --ignore=tests/test_m2_real.py --ignore=tests/test_m3_real.py --ignore=tests/test_m4_real.py
# Opt-in full real-model run, only in an authorized disposable QA profile:
$env:M1_RUN_REAL='1'; $env:M2_RUN_REAL='1'; $env:M3_RUN_REAL='1'; $env:M4_RUN_REAL='1'
& .\.venv-m1-clean\Scripts\python.exe -m pytest -q
```

These are documented future regression commands, not claimed W0 runs. On M5 branch add `tests/test_m5.py` (24 deterministic tests) and opt-in `M5_RUN_REAL=1`; those files are absent on approved develop. Existing CI workflow `.github/workflows/m0-tests.yml` has five suite gates on develop (26/79/31/38/41); M5 adds a sixth independently. Real-model flags require installed model paths and fixture-generation prerequisites; do not label a skipped real suite as acceptance.

W1 tests: isolated health/no-live-DB API tests; exact-origin/Host/DNS-rebinding/CSRF/auth failures; frontend typed client offline/error states; Playwright health/restart flow; owned-process lifecycle/port collisions. W2–W6 add contract tests against existing services and source hashes, copied DB migration, native subprocess cancellation and genuine local model execution. Full E2E at W7 follows upload→OCR→review→M2→ASR/TTS→preview→final→download→restart; retain real playback/listening acceptance separately from automated metadata checks.

## Approval and unresolved decisions

Recommend approving W1 as health/security/runtime only, with root `app` retained, `fashion_api` naming and direct authenticated browser→API transport. Confirm whether a future live-data profile should adopt existing M4 or M5 storage; no selection/migration happens in W1. Approve any later M5 component integration separately. Exact new Web dependency pins are a W1 preflight resolution gate against current Python pins; no working AI dependency upgrades are authorized by this architecture. Clean-machine portable qualification and Web benchmarks remain outstanding and must not be waived implicitly.
