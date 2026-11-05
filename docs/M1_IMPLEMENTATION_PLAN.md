# M1 — Chinese OCR and translation plan

## Baseline and scope

Inspected M0 source, tests, README, full AGENT_MVP_SPEC, M0 plan and implementation log before code. Branch feature/m1-ocr-translation starts at fetched approved origin/develop 806c114c19066115cdc38d3894281271e23da9d2. Main remains unchanged. M1 is detection, translation and review only: no removal, overlay export, speech or M2. Owner's workflow update authorizes verified feature push and PR to develop, never merge/tag.

## Architecture and modules

Keep M0 upload/database/UI interfaces. Add frame_extractor (bounded sequential FFmpeg extraction + OpenCV image validation), OCR provider (PaddleOCR 3 adapter), text_tracker (text/spatial/temporal grouping), translation provider interface + offline Argos and manual adapters, persistent jobs (one subprocess worker globally), review repository and Streamlit OCR page. Worker process isolates model imports, bounds runtime and permits cancellation; SQLite records survive page reruns. UI never parses vendor OCR structures.

## OCR/model and frame sampling

Use pinned PaddleOCR 3.3.2/PaddlePaddle 3.2.2 CPU, PP-OCRv5_mobile_det + PP-OCRv5_mobile_rec, disabled orientation/unwarping extras. Initialize once per worker. Download only these models explicitly during setup; actual inference should use configured local model paths. Traditional coverage depends on the multilingual Chinese v5 model; verify separately from simplified fixtures.

Default one sample per second, configurable minimum 0.1 seconds, cap 300 frames, OCR image longest side 1280, one job at a time, 2 CPU threads. FFmpeg seeks a target source timestamp and returns one frame at a time. Store requested source time (sampling precision is bounded by source frames; not frame-perfect tracking). Map detections from resized images to display-oriented original dimensions, store original-space [x,y,w,h] plus original width/height and polygon. Frame cache keyed by source SHA256 + sampling/preprocess version + time; validate cached dimensions. Original video remains unchanged. Cache/model/media paths restricted to managed storage.

## Grouping

Raw detections are retained including English-only/numeric-only regions; only CJK-containing text becomes a translation segment. Match normalized text conservatively (default similarity .94), IoU >= .3, adjacent samples, one-to-one per frame; reject numeric/Latin identifier changes even when overall text is similar. Use best-confidence observation as representative text/box; retain detection associations. Timing is approximate sample intervals clipped to video duration; text disappearing/reappearing beyond gap produces separate segments. Low-confidence rows are marked for review; extremely low scores below configured threshold excluded from segments but retained raw.

## Translation

Default manual (no network/cost). Working optional Argos CPU offline provider uses explicitly installed zh→en and en→vi packages, since official index has no direct zh→vi package. Only two packages are needed, quality loss from pivot is documented. Optional curated exact fashion terminology dictionary improves known phrases; never substitutes text for unknown failures. Cache key includes normalized text, context, provider and installed model versions. Provider errors remain visible; bounded attempts/backoff/timeouts, selected-segment regeneration only, all auto results pending review. Manual edits/approval are transactional and protected from stale job writes. No cloud text transmission or API keys required; provider interface allows later configured cloud adapters.

## SQLite migration and jobs

Add schema_migrations, ocr_jobs, ocr_detections, text_segments, translation_cache. Migration 1 only adds tables/indexes/constraints in a transaction, leaving projects schema/data untouched; use explicit migration marker and SQLite backup API for existing on-disk database before upgrade. Foreign keys to projects, indexed project/time queries, check constraints for state/confidence/coordinates/review status. One active job enforced by partial unique index across all projects; queue/retry use fresh UUID and existing outputs survive failure. State transitions NOT_STARTED (no row), QUEUED, PROCESSING, COMPLETED, FAILED, CANCELLED; persist completed/total counts and sanitized errors. Worker lease/heartbeat and owner PID protect against duplicate workers; process stop/restart reclaims stale work safely. Commit detections/segments atomically only when successful; failed/cancelled runs never erase edited rows. OCR rerun with existing segments requires explicit acknowledgement in UI.

## UI

Add Nhận diện & Dịch to current sidebar, select existing project, configure sampling, start/cancel jobs, periodic status refresh, retry errors. Editable grid: selection, Chinese source, Vietnamese, timestamps, original-space box, confidence, pending/approved/rejected. Save per-line edits and review status, translate selected pending/rejected lines, protect approved/manual rows. Frame preview draws diagnostic boxes in original dimensions and displays source timestamps; no source video rendering.

## Errors/resources

Validate UUIDs, paths and source hash, enforce input size/duration as M0, target frame count/resolution, local model paths, single worker process, global job timeout and per-frame extraction timeout. Log only job/project identifiers and error classes. Missing models/provider packages get actionable Vietnamese error; manual route remains usable. Caches and downloadable models are ignored. Cancellation is cooperative between frames plus process termination fallback for stuck native inference, never against original source files.

## Testing and acceptance

First rerun all 26 M0 tests. Add meaningful unit tests for timestamp/cap/portrait/cache/error logic, OCR normalization/multiple regions/mixed CJK/low confidence/missing model, dedup/spatial/gap/similar differing captions, providers retry/cache/timeouts, DB constraints/migration preservation/review edits, worker success/failure/cancel/restart/reruns. Mock AI only in unit tests; separate opt-in real OCR + real offline translation smoke test uses generated Chinese fixture, saves edited Vietnamese, approves, reopens DB and verifies source unchanged. Validate browser OCR launch/progress/grid/frame preview when environment supports it. Update CI to keep M0 26-test gate separate and run M1 deterministic tests without model downloads; real model test explicitly opt-in.

Completion requires all M0 and M1 automated tests pass, real PaddleOCR detects a controlled Chinese video, actual Argos generates Vietnamese, edits and reviews persist, existing M0 DB preserved, invalid/cancel/retry flows tested, tracked-file audit clean. Mark unverified criteria NOT TESTED and never claim real accuracy from mocks. Record measured timing and model sizes only after execution. Pin additional versions after resolver/install smoke verification. Deliver README, .env.example, implementation log, M1_TEST_REPORT, Conventional Commits, verified feature push and PR (no merge/tag/M2).
