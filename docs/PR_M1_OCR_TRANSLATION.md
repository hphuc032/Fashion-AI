# feat(m1): add Chinese OCR and offline translation review

Base: develop · Head: feature/m1-ocr-translation

An uploaded video can now be sampled for embedded Chinese captions, grouped into timed text segments, translated offline to Vietnamese, edited and reviewed in the existing Streamlit application. The original video and M0 project data are preserved. This is M1 only; it does not remove/replace video text or add speech/rendering functionality.

## Implementation

- Bounded incremental FFmpeg/OpenCV extraction (default 1 s, cap 300, longest side 1280), SHA-based frame cache, display-oriented original-space bounding boxes and raw polygons.
- PaddleOCR 3.3.2/PaddlePaddle CPU 3.2.2 with PP-OCRv5_mobile_det + mobile_rec; no optional document/orientation/VL models. Raw mixed-language/low-confidence detections remain inspectable; only eligible CJK segments get translation rows.
- Conservative temporal/text/IoU association with one-to-one matching and number/Latin-identifier changes protected from merging.
- Manual default plus working offline Argos 1.9 zh→en→vi packages via CTranslate2/SentencePiece; four explicitly documented exact fashion terminology entries. Persistent provider/version/context cache, bounded retries/timeouts/character budget. No cloud credentials or silent fake translation.
- Additive SQLite migration and pre-upgrade backup, raw detections/segments/jobs/cache, FK/state constraints. No changes to M0 projects schema/data. Transactional human edits with revision conflict checks.
- Exclusive persisted background job slot, disposable worker subprocesses, status/progress, cancel/deadline/crash recovery. OCR and translation in separate processes avoid observed Windows native DLL conflicts. Failure/cancel keeps previous reviewed output.
- Vietnamese OCR page with paged editor, selected-segment translation, approve/reject, time/box edits and diagnostic frame preview. Pinned NumPy/PyArrow/pandas stack validated for populated tables.

## Verification

Develop baseline: 806c114c19066115cdc38d3894281271e23da9d2, fetched and verified before development. Main and existing v0.1.0 untouched.

**87 tests passed in 26.28s, zero skipped/errors/failures**, Python 3.11.18 on Windows with real FFmpeg/FFprobe and M1_RUN_REAL=1. Breakdown: original 26 M0 tests, 60 deterministic M1 tests, 1 real-model production worker end-to-end/cancel test. Mock-based tests do not claim OCR accuracy. Supervisor regression also protects the winning job from duplicate-launcher exit races.

Real fixture: 6 seconds, 540×960, 25 fps, synthetic Chinese captions → 18 raw detections → 3 logical Chinese segments. Offline neural inference for 我喜欢这件衬衫 returned Tôi thích cái áo này.; manual edit/approval/reopen and real worker cancellation preserve results/source bytes. Existing local M0 DB: all 1 project row unchanged, automatic backup created. Independent clean runtime resolved 91 packages with no Torch/spaCy/Stanza/Argos library.

Actual Brave verification: upload, OCR progress, translation selection, manual correction/approval, reload persistence, diagnostic boxes. Screenshots/models/fixtures/databases remain ignored locally. Detailed evidence: docs/M1_TEST_REPORT.md and docs/IMPLEMENTATION_LOG.md. CI runs original M0 gate and deterministic M1 suite without model downloads; hosted results will be reported after this push.

Hosted PR checks on aac14d6 passed: [run 41970476863](https://github.com/hphuc032/Fashion-AI/actions/runs/41970476863), both m0-tests and m1-tests with no-skip count gates. PR #2 remains open for owner review. The final documentation-only handoff commit does not alter the verified application, tests or CI definition.

## Acceptance and limitations

- [x] M0 regression suite remains green; select/upload existing projects.
- [x] Start persistent OCR job, detect Chinese, store time/boxes/raw confidence.
- [x] Group representative duplicate captions without merging changed prices/IDs.
- [x] Generate Vietnamese via actual offline provider, edit/approve/reject and reopen.
- [x] Preview diagnostic boxes, reject invalid input, preserve existing M0 DB.
- [x] Full automated suite and real-model E2E/cancellation passed.
- [ ] Owner M1 acceptance and integration approval (pending).

Argos pivot translation is not reliably faithful for arbitrary captions: 这件衬衫很舒服 produced Áo đẹp đấy.; browser review corrected it to Áo sơ mi này rất thoải mái. All automatic output is pending review. Brands, codes, prices and material claims need human verification. No general accuracy guarantee, commercial corpus benchmark or GPU/Traditional-Chinese validation. Timestamp precision is sampling-level, VFR/moving/occluded captions can need denser samples/manual edits. Disk caches may accumulate. Local trusted single user only.

Scope stops at reviewable text data/diagnostic stills. No removal/overlay on final video, ASR, dubbing, subtitles, exports, scraping or posting. This PR is prepared for review only: **do not merge, tag v0.2.0, modify main or begin M2 without approval**.
