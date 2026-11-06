# M4 verification and delivery

Approved base: `3809a4cd71a60d3ecf4a1e5c9ca84ec265b78936` (develop, merged M3 PR #5; M2 PR #4 already integrated). Working tree was clean. Plan committed before application code as `bb694fb`. Baseline actual-model M0–M3 run: **177 passed in79.00s**. Main remains unchanged. M4 feature PR must not be merged or tagged without owner approval.

## Architecture and files

New `app/database/final_schema.py` adds version50 subtitle_files/final_render_jobs/final_exports. New services: `replacement_contract.py` reads validated M2 output; `final_render_config.py` validates styles/presets; `subtitle_service.py` produces ASS; `video_mux_service.py` streams FFmpeg; `final_output_validation.py` verifies media; `final_render_service.py` orchestrates jobs/preview/library; `final_job_manager.py` supervises disposable `app/final_worker.py`. New UI `app/ui/final_export_studio.py` is linked from existing dashboard. Settings/workload guard integrate M4 without duplicating OCR/translation/TTS/masking. Requirements-m4 inherits pinned M3. Tests, CI, env template, README, plan and implementation log accompany these changes.

Strict project/path/job/source SHA/revision/config contracts reject missing, cross-project, stale or incomplete inputs. Only completed M2 and approved M3 are used. Publication rechecks source and review/config under a SQLite write lock. UUID staging and atomic rename preserve previous exports and source files. One heavy job across milestones; idempotent requests, cancellation, lease/PID recovery, bounded preview cache and reversible export trash. Final output contract includes filename/path/size/SHA/duration/resolution/aspect/codecs/subtitle mode/language/audio sync/probe/config/export timestamp.

## Subtitles, mux and validation

ASS v4+ UTF-8 uses approved M3 speech only, never OCR promotional captions. Original fractional timestamps are retained in reports and quantized within10ms to ASS centiseconds, without independent retiming. Validate bounds/duplicates/approval/glyphs; wrap/shrink without truncation to two lines. Short/high-reading-rate cues require review acknowledgement. Overlapping speakers stack into safe available space, or fail visibly. Configurable system fonts, responsive reference1080 font size, colors/outline/shadow/background/alignment/position/margins/line spacing and speaker styles. Locally discovered fonts are staged temporarily and not redistributed; missing glyphs fail. Text braces/backslashes are escaped; a WORD JOINER prevents literal ASS escape sequences from being interpreted.

Default burn-in uses libass. **Native ASS is not promised inside MP4**: soft mode explicitly converts the same generated event report to a temporary escaped SRT bridge and then mov_text, retaining the original ASS sidecar. Direct ASS→mov_text leaked visible brace escape characters during testing; this was fixed and actual UTF-8 mov_text packets verified. Advanced ASS styles/placement and mobile playback support vary. No-subtitle mode ignores unused style/glyph settings.

M2 supplies video only; M3 supplies audio only. Optional background requires separated-track provenance/rights/source SHA/content SHA/project/timeline under its managed directory; raw Chinese dialogue is never mapped. M4 does not perform separation. Timeline follows source/M3; short audio pads silence, audio longer than video is rejected for correction. No blind `-shortest`. Resample48k, volume controls and limiter avoid clipping; output AAC mono, H.264/yuv420p/faststart. Geometry preserves aspect, padding default, crop confirmed. Original keeps dimensions/rational FPS; TikTok1080×1920 or720×1280; compact/selected-range preview uses at most640 long edge. Fast/Balanced/High libx264 CRF26/21/18 and veryfast/fast/medium trade size/quality/CPU; CPU libopenh264 fallback uses bitrate instead of unsupported CRF. Stream-copy video when soft/none geometry/FPS/timeline permit.

Every export requires FFprobe metadata, full video decode, MP4 atom faststart check, stream-start/duration/FPS checks, zero-lag decoded waveform comparison to configured M3 (+eligible background), clipping/tail checks and representative transformed-M2 frame comparisons. Burn mode requires changed subtitle pixels; font glyph checks and direct image inspection supplement that evidence. Soft mode verifies actual mov_text payload. Sampled frame checks do not prove every frame or arbitrary font/player correctness. Waveform correlation verifies preservation of M3 timing/content, not linguistic accuracy or a subjective speech-quality score.

## Automated and real evidence

Final full-suite result is recorded below after verification. Intermediate complete run: **218 passed in140.79s**, zero failures/errors/skips, before adding the no-subtitle unused-style regression. Deterministic M4 tests cover41 cases; one additional opt-in real M4 E2E uses production subprocess workers. Tests include invalid timestamps/ranges/escaping/multiline/overlaps/fallback, all subtitle modes, real presets/crop/padding, short/long audio and synthetic background mix, missing streams/wrong codecs/corrupt/zero output, library/reopen/trash/restore, stale edits/publication failure, cancellation/dead-worker recovery, job exclusion and populated/first-use Streamlit AppTest. Deterministic integration tones are explicitly test providers, not claims of actual AI speech.

Actual end-to-end original synthetic Chinese fashion fixture: generated6s540×96025fps with Chinese captions and licensed AISHELL3 synthetic Mandarin, no downloaded creator video. Real PaddleOCR→Argos→explicit manual text review→M2 worker→Whisper base CPU→Argos→explicit manual speech review→VAIS1000 local Vietnamese TTS→M3 master→M4 preview/final worker→validation→cancelled retry→SQLite reopen. Independent test **1 passed in34.46s**, measured pipeline32.5s. Persistent demo repeat pipeline31.71s. Model/provider details/licenses are in M3 report; optional AISHELL3 is a test-only model. No cloud API or media upload.

Recognition observed `我喜歡這類衣服`; Argos produced `Tôi thích cái này.` and omitted garment detail. Fixture reviewer explicitly corrected to `Tôi thích bộ quần áo này.` before approval/synthesis. This is manual correction, not automatic translation success without review. No general ASR/translation/naturalness/peak-memory benchmark.

Persistent final export: **6.0s,540×960,9:16,25fps,H.264 High/AAC,yuv420p,48kHz mono**, audio/video starts0.0, faststart true, **41,962bytes**, full video decode passed. Decoded waveform correlation **0.9999840997308738**, peak **0.56805419921875**, **144,000** compared24k samples, duration difference **0.0s**. Input source/M2/M3 hashes unchanged. SHA256 `12f730f8c79582280f05f7af37241210b930ae318016c769534d0f419fb26d7d`.

Actual final frame at0.71s inspected directly: readable M2 `Phối đồ nam` / `Mẫu mới Thu Đông`, preserved `ABC123` and M4 `Tôi thích bộ quần áo này.` with Vietnamese diacritics. Ignored local proof `docs/screenshots/m4-final-frame.png`; video remains only under ignored storage. Actual browser preview playback reached1.58s with duration5s/errornull, dimensions360×640. Browser connection then became unavailable before repeating final export/download clicks. **Final browser button/download roundtrip and subjective audio listening in this resumed session: NOT TESTED**; backend real final rendering, playback readiness, decoded audio and populated UI AppTest were verified. This limitation must not be hidden by an unconditional acceptance-complete claim.

Migration experiment: SQLite backup API made an isolated consistent copy of the populated M3 demo DB. Production migration preserved **13 pre-existing non-version tables /8 rows**, versions1/20/30/40/50 coexist, exactly one pre-v50 backup. Original DB untouched; no existing table recreated/deleted.

## Acceptance matrix

| # | Criterion | Result / evidence |
|---|---|---|
|1|Retrieve M2/M3 artifacts|PASS — strict contracts + real production workers|
|2|Valid Vietnamese ASS|PASS — generated/parsed/real libass rendering|
|3|Vietnamese Unicode|PASS — glyph validation and inspected final frame|
|4|M3 timestamp alignment|PASS — raw/ASS timing, zero-lag waveform and actual cues|
|5|Customize appearance|PASS — validated configs, speaker/layout tests and populated UI|
|6|Burned-in subtitles|PASS — real render and visible representative frame|
|7|Soft subtitles where supported|PASS — real MP4 mov_text text/language; ASS sidecar, compatibility acknowledged|
|8|M2/M3 mux|PASS — actual E2E preserves source hashes|
|9|AV synchronization|PASS — starts/duration/sample comparison; no broad perceptual-quality claim|
|10|Exclude Chinese dialogue|PASS — explicit stream mapping and distinct original/dub tone regression|
|11|H.264/AAC MP4|PASS — real FFprobe + full decode|
|12|TikTok/Original presets|PASS — real1080×1920 padding and original540×960; crop/compact tests|
|13|FFprobe output validation|PASS — all streams/metadata checked, invalid outputs rejected|
|14|Preview/export management|PASS automated/backend; final browser download roundtrip NOT TESTED after browser disconnect|
|15|Persistent jobs|PASS — reopen/recovery/cancel/retry/exports migration tests|
|16|M0–M3 remain operational|PASS subject to final full-suite result below|
|17|All old/new tests|See final exact result below|
|18|Real E2E rendered and inspected|PASS video/frame/decode; subjective audio listening NOT TESTED in resumed session|

## Windows setup and execution

Run from repository root. Python3.11, FFmpeg/FFprobe with libass/ass filter, AAC, CPU H.264 and mov_text are required. Install licensed Vietnamese-compatible system font (Arial/Segoe UI already on Windows, or DejaVu Sans); never copy unlicensed fonts into Git. Use `.env.example` only as a template on a fresh install. Existing local environment/settings must not be overwritten.

```powershell
Set-Location 'D:\tiktok\Fashion-AI'
py -3.11 -m venv .venv-m4
.\.venv-m4\Scripts\python.exe -m pip install -r requirements-m4.txt
# Only on a fresh install: Copy-Item .env.example .env
# Replace these two executable paths with your installed FFmpeg build:
$env:FFMPEG_PATH=(Resolve-Path '.tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe').Path
$env:FFPROBE_PATH=(Resolve-Path '.tools/ffmpeg/ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe').Path
& $env:FFMPEG_PATH -hide_banner -filters | Select-String 'ass|subtitles'
& $env:FFMPEG_PATH -hide_banner -encoders | Select-String 'libx264|libopenh264|aac|mov_text'
# Existing M2/M3 artifacts suffice for M4; setup below is only for missing earlier models/real E2E:
$env:HF_HUB_DISABLE_XET='1'
.\.venv-m4\Scripts\python.exe scripts/setup_m1_models.py --ocr --translation
.\.venv-m4\Scripts\python.exe scripts/setup_m3_models.py --whisper --tts --fixture-chinese
$env:ASR_PROVIDER='whisper'
# Real fixture requires an installed Chinese font; choose your actual path:
$env:M1_CHINESE_FONT=Join-Path $env:WINDIR 'Fonts/msyh.ttc'
$env:M1_RUN_REAL='1'
$env:M2_RUN_REAL='1'
$env:M3_RUN_REAL='1'
$env:M4_RUN_REAL='1'
.\.venv-m4\Scripts\python.exe -m pytest -q --tb=short --junitxml=storage/temp/m4-full.junit.xml
.\.venv-m4\Scripts\python.exe -m streamlit run app/main.py
```

Verified machine uses existing `.venv-m1-clean` instead of a newly created environment. Actual full flags require all local models above; without opt-in flags those real tests deliberately skip. CI gates M0–M4 deterministic suites including real FFmpeg, without downloading AI weights. Background separation quality, actual external separated music, all mobile players, actual FunASR/Azure inference, GPU acceleration, long-form production videos and exhaustive subjective AV review remain NOT TESTED. No separated background present means voice-only is available, background disabled.

Primary format references: [FFmpeg MP4 codec compatibility](https://github.com/FFmpeg/FFmpeg/blob/master/libavformat/movenc.c), [FFmpeg filters](https://github.com/FFmpeg/FFmpeg/blob/master/doc/filters.texi), [Aegisub ASS tags](https://aegisub.org/docs/latest/ass_tags/), [libass parsing](https://github.com/libass/libass/blob/master/libass/ass_parse.c).

## Final verification and publication

Final complete Windows CPU run: **219 passed in269.00s**, zero failures/errors/skips. Counts:26M0 +79 deterministic M1/Smart +1real M1 +31M2 +1real M2 +38M3 +1real M3 +41M4 +1real M4. All four real flags enabled. Local ignored JUnit: `storage/temp/m4-full.junit.xml`. Criteria16/17 automated regression verification PASS. No extra test run required for documentation-only edits after this result.

Audit of127 tracked/candidate source/config/docs paths: zero forbidden runtime/data/media/model files, zero files over1MiB, zero credential-pattern matches. Existing .gitignore excludes .env/SQLite/storage/media/ASS/audio/model binaries/screenshots/logs. Complete source diff reviewed; whitespace checks pass. Fetch reconfirmed develop3809a4c and maina3d2e63; branch ancestry unchanged. Authorized normal feature push and review PR only; no merge, force push, main modification, tagv1.0.0, release or additional milestone. This is a reviewable implementation with the manual verification limitations above, not unconditional final owner acceptance.

Published branch [feature/m4-final-rendering](https://github.com/hphuc032/Fashion-AI/tree/feature/m4-final-rendering), draft [PR#6](https://github.com/hphuc032/Fashion-AI/pull/6) targeting develop, open/unmerged. Implementation commits:bb694fb,f9b2125,4c1ff3f,dbf1ad7,162d21c,adc6650,656f463,8c17443. Final docs-only publication commit and hosted-check results are supplied in PR/final handoff. Draft retained for the explicitly untested manual checks.
