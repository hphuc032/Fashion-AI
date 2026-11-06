# M1 verification report — 2026-11-05 (Asia/Saigon)

## Baseline and environment

Feature branch created from latest fetched approved origin/develop **806c114c19066115cdc38d3894281271e23da9d2**. Main remains a3d2e63 / v0.1.0. No M1 merge/tag/M2 authorized or performed. Owner later authorized verified feature push and PR to develop.

Windows, Python 3.11.18, FFmpeg/FFprobe 9.0.2, 20 logical CPUs, 15.7 GiB system RAM; CPU inference with configured 2 threads, one active job per DB. Primary dependencies pinned in requirements-m1.txt. Independent .venv-m1-clean install/sync resolved 91 packages, with no Argos library, Torch, spaCy, Stanza or document OCR extras.

## Files and architecture changes

- Modified: .env.example, .gitignore, requirements-m1.txt (new dependency file), app/core/config.py, app/database/session.py, app/ui/dashboard.py, .github/workflows/m0-tests.yml, README.md, docs/IMPLEMENTATION_LOG.md.
- New schema: app/database/m1_models.py, app/database/migrations.py.
- New providers: app/providers/__init__.py, app/providers/ocr/{__init__,paddle_provider}.py, app/providers/translation/{__init__,base,argos_provider}.py.
- New services/worker: app/services/{frame_extractor,text_tracker,translation_service,ocr_repository,ocr_service,job_manager}.py and app/worker.py.
- New UI: app/ui/ocr_page.py, app/ui/translation_editor.py.
- New scripts: scripts/setup_m1_models.py, scripts/generate_m1_fixture.py.
- New tests: tests/{__init__,conftest,test_frame_extractor,test_job_manager,test_m1_integration,test_m1_real,test_m1_ui,test_ocr_service,test_text_tracking,test_translation}.py. Original M0 test files unchanged.
- New docs: docs/M1_IMPLEMENTATION_PLAN.md, docs/M1_TEST_REPORT.md, docs/PR_M1_OCR_TRANSLATION.md.

Dependencies are lazy at the model boundary. Original upload/storage/video services remain unchanged. The only M0 persistence entry-point change calls the additive migration instead of unversioned create_all.

## Executed tests (actual results)

| Run | Result |
|---|---|
| Approved M0 baseline before M1 | 26 passed in 1.78s |
| Early deterministic suite | 73 passed, 1 failed, 1 skipped; failure was expired SQLAlchemy fixture object, corrected |
| Early expanded UI suite | 78 passed, 1 failed, 1 deselected; Streamlit test cache leaked settings between AppTests, corrected |
| Independent clean full run before runtime isolation fix | 80 passed, 1 failed; in-process Paddle/CTranslate2 DLL conflict discovered |
| Real production worker flow after isolation | 1 passed in 15.93s; 18 detections, 3 segments, edits/reopen verified |
| Complete suite before final concurrency review | 86 passed in 28.80s; zero skips |
| **Final complete suite with M1_RUN_REAL=1** | **87 passed in 26.28s; 0 failures/errors/skips** |

Final suite consists of **26 unchanged M0 tests + 60 deterministic M1 tests + 1 real-model integration test**. It includes a final supervisor regression: a duplicate launcher's exit cannot fail the owning/winning worker. The final JUnit real test took 18.068s including fixture creation, worker startups, OCR, neural translation, edit/approval, cancellation and database reopen. This is a controlled fixture measurement, not a general accuracy/speed benchmark. Peak RAM was not measured.

Command (with real FFmpeg/FFprobe paths in environment):

```powershell
$env:M1_RUN_REAL='1'
.\.venv-m1-clean\Scripts\python.exe -m pytest -q --tb=short --junitxml=storage/temp/m1-final.junit.xml
```

Deterministic tests use mocked OCR/provider outputs for control flow, output normalization, low confidence/mixed CJK, conservative temporal/spatial grouping, cap/caching/invalid frame handling, rotation mapping, retry/cache/timeout, raw detections, review persistence/stale revisions, foreign keys, migration backup/data preservation, job exclusivity/cancel/crash recovery and populated Arrow-backed Streamlit editor. They make no OCR accuracy claim. Real M0 FFprobe test runs too, not skipped.

## Real OCR and translation

Generated 6-second silent H.264 540×960 / 25 fps fixture with two Chinese regions and one English/numeric region; main caption changes at 3s. Actual PaddleOCR v5 mobile produced **18 raw detections and 3 Chinese logical segments**. Expected 男生穿搭 and 秋冬新款 recognized; ABC 123 retained raw and excluded from translation. Coordinates mapped to 540×960, timestamps bounded by video duration, repeated captions grouped.

Offline Argos zh→en→vi packages (1.9), executed via CTranslate2 4.8.5 + SentencePiece 0.2.2. Known exact phrases use the explicitly documented four-entry curated terminology table. Bypassing that table for 我喜欢这件衬衫 yielded **Tôi thích cái áo này.**, demonstrating real neural inference. Automated translations stay pending. Manual Unicode Vietnamese edit/approval persisted after disposing/reopening SQLite. Original imported bytes unchanged. An actual new OCR worker was cancelled; previous approved result and original file survived.

Downloaded archives: OCR det 4,935,680 B; OCR rec 16,834,560 B; Argos zh_en 74,481,402 B; en_vi 67,770,159 B. Extracted model directories including manifests: det 4,923,879 B; rec 16,824,996 B; zh_en 86,138,235 B; en_vi 79,380,592 B. No weights, archives or fixtures tracked in Git.

## Browser and existing-data verification

Actual Brave UI on localhost:8502 with isolated storage/m1-demo: uploaded synthetic video; launched real background OCR; observed persisted 6/6 frame progress; selected three segments and translated through worker; edited and approved a sentence in the data editor; reloaded page and confirmed edit/approval persisted; inspected frame boxes, raw confidence and English-only exclusion. Server was also restarted and prior OCR results remained. Actual screenshots are local ignored docs/screenshots/m1-review.jpg and m1-boxes.jpg.

Browser test exposed PyArrow 26's NumPy >=2 requirement; fixed via PyArrow 19.0.1/pandas 3.0.6/NumPy 1.26.4 and added populated-editor regression coverage. Clean runtime test exposed DLL conflicts if Paddle and CTranslate2 share a Windows process; real tests now exercise the production separate-process architecture, which passed. CPU/GPU bypass flags were not used to suppress native failures.

Migrated the existing local M0 fashion_ai.db using the same production migration function; compared all projects rows before/after: **1 existing row unchanged**, one consistent pre-M1 backup created. Unit legacy DB fixture also confirms original projects columns and records unchanged and backup not repeated on reopen. No database recreation or deletion.

## Acceptance

| Criterion | Result | Evidence |
|---|---|---|
| M0 remains operational | PASS | All original 26 tests + browser upload/preview metadata |
| Select existing video and start OCR | PASS | Browser real worker launch |
| Chinese detected in video | PASS | Real PaddleOCR fixture, 18 raw detections |
| Persist timestamps/boxes/raw diagnostics | PASS | DB assertions and browser frame inspector |
| Repeated captions grouped | PASS | Real 3-segment fixture + distinct/spatial/gap/numeric-change tests |
| Working Vietnamese translation provider | PASS | Real Argos inference + explicit exact fashion terminology |
| Edit and approve/reject | PASS | Transactional tests and browser manual correction/approval |
| Reopen preserves results | PASS | DB reopen tests, browser reload/server restart |
| Bounding boxes preview | PASS | Actual browser image with diagnostic rectangles |
| Invalid input fails clearly | PASS | Frame/provider/path/size/state tests; errors sanitized |
| Existing M0 data preserved | PASS | Actual pre/post row equality + backed-up legacy schema test |
| Automated tests | PASS | 87/87, zero skips |
| Controlled Chinese video + translation E2E | PASS | Actual models and production worker processes |
| Cancellation keeps reviewed output | PASS | Real worker cancellation + deterministic tests |
| GPU, Traditional Chinese, vertical glyph layouts | NOT TESTED | CPU simplified horizontal fixture only |
| Broad real-world OCR accuracy / long clips / VFR timing | NOT TESTED | No representative corpus benchmark |
| General neural translation faithfulness | LIMITED | Known mistranslation observed; mandatory human review |

## Limits and owner review

Argos pivot quality is variable: 这件衬衫很舒服 produced **Áo đẹp đấy.**, which is not faithful; browser review corrected it to **Áo sơ mi này rất thoải mái** and approved the manual edit. This limitation is disclosed in UI/README; no claim of universal translation accuracy. Brand names/product IDs/prices/material claims require human verification. No automatic claim checking or product matching.

Sampling timestamps identify requested source positions with interval-level accuracy; not exact per-frame PTS or full temporal tracking. Moving/obscured captions may split/miss; tune interval and edit. Low-confidence raw text remains available; empty OCR is a valid result. Frames are cached but caches can accumulate on disk. Deadline/lease ends orphan/dead jobs; retry requires explicit action. Single local trusted user, no cloud deployment. No Chinese text removal, overlays in output video, ASR/dubbing/subtitles/render/export/M2.

Functionality is verified in the scope above and ready for owner review; owner M1 acceptance, integration and v0.2.0 remain pending. GitHub PR/branch URLs and exact final commits are reported in handoff after publication.

## Published feature / hosted checks

Branch: https://github.com/hphuc032/Fashion-AI/tree/feature/m1-ocr-translation. Review PR: https://github.com/hphuc032/Fashion-AI/pull/2 (base develop; open, unmerged). Hosted run https://github.com/hphuc032/Fashion-AI/actions/runs/41970476863 on aac14d6 passed both m0-tests and m1-tests, including explicit no-skip count gates. Model E2E remains local-only; CI does not claim real OCR accuracy. Final documentation-only handoff commit preserves all tested application/test/CI files. No force-push/main change/merge/tag/M2.
