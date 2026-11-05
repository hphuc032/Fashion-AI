# M3 verification — 2026-11-05

Approved baseline: `59220ba4fd89b92b2adc13cc4a018d73bb368389` on origin/develop, owner merge of M2 PR #4. Clean branch `feature/m3-ai-dubbing` created from that exact commit. Plan committed first as `76a9ab6`. Existing real M0/M1/M2/Smart baseline:138 passed in57.51s. Main unchanged; no M3 merge/tag/release or M4 implementation.

## Automated evidence

Complete Windows CPU run, Python3.11.18, portable FFmpeg/FFprobe9.0.2, pinned requirements-m3.txt: **177 passed in75.77s, zero failures/errors/skips**. Counts:26 M0 +79 deterministic M1/Smart +1 real M1 +31 M2 +1 real M1→M2 +38 deterministic/actual-FFmpeg M3 +1 actual M3 AI worker E2E. All M1_RUN_REAL/M2_RUN_REAL/M3_RUN_REAL flags enabled. Local ignored JUnit: `storage/temp/m3-full.junit.xml`.

New tests cover MP4/MOV/MKV extraction, missing/corrupt audio, mono16k conversion and cache, initial0.7s audio offset preservation, FunASR milliseconds/speaker/unknown-confidence structures, invalid timestamp/confidence, overlapping chunk dedup, missing model errors, atempo chains/limits, shorter/gentle/severe mismatch, PCM silence placement/exact sample count, overlap/clipping/cancel cleanup, TTS cache/settings, explicit cloud gate and mocked Azure voice/SSML validation, manual edits/revisions/speaker config, rights/pending/idempotency, worker transitions/failure/cancel/dead recovery, queue exclusion, stale contract and SQLite reopen, populated/first-use Studio. Fake providers generate tones only in isolated tests and are explicitly named; they do not count as real speech verification.

## Real ASR, translation and TTS

Original Mandarin fixture generated from our text `我喜欢这件衣服。` using local AISHELL3 VITS, anonymous model speaker21 (not voice cloning), noise scales0 for repeatability; dataset published under Apache2. Source synthesis8k mono, muxed as AAC into an original5s video solely for testing. No private or downloaded creator video. Fixture model is optional and never loaded by production ASR/TTS/startup.

Actual **faster-whisper base**, CPU int8/2threads, forced zh, word timing requested, inference in a disposable worker. Observed phrase `我喜歡這類衣服` (Traditional output), valid0..video-duration timing; confidence stays **None**, since no calibrated phrase confidence is supplied. Recognition differs slightly from original “件”→“類”; no general accuracy claim. Earlier tiny runs had unstable/homophone mistakes; base chosen after this evidence. Chinese script is preserved, not silently rewritten to Simplified.

Actual existing Argos zh→en→vi through the existing TranslationService with a speech-context cache key generated `Tôi thích cái này.`. This loses garment detail. Explicit human fixture review corrected/approved `Tôi thích bộ quần áo này.` before synthesis; this is **manual correction, not a fabricated automatic fallback**. Unknown neural semantics are always reviewed; price/brand/number/CJK/claim flags remain visible.

Actual **sherpa-onnx1.13.8 + Piper VAIS1000 medium**, verified one installed voice `vais1000:0`, sample rate22,050Hz. Runtime verifies loaded model speaker count and voice ID, checks unsupported pitch. Model manifest+runtime version, text and all settings identify TTS cache. Real voice preview and full-track job both produced speech. No cloud credentials/network/paid API used. First attempted sherpa2.0.1 no longer included the phonemizer and returned empty audio; downgraded to a compatible pinned1.x runtime, then actual synthesis passed. This failure was not counted as success.

Independent complete real M3 worker E2E: **1 passed in12.15s**, measured pipeline10.75s;5.0s WAV master,24k mono PCM16, **120,000 samples**,240,044 bytes. Includes real ASR→Argos→manual review→voice preview→TTS/sync→assembly, actual job cancellation/reopen and original video byte comparison. Later full-suite reruns also passed. Shorter speech preserves natural speed and trailing silence; gentle mismatch uses atempo; severe mismatch fails with a shorten/retime instruction. Master silence covers unspoken regions; Chinese dialogue is not mixed into output. Source video remains byte-identical; original audio stream copied into separate MKA and a timeline-aligned16k WAV serves ASR/preview.

## Migration and compatibility

SQLite backup API copied the existing populated M2 demo DB into an isolated upgrade fixture. Compared every pre-existing non-version table before/after: **9 tables,33 rows unchanged**. Exactly one pre-v40 backup created; schema versions **1,20,30,40** coexist. No existing table recreated/deleted; speech/audio tables separate from OCR text/render configuration. All old138 tests still pass. Existing source DB was not modified by this experiment.

## Acceptance matrix

| Requirement | Result | Evidence |
|---|---|---|
|1 Extract original audio | PASS | Actual stream copy/mono16k and three containers/offset tests |
|2 Working Chinese ASR | PASS | Actual local Whisper base; FunASR adapter separately qualified below |
|3 Valid phrase timestamps | PASS | Normalization/chunk/range tests and real worker |
|4 Working Vietnamese translation | PASS with manual review | Real Argos; omission corrected explicitly |
|5 Editable/approved speech | PASS | Revision/review tests and populated Studio |
|6 At least one verified Vietnamese TTS voice | PASS | Actual loaded VAIS1000 voice and WAV generation |
|7 Voice preview | PASS | Real preview worker and UI control |
|8 Segment synchronization | PASS | Actual atempo/normalization; conservative limits |
|9 Complete Vietnamese audio timeline | PASS | Real assembled WAV |
|10 Timeline matches source | PASS | Exact120,000 samples for5s; master tolerance1/24000s |
|11 Source video/audio preservation | PASS | Source byte equality, separate copied source artifact |
|12 Audio preview/download | PASS | Studio controls; actual browser result recorded in implementation log |
|13 Persistent history | PASS | SQLite reopen/E2E and supervisor tests |
|14 CPU without mandatory GPU | PASS | All actual model jobs ran on CPU |
|15 M0/M1/M2 functional | PASS | All138 old tests |
|16 Automated tests pass | PASS |177/177, zero skipped |
|17 Real Chinese→Vietnamese TTS→assembled artifact | PASS in controlled scope | Actual models, original synthetic speech, manual review |
| FunASR actual model/optional diarization | NOT TESTED | Adapter/output contracts unit tested; heavyweight model/toolkit not installed |
| Azure real voice list/synthesis | NOT TESTED | Explicit configurable REST adapter mocked; no credentials supplied or paid calls |
| GPU/Windows10 specifically/broad naturalness/real multi-speaker corpus | NOT TESTED | No benchmark claimed |
| Background source separation (ModeB) | NOT IMPLEMENTED, optional | UI explains limitation; ModeA works independently |

## Providers and sources

- [FunASR AutoModel contract](https://github.com/modelscope/FunASR/blob/main/docs/python_api.md): primary adapter local timestamp-capable Paraformer; optional local VAD/punctuation/speaker paths. Never infer timestamps for a model with no timestamps. Native sentence_info milliseconds divided by1000; missing confidence remainsNone. For diarization, one chunk only to avoid relabelling speakers across chunks; otherwise default/manual stable speaker labels.
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper): alternative actually tested base CPU. Model size configurable via explicit installer and local path, no hub resolution in application.
- [Vietnamese model](https://k2-fsa.github.io/sherpa/onnx/tts/all/Vietnamese/vits-piper-vi_VN-vais1000-medium.html) and [model card](https://huggingface.co/rhasspy/piper-voices/blob/main/vi/vi_VN/vais1000/medium/MODEL_CARD): one voice22,050Hz, dataset CC BY4.0; respect model/runtime notices. No binary/font/model redistributed in Git.
- [AISHELL3 provenance](https://www.openslr.org/93/): optional original-fixture synthesis model; dataset Apache2. Anonymous model voice is not an imitation of the source creator. An experimental Huayan model with unknown dataset licensing was excluded from acceptance fixtures.
- [Azure REST](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech): optional cloud adapter, dynamically verifies vi-VN voice list, never hardcodes an assumed cloud voice. Credentials environment-only; explicit text-transmission confirmation; no source audio upload.

Measured installed directories: Whisper base147,884,779 bytes; Vietnamese TTS81,183,394 bytes; optional AISHELL3 fixture model213,480,265 bytes (archive31,559,701). Normal application needs only chosen ASR and TTS, not fixture model, tiny candidate, Torch/FunASR or cloud. No startup downloads, no peak RAM/throughput/general quality benchmark claimed.

## Exact Windows commands

From repository root with Python3.11 and FFmpeg/FFprobe/libx264 available:

```powershell
py -3.11 -m venv .venv-m3
.\.venv-m3\Scripts\python.exe -m pip install -r requirements-m3.txt
# New setup only; do not overwrite an existing .env:
Copy-Item .env.example .env
# Set FFMPEG_PATH/FFPROBE_PATH in .env when not on PATH.
# ASR_PROVIDER=whisper selects the tested CPU alternative.
$env:HF_HUB_DISABLE_XET='1'
.\.venv-m3\Scripts\python.exe scripts/setup_m3_models.py --whisper --tts
.\.venv-m3\Scripts\python.exe scripts/setup_m1_models.py --ocr --translation
# Optional, only to reproduce original synthetic Mandarin test:
.\.venv-m3\Scripts\python.exe scripts/setup_m3_models.py --fixture-chinese
$env:M1_RUN_REAL='1'
$env:M2_RUN_REAL='1'
$env:M3_RUN_REAL='1'
.\.venv-m3\Scripts\python.exe -m pytest -q --tb=short
Remove-Item Env:M1_RUN_REAL,Env:M2_RUN_REAL,Env:M3_RUN_REAL
.\.venv-m3\Scripts\python.exe -m streamlit run app/main.py --server.address 127.0.0.1
```

Actual verification used existing `.venv-m1-clean` and explicit absolute portable FFmpeg/FFprobe environment paths. Deterministic M3: `python -m pytest tests/test_m3.py -q`. Without flags three actual-model tests skip visibly. CI has26/79/31/38 no-skip gates, no model downloads. Optional FunASR: install requirements-m3-funasr.txt in a compatible environment; explicitly install local Paraformer timestamp-capable model and optional VAD/punc/CAM++ via official toolkit/setup outside app, set ASR_MODEL_DIR/FUNASR_* paths; no remote-code models enabled. No claim that unexecuted FunASR package/model combination was tested.

## M4 audio-only interface

Call `app.services.dubbing_contract.approved_dub(sessions, settings, project_id)`. Returns versioned JSON-compatible dictionary with original audio path, source SHA, timestamped Chinese/Vietnamese/speaker/ASR/confidence/revision rows, raw TTS and synchronized segment paths/durations/ratio/factor/warnings, full WAV path/hash/duration/sample rate and processing/voice configuration (no credentials). Corresponding `manifest.json` beside master for inspection. Validates current rights, transcript fingerprints/approval, segment set, speaker config, source hash, master hash/duration and managed per-project artifact existence. Stale/missing/changed output is rejected; no automatic fallback to old approval. No MP4 mux, ASS/SRT or M4 work added.

## Limits

Neural ASR/Argos errors remain possible; transcript/timing/meaning must be reviewed. Synthetic speech is a controlled smoke test, not a human-speech benchmark. ASR punctuation/speaker metadata depend on model; no calibrated confidence invented. Chunk overlap dedup is conservative text+time matching, not forced alignment; ambiguous overlapping speakers remain separate and must be manually corrected. Default assembler blocks overlaps; no automatic multi-speaker mixing. FunASR optional diarization limited to one configured chunk; default speaker/manual correction works without it.

Local TTS has one model voice and no pitch/gender controls. Azure availability depends on configured account/region; real cloud untested. Default gentle sync0.85–1.20; very short speech remains natural with silence, long speech blocks rather than being clipped. Normalization/limiter reduces clipping, not a broad perceptual quality guarantee. Master duration tolerance one24k sample; segment atempo boundary tolerance35ms may require manual timing if adjacent audio conflicts. Video without audio returns actionable error; empty recognized transcript can assemble a silent timeline after completed ASR.

One heavy job across OCR/render/dub; disposable worker/cancel/timeout and owned-file cleanup; restart marks dead work failed for explicit retry, retains previous completed audio. Cached TTS keyed by model/runtime/content/settings, source extraction keyed by source SHA. Cache/log/output retention can grow on disk; no automatic user-media deletion. A power loss around rename/DB commit can leave an orphan UUID artifact; it is not considered completed/approved. Cloud consent/settings snapshots contain no credentials; API keys read only from environment. No voice cloning, source separation guarantee, posting, release or M4 mux.

Actual Brave localhost8504 completed ASR/selected Argos/manual edit+approval/voice preview/full assembly/download/M4 contract. Master HTML audio readyState4,duration5,errornull; pausedfalse/currentTime0.459981 while playing. Screenshot docs/screenshots/m3-dubbing.jpg is local ignored. Final populated/first-use UI presentation regression:1 passed in1.99s after hiding internal UUID/path labels.

## Files created or changed

- `.env.example`
- `.github/workflows/m0-tests.yml`
- `.gitignore`
- `README.md`
- `app/core/config.py`
- `app/database/speech_schema.py`
- `app/dub_worker.py`
- `app/providers/asr/__init__.py`
- `app/providers/asr/base.py`
- `app/providers/asr/funasr_provider.py`
- `app/providers/asr/whisper_provider.py`
- `app/providers/tts/__init__.py`
- `app/providers/tts/azure_tts_provider.py`
- `app/providers/tts/base.py`
- `app/providers/tts/local_tts_provider.py`
- `app/services/audio_extractor.py`
- `app/services/audio_sync_service.py`
- `app/services/dub_jobs.py`
- `app/services/dubbing_contract.py`
- `app/services/dubbing_service.py`
- `app/services/ocr_service.py`
- `app/services/render_jobs.py`
- `app/services/speech_repository.py`
- `app/services/speech_segmentation.py`
- `app/services/translation_service.py`
- `app/services/workload_guard.py`
- `app/ui/dashboard.py`
- `app/ui/dubbing_studio.py`
- `docs/IMPLEMENTATION_LOG.md`
- `docs/M3_IMPLEMENTATION_PLAN.md`
- `docs/M3_TEST_REPORT.md`
- `requirements-m3-funasr.txt`
- `requirements-m3.txt`
- `scripts/generate_m3_fixture.py`
- `scripts/setup_m3_models.py`
- `tests/test_m3.py`
- `tests/test_m3_real.py`

## Publication

[Feature branch](https://github.com/hphuc032/Fashion-AI/tree/feature/m3-ai-dubbing), open/unmerged [PR #5 → develop](https://github.com/hphuc032/Fashion-AI/pull/5). Verified implementation head2deaa27, commits76a9ab6/c8e372b/3036308/24a2f00/8f0e306/3922052/2deaa27; final docs-only publication SHA and latest hosted check results in handoff/PR. Normal pushes only; main/tag unchanged, no M4.
