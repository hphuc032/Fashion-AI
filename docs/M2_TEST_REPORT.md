# M2 verification — 2026-11-05

Approved baseline: `origin/develop` **bb4b94a510cce6f8eedd4393132fdababf444f48**, merge of M1 PR #2. M2 branch: `feature/m2-text-replacement`. Smart Review remains independent PR #3; its shared migration/edited-approval fix is reused as `6bd5ab6`. No main modification, merge, release, tag or M3.

## Results

Windows, Python 3.11.18, CPU, FFmpeg/FFprobe 9.0.2, pinned requirements-m2.txt. Final complete run: **119 passed in 54.45s**, zero failures/errors/skips. Breakdown: **26 M0 + 60 deterministic M1 + 1 real M1 + 31 deterministic/real-FFmpeg M2 + 1 real M1→M2**. JUnit is local ignored `storage/temp/m2-final-results.xml`.

Real complete worker test independently passed in 27.92s; measured M1→M2 portion 24.16s (includes worker startups, OCR, translation, approval, preview, render and cancellation/reopen), output 76,890 bytes. Synthetic original 540×960, 25 FPS, 6 seconds with Chinese text and AAC sine tone. Paddle mobile OCR → Argos offline → approved `Phối đồ nam` → before/after → H.264 MP4 with AAC. FFprobe: **540×960, 6.0s**. Source/output AAC packet SHA256 arrays match exactly; audio packet PTS arrays match within 1/48000 second. Source bytes unchanged. Cancellation after worker enters PROCESSING preserves previous output; reopened DB retains completed history. These are controlled-fixture results, not a performance or quality benchmark.

Four actual 320×240 exports separately exercise solid, blur, OpenCV inpaint and overlay, each preserving AAC packets and source bytes. Additional actual exports verify VFR normalization and 30000/1001 FPS with 90° display rotation. Pixel assertions check composition outside selected regions before lossy encoding. Frame clock uses exact rational normalized FPS; VFR retains presentation duration within max(0.12s, 2 normalized frames), not the original varying frame cadence.

UI: actual Brave at localhost:8503 using existing isolated synthetic M1 project. Loaded three approved segments, saved first segment configuration, observed Chinese→Vietnamese before/after, changed synthetic source rights from unknown to owned, confirmed licensed source/caption regions, launched render, saw COMPLETED history and Tải MP4, clicked download, and played the output. Browser metadata: readyState=4, duration=6, width=540, height=960, error=null; playback paused=false/currentTime=1.3046. Browser fixture is silent; audio is verified by the separate real worker test above. Ignored local screenshots: `docs/screenshots/m2-preview.jpg`, `m2-export.jpg`.

Migration on actual demo DB made `app.pre-v30-b4a7b412.db`; compared against backup: **3 text_segments, 18 ocr_detections, 2 segment_reviews and 2 review_events unchanged**. Versions 1,20,30 coexist. Source rights were then explicitly updated through UI; replacement configuration/history are new separate records. Existing M0/M1 legacy-migration and data-preservation tests pass.

Earlier validation: 25 initial M2 tests passed; first complete run had 115 pass/1 fail because FFmpeg 9 no longer wrote rotation via old metadata option. Fixture now uses input `-display_rotation 90`; rotated output verified. Actual first-use UI found a default integer opacity rejected by Streamlit's float slider; fixed default/coercion and expanded AppTest to cover no saved configuration. Subsequent complete run 118 passed; final 119 adds provider-boundary coverage. No failure was treated as success.

## Acceptance matrix

| Criterion | Status | Evidence / scope |
|---|---|---|
| M0/M1 functional | PASS | All 87 existing tests including real models |
| Existing approved translations; rejected excluded; pending explicit | PASS | Repository tests and populated Studio |
| Accurate intended boxes, moving/static/multiple/fractional intervals | PASS | Interpolation/pixel/timeline tests; sparse samples block until reviewed |
| Selectable removal modes | PASS | Four real FFmpeg exports and Studio selector |
| Vietnamese Unicode and missing glyph handling | PASS | Verified system cmap, wrapping/fallback tests and browser `Phối đồ nam` |
| Adjustable placement/style and collision warnings | PASS | Separate config, controls, fit/collision/boundary tests |
| Before/after preview | PASS | Actual UI and real E2E; same compositor |
| Valid final MP4 | PASS | Actual UI + 6 real FFmpeg mode/timeline fixtures + worker E2E |
| Original audio preserved/synchronized | PASS | AAC packet hashes and PTS; other codecs use documented policy |
| Duration/dimensions/FPS/orientation | PASS | FFprobe, 540×960/6s and rational FPS/rotation/VFR tests |
| Persistent jobs/configuration/reopen | PASS | SQLite E2E, dead-worker recovery, constraints, idempotency tests |
| Failure/cancel does not corrupt originals/prior outputs | PASS | Cleanup/stale snapshot/cancel tests and real E2E |
| Windows CPU, no mandatory GPU | PASS | Entire run Windows CPU, local models |
| All existing/new tests and original synthetic E2E | PASS | 119/119 zero skipped |
| General complex-scene removal quality, optical flow, long-video peak RAM | NOT TESTED | No broad quality/throughput/memory benchmark claimed |
| Windows 10 specifically / GPU / arbitrary audio codecs | NOT TESTED | Tested current Windows host and AAC; fallback AAC policy implemented |

## Reproduce on Windows PowerShell

From repository root, install Python 3.11 and FFmpeg/FFprobe with libx264; FFmpeg 6.1+ is used by rotation test. Do not commit local runtime or models.

```powershell
py -3.11 -m venv .venv-m2
.\.venv-m2\Scripts\python.exe -m pip install -r requirements-m2.txt
Copy-Item .env.example .env  # only for a new setup; preserve existing .env
# Set FFMPEG_PATH/FFPROBE_PATH in .env when the tools are not on PATH.
.\.venv-m2\Scripts\python.exe scripts/setup_m1_models.py --ocr --translation
$env:M1_RUN_REAL='1'
$env:M2_RUN_REAL='1'
# Windows uses WINDIR/Fonts/msyh.ttc for the synthetic Chinese fixture.
# Else set M1_CHINESE_FONT to a licensed CJK font file.
.\.venv-m2\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:M1_RUN_REAL,Env:M2_RUN_REAL
.\.venv-m2\Scripts\python.exe -m streamlit run app/main.py --server.address 127.0.0.1
```

Actual verification used existing `.venv-m1-clean\Scripts\python.exe` and explicit absolute portable FFmpeg/FFprobe environment paths. Without opt-in flags two real-model tests skip visibly; run deterministic M2 alone with `python -m pytest tests/test_m2.py -q`. CI installs CPU dependencies/FFmpeg/DejaVu font, runs separate M0/M1/M2 gates and does not download models. Hosted CI results are recorded after publication.

## Limits and operation

OpenCV Telea is basic local ROI inpainting; moving/complex textures can smear. Preview and manual inspection remain necessary. No optical flow or deep inpainting is claimed; associated sampled M1 boxes interpolate only over supported gaps, otherwise explicit acknowledgement/manual override is required. OCR sample boundaries can need timing correction. Two overlapping translated boxes block output instead of hiding text. Each enabled segment is explicit configuration; unconfigured approved segments remain unchanged.

System Arial/Segoe UI (Windows WINDIR) or Pillow-resolvable DejaVu Sans; no redistributed font. Every character's cmap is checked, missing glyph/too-small layout blocks export, no silent truncation. Text fit shrinks within its configured box. VFR is normalized to rational average FPS; even display dimensions required for yuv420p. AAC/MP3/ALAC audio stream copied, other first audio streams transcoded AAC. Additional audio/subtitle streams are not exported. Nonzero/negative-start or unusual codec timelines beyond AAC fixture are not comprehensively benchmarked.

One active render globally per DB; OCR/delivery queues exclude concurrent rendering. Worker PID/module/job ownership checked before termination; deadline/cancel stops child FFmpeg. Frames stream sequentially, no whole uncompressed video in RAM; no peak RAM measurement claimed. Preview output PNG cache bounded by PREVIEW_CACHE_ENTRIES; inherited M1 source-frame cache may accumulate on disk. Completed MP4s/worker logs retained for review, no auto-delete of user media. Power loss between rename/DB commit can leave an orphan UUID export, never mark an unvalidated partial completed. User must confirm source rights and permitted caption regions; no attribution/watermark-specific automation.

## Changed files

Shared migration/review safety: `app/database/migrations.py`, `app/services/ocr_repository.py`. M2 schema/settings: `app/database/render_schema.py`, `app/core/config.py`, `.env.example`, `requirements-m2.txt`. Composition: `text_layout.py`, `text_compositor.py`, `inpainting_provider.py`. Persistence/preview/export: `replacement_repository.py`, `render_preview.py`, `video_renderer.py`, `render_jobs.py`, `app/render_worker.py`, OCR queue guard in `ocr_service.py`. UI: `app/ui/replacement_studio.py`, `dashboard.py`. Tests: `tests/test_m2.py`, `test_m2_real.py`, workflow. Documentation: plan, this report, README and implementation log. All service paths are under `app/services/`.
