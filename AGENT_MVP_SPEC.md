# FASHION AI LOCALIZER — AGENT BUILD SPEC & EXECUTION PLAN

**Version:** 1.0
**Language:** English for technical instructions; Vietnamese for product UI and user-facing messages.
**Target:** Local MVP on Windows laptop (16 GB RAM), accessible via browser.
**Project name:** `fashion-ai-localizer`
**Implementation status:** Specification only. Do not claim any feature has been implemented until verified.

> **Agent instruction:** You are the implementing software engineering agent. Read this entire document before writing code. Inspect the repository first, then implement and test the MVP in vertical slices. Do not replace functioning files without inspecting them. Record decisions and actual test results in `docs/IMPLEMENTATION_LOG.md`. Build the smallest working end-to-end pipeline before adding refinements. If a credential or external account is missing, provide a mock/demo adapter and clearly identify it; do not fake successful API integration.

---

## 1. Product overview / Bối cảnh

The owner operates **one existing Vietnam TikTok account** focused on **men's fashion affiliate marketing**. They research Chinese fashion videos and styling trends on Douyin and already have a browser extension capable of downloading videos. This tool must **not** implement automated Douyin scraping, bypass restrictions, or TikTok auto-posting. The user manually imports a locally available video, reviews the transformation, exports an MP4, and manually decides whether/how to publish it.

**Main objective:** Turn a **lawfully usable** Chinese-language men's fashion video into a Vietnamese-localized video. Localize both:

1. **Visible Chinese text embedded in video frames** (OCR -> translate -> replace in place); and
2. **Spoken Chinese audio** (ASR -> translate -> natural Vietnamese TTS -> dubbing, subtitles).

**Target user:** Solo creator, Vietnamese UI, minimal technical setup, preference for **free/local processing** with optional paid cloud providers.

**Non-negotiable:** Removing watermarks, replacing Chinese text, or dubbing audio does **not** establish copyright ownership or authorization to repost. Users must confirm source rights before export. Preserve original source metadata and distinguish permission from mere possession of a file. Video captions and product assertions must not falsely claim a product is identical to the footage when unverified.

### MVP success definition

A user can: create a project -> import one supported local video -> inspect detected Chinese on-screen text and dialogue -> edit Vietnamese translations -> apply Vietnamese text overlay/replacement -> optionally add Vietnamese dubbing and subtitles -> render preview/export -> save final MP4 and SRT -> manually publish outside the app.

**MVP is semi-automatic:** Required human review of translations, text regions, output, and usage rights. No automated affiliate product matching.

---

## 2. Scope and exclusions

### In scope (P0 = MVP)

- Vietnamese Streamlit web UI running on localhost.
- Import video file via upload (MP4 preferred; MOV optional) with validation; no remote download.
- Source record: original URL (optional), creator name (optional), license/permission status, usage notes; explicit confirmation before export.
- Read video metadata using `ffprobe` (resolution, duration, fps, codec); safe storage and file-size/duration limits configurable.
- Extract mono 16 kHz audio with FFmpeg.
- Sample video frames at configured rate (e.g. 1–2 fps) for OCR to bound CPU costs; allow targeted additional sampling.
- Detect Chinese on-screen text using PaddleOCR; merge repeated detections across neighboring frames into timed text tracks; provide editable start/end and bounding boxes.
- Translate Chinese text to conversational Vietnamese appropriate for men's fashion; allow user edits before render.
- Replace original on-screen Chinese text: baseline is mask/blur or solid/background patch + Vietnamese overlay; optional inpainting is P1, **not required for first working release**. Never claim pixel-perfect removal from arbitrary dynamic backgrounds.
- Use `faster-whisper` to transcribe Chinese dialogue (when audio exists), preserving timestamps; allow manual corrections.
- Translate dialogue and generate Vietnamese natural-sounding speech via configurable TTS adapter (Azure Speech optional); supply an offline/mock or non-network fallback for testing and optional voice-off workflow. Handle silent videos.
- Generate timed SRT subtitles and optional embedded subtitle render; support Vietnamese Unicode fonts.
- Render final video using FFmpeg at original aspect ratio (including 9:16), H.264 video + AAC audio; allow preview, SRT and MP4 download.
- Background execution or a non-blocking job design with persisted progress per stage, retries at stage boundaries, and understandable errors.
- Store state locally in SQLite; media artifacts in per-project directories, not in database blobs.
- Basic logs, integration/unit tests and a sample synthetic test fixture (no copyrighted Douyin assets bundled).

### Out of scope (P1/P2)

- Douyin downloader, platform scraping, bypassing DRM or anti-bot, watermark removal.
- Automatic TikTok sign-in, posting, affiliate tagging, engagement automation.
- Full character diarization, speaker-specific emotional voice acting, lip sync.
- Perfect temporal tracking, complex object removal/inpainting on moving backgrounds.
- Bulk parallel processing, cloud deployment, multi-user authentication, payments.
- Automatic matching of an unrelated shop item to a video, or making unverified product claims.

---

## 3. Recommended architecture

### MVP architecture: local modular monolith

```text
Browser (localhost:8501)
        |
   Streamlit UI
        |
 Application orchestrator / jobs
        |
        +-- Video service -------- ffprobe / ffmpeg
        +-- Frame OCR ------------ PaddleOCR (Chinese)
        +-- Text grouping -------- OCR track timelines
        +-- Translation ---------- pluggable translator
        +-- Speech-to-text ------- faster-whisper (local)
        +-- Text-to-speech ------- pluggable Azure TTS / optional fallback
        +-- Text replacement ---- OpenCV/Pillow overlay + FFmpeg
        +-- Subtitle + render ---- SRT / FFmpeg
        |
      SQLite (project metadata, jobs, text tracks, edits)
      storage/projects/<id>/ (source, temp, previews, exports)
```

**Avoid FastAPI, React, Redis, Postgres, Celery and Docker in P0** unless repository context absolutely requires them. One local user needs a small, robust application, not a distributed architecture. Use Python 3.11; choose pinned compatible versions after checking current package support. Use `pathlib`, typed functions, unit-testable services, and `subprocess.run([...], shell=False, check=True, timeout=...)` for FFmpeg.

### Proposed folder structure

```text
fashion-ai-localizer/
├── README.md
├── AGENT_MVP_SPEC.md
├── .env.example
├── .gitignore
├── pyproject.toml              # dependencies & tooling (or requirements files)
├── app/
│   ├── __init__.py
│   ├── ui.py                   # Streamlit entrypoint
│   ├── config.py               # env and local settings
│   ├── db.py                   # SQLite and migrations/init
│   ├── models.py               # typed domain records
│   ├── pipeline.py             # idempotent step orchestrator
│   ├── rights.py               # user confirmation and audit
│   ├── services/
│   │   ├── media.py            # FFmpeg / ffprobe
│   │   ├── frames.py           # frame sampling
│   │   ├── ocr.py              # PaddleOCR adapter
│   │   ├── text_tracks.py      # deduplicate OCR detections / timing
│   │   ├── translation.py      # provider interface + adapters
│   │   ├── asr.py              # Whisper adapter
│   │   ├── tts.py              # provider interface + adapters
│   │   ├── subtitle.py         # SRT generation
│   │   ├── overlay.py          # masking and Vietnamese text drawing
│   │   └── render.py           # final MP4 composition
│   └── utils/
│       ├── files.py
│       └── logging.py
├── tests/
│   ├── test_media.py
│   ├── test_text_tracks.py
│   ├── test_subtitle.py
│   ├── test_rights.py
│   ├── test_pipeline.py
│   └── fixtures/              # generated, license-safe synthetic input
├── scripts/
│   └── generate_test_video.py
├── docs/
│   ├── IMPLEMENTATION_LOG.md
│   ├── ARCHITECTURE.md
│   └── TROUBLESHOOTING.md
└── storage/                    # gitignored
    └── projects/<uuid>/
        ├── source/
        ├── audio/
        ├── frames/
        ├── ocr/
        ├── asr/
        ├── voice/
        ├── preview/
        └── exports/
```

File/module names are a suggested baseline; maintain conceptual boundaries even if implementation differs.

---

## 4. Data model (SQLite, no video BLOB)

Use SQLite for one user; enable foreign keys, index common queries, use transaction boundaries. Minimal tables:

### `projects`
- `id TEXT PRIMARY KEY` UUID
- `name TEXT NOT NULL`
- `source_url TEXT NULL`
- `creator_name TEXT NULL`
- `rights_status TEXT NOT NULL` (`unknown`, `owned`, `licensed`, `permission_granted`)
- `rights_notes TEXT NULL`
- `rights_confirmed_at TEXT NULL`
- `video_path TEXT NOT NULL` (relative, inside storage)
- `duration_ms INTEGER`, `width INTEGER`, `height INTEGER`, `fps REAL`
- `status TEXT NOT NULL`, `created_at TEXT NOT NULL`, `updated_at TEXT NOT NULL`

### `jobs`
- `id TEXT PRIMARY KEY`, `project_id TEXT REFERENCES projects(id)`
- `stage TEXT`, `status TEXT` (`queued`, `running`, `needs_review`, `completed`, `failed`)
- `progress INTEGER` (0–100), `error_message TEXT NULL`
- `attempts INTEGER`, `started_at TEXT`, `finished_at TEXT`

### `onscreen_text_tracks`
- `id TEXT PRIMARY KEY`, `project_id TEXT REFERENCES projects(id)`
- `start_ms INTEGER`, `end_ms INTEGER`, `x INTEGER`, `y INTEGER`, `w INTEGER`, `h INTEGER`
- `original_zh TEXT`, `translated_vi TEXT`, `confidence REAL`, `approved INTEGER DEFAULT 0`

### `speech_segments`
- `id TEXT PRIMARY KEY`, `project_id TEXT REFERENCES projects(id)`
- `start_ms INTEGER`, `end_ms INTEGER`, `original_zh TEXT`, `translated_vi TEXT`
- `voice_id TEXT NULL`, `tts_path TEXT NULL`, `approved INTEGER DEFAULT 0`

### `assets`
- `id TEXT PRIMARY KEY`, `project_id TEXT REFERENCES projects(id)`
- `kind TEXT` (`source`, `audio`, `srt`, `preview`, `export`, `tts`)
- `relative_path TEXT`, `created_at TEXT`

Keep `translation provider` and `TTS provider` settings in `.env` and/or local config without persisting API keys in DB.

---

## 5. UI requirements (Vietnamese)

Single-user Streamlit tabs/pages:

1. **Dự án:** create/open project; upload local video; enter optional source URL/creator; show metadata and original preview; display permission status.
2. **Nhận diện & Dịch:** run OCR/ASR; show editable grid with Chinese text, Vietnamese translation, timestamps, bounding box and approval state; enable per-line manual edits; handle untranslated/low-confidence detection visibly.
3. **Lồng tiếng & Phụ đề:** enable/disable voice, select available voice, adjust rate, preview small test, enable SRT/burn-in; let user choose original audio volume / ducking (do not silently erase ambience).
4. **Xem trước & Xuất:** preview visual replacement and final MP4, approve content and rights, export MP4 + SRT, show paths/downloads; show errors/retry.
5. **Cài đặt:** model size (`tiny`, `base`, `small`), translation provider, TTS provider, CPU/GPU availability, paths, privacy notes.

User-facing labels/errors in Vietnamese. Display **“Bản dịch cần được kiểm tra trước khi xuất”** where relevant. Do not expose secret credentials or absolute sensitive paths in logs.

---

## 6. Pipeline details and correctness expectations

### A. Import

- Accept local MP4, and MOV only if ffprobe accepts codecs.
- Sanitize filenames; store with generated UUID; never build paths from user-provided names directly.
- Enforce configurable defaults: `MAX_VIDEO_MB=250`, `MAX_VIDEO_SECONDS=180` for MVP. These are **MVP safety/performance limits**, not platform rules.
- Validate actual file contents with ffprobe (do not trust extension/MIME).
- Preserve original source; do not overwrite it.

### B. OCR Chinese on-screen text

- Sample frames at 1–2 fps initially; expose configurable rate.
- PaddleOCR Chinese model, detect text boxes and confidence; map sampled-frame coordinates to original video resolution.
- Group similar OCR text across adjacent frames using text similarity + bounding-box IoU/center proximity; adjust start/end from detected samples with honest precision limits.
- Store confidence and review flag; make all results editable.
- Distinguish embedded on-screen text from automatically generated subtitles where possible; allow the user to deselect regions (e.g. decorative text, product logos).

### C. Translation

- Adapter interface: `translate(text, context, source='zh', target='vi') -> str`.
- Start with an explicitly configured translation provider (e.g. Azure Translator or Google Cloud Translation); no hard-coded credentials.
- Optional LLM-based polishing only if provider configured; **never fabricate prices, discounts, stock, brand, measurements, or performance claims**.
- Batch/deduplicate text to reduce API calls. Cache by normalized input and provider/model version. Show errors and allow manual translation without an API key.

### D. ASR and dubbing

- Use `faster-whisper` with Chinese forced language where applicable; CPU fallback, smaller model on 16 GB RAM. Model download may require Internet once.
- No speech: skip ASR and TTS cleanly.
- Split into timed utterances, edit translations, generate TTS per approved segment.
- Provider interface `synthesize(text, voice, rate, output_path)`; Azure is optional for natural Vietnamese voice, with explicit environment variables and provider errors.
- Time alignment: segment timing and speed adjustment (within sensible bounds); if TTS longer than segment, warn and offer user review rather than cause overlaps or silent clipping.
- Preserve original music/ambience when legally usable; optionally reduce original audio via mix/ducking. If isolated dialogue removal is unavailable, explain that original Chinese speech may remain audible under new voice. **Clean separation of voice from background music is not P0.**
- Do not clone a real person's voice without authorization.

### E. Replace Chinese on-frame text

- P0 use OpenCV frame overlay with region masking/blur/solid patch and PIL text drawing (Vietnamese Unicode via installed/available font). Choose readable contrast, outlines and padding.
- Export with maintained frame rate/aspect ratio; avoid repeated lossy re-encodes.
- Offer manual repositioning/timing edits because OCR, moving text and background may cause errors.
- P1 optional AI inpainting (LaMa or similar) may produce better results but must be optional and should not block MVP.

### F. Subtitles & rendering

- Generate valid UTF-8 SRT (correct `HH:MM:SS,mmm` timing, strictly ordered, no negative times).
- Render H.264/AAC MP4; preserve source aspect ratio. For vertical 9:16 input target original frame size (or optional 1080x1920 up/downscale only if desired).
- Ensure output mux includes audio when requested; handle no-audio originals.
- Create short, low-resolution preview before full export for efficient review.
- Export names: `<project_slug>_vi.mp4` and `<project_slug>_vi.srt`.

### G. Reliability and resource discipline

- Process one video at a time on laptop. Never spin CPU OCR/ASR/render in parallel by default.
- Persist stage outputs and hashes; rerun only invalidated stages after edits. Progress must reflect actual completed stages, not fabricated percentages.
- Capture subprocess stdout/stderr on failure, do not show raw stack traces to users.
- UI must remain usable and show stage status; choose a simple worker thread/process and SQLite state or Streamlit-friendly long-task design, not Redis/Celery P0.
- Safe handling of malformed/malicious video inputs; FFmpeg subprocess list arguments with no `shell=True`; limit file size, duration and storage.
- Ensure output is correctly playable and visibly localized on representative permitted/synthetic input.

---

## 7. Configuration and costs

`.env.example` should contain placeholders, never actual credentials:

```dotenv
APP_STORAGE_DIR=./storage
MAX_VIDEO_MB=250
MAX_VIDEO_SECONDS=180
OCR_SAMPLE_FPS=1
WHISPER_MODEL=base
WHISPER_DEVICE=cpu
TRANSLATION_PROVIDER=manual
GOOGLE_TRANSLATE_API_KEY=
AZURE_TRANSLATOR_KEY=
AZURE_TRANSLATOR_REGION=
TTS_PROVIDER=disabled
AZURE_SPEECH_KEY=
AZURE_SPEECH_REGION=
AZURE_VOICE=vi-VN-HoaiMyNeural
```

- Free/local: Streamlit, FFmpeg, OpenCV, PaddleOCR, faster-whisper, SQLite are typically zero software license cost; confirm dependency/model licenses in repo documentation.
- API translation / Azure neural voice **may** have free tiers and pay-as-you-go pricing; free-tier eligibility and region/provider prices change. **Do not promise a fixed cost or assume a free tier exists for the user's account.**
- Working budget target for initial trials: **0–50,000 VND/month API spend** when possible, excluding rights/licensing, electricity, storage, and the developer's time. Provide config defaults that do not make paid API calls without explicit setup.
- User supplies valid credentials when choosing a cloud provider. A fully offline/manual translation + subtitles-only mode must remain testable.

---

## 8. Agent execution plan (implement in order)

### Milestone M0 — Repository bootstrap and executable skeleton

**Implement**
- Detect whether repository already exists; inspect and preserve useful code.
- Initialize Python project and version-pinned dependencies appropriate to Windows/Python 3.11.
- Build Streamlit UI with project creation, upload, local storage, sqlite initialization, ffprobe validation and video preview.
- Add `.env.example`, README setup instructions, basic structured logging, `.gitignore`.

**Acceptance tests**
- `streamlit run app/ui.py` starts on localhost.
- Import a generated synthetic MP4 (Chinese visible text and optional Chinese sample voice if legally sourced); metadata recorded in SQLite.
- Invalid file type returns clear Vietnamese error, without crash or path traversal.

### Milestone M1 — OCR and editable Vietnamese on-screen translations

**Implement**
- Extract frames, run OCR with CPU path, merge repeated detections to tracks.
- Show editable grid for source, translation, time range and box coordinates.
- Manual translator always works; optional API translator behind adapter; cache duplicates.

**Acceptance tests**
- On a generated Chinese text fixture, at least one expected text track can be detected (subject to OCR model) and edited.
- Track grouping does not create a new row for every sampled frame of identical static text.
- Saving edited Vietnamese text survives Streamlit reload.

### Milestone M2 — Visual replacement and short preview

**Implement**
- Generate text overlay over selected regions, with Vietnamese diacritics supported.
- Build preview (e.g. first 10–15 seconds) and expose region/time edits.
- Keep unchanged frames intact outside designated regions.

**Acceptance tests**
- Exported preview visibly shows user-edited Vietnamese wording.
- Same original resolution/aspect ratio; playable file.
- No failure on textless videos (skip overlay).

### Milestone M3 — Chinese ASR, Vietnamese dialogue and TTS

**Implement**
- Extract audio, transcribe Chinese via faster-whisper with CPU fallback.
- Editable dialogue translations + SRT output.
- Pluggable TTS provider and optional Azure implementation, speech timing and overlay mix.
- Handle silent video and absent cloud credentials cleanly.

**Acceptance tests**
- Audio fixture yields timestamped transcript; user can edit before synthesis.
- Configured TTS produces audible Vietnamese voice (requires provider credentials); without credentials, app still renders original-audio or muted subtitle-only version.
- Subtitle timestamps are valid and sync reasonably with source segments.

### Milestone M4 — Full export, reviews, robustness

**Implement**
- Assemble on-screen translations, optional dubbing, subtitles and export to MP4/SRT.
- Rights-confirmation gate before export; log user confirmation and source rights metadata.
- State machine + retry failed steps; summary of stages, artifacts, warnings.
- Docs, reproducible tests and sample data generator.

**Acceptance tests**
- One full end-to-end test from legal/synthetic video to final playable MP4.
- Export blocked when `rights_status=unknown` or confirmation unchecked; informative error.
- Report actual pass/fail of automated tests and a **manual visual/audio verification checklist**.
- Restart app and reopen project with edits and final artifacts intact.

### Optional P1 (only after P0 accepted)

- Selective AI inpainting for complex moving backgrounds.
- Better speaker diarization and per-character voices.
- Batch processing 3–5 videos sequentially.
- Apparel-specific terminology dictionary and product metadata/commission tracking.
- Timeline editor, scene cut detection, smarter OCR region tracking.

---

## 9. Test matrix / Definition of Done

At minimum test these cases:

| Scenario | Expected result |
|---|---|
| Vertical MP4 with static Chinese text and Chinese speech | Text and speech detected; editable; localized output playable |
| Video without speech | No ASR/TTS crash; subtitles optional; export works |
| Video without embedded text | OCR empty state; export works |
| Chinese text changes mid-scene | Distinct timed tracks or flagged for manual correction |
| Low-confidence OCR or translation error | Warning and editable fallback |
| No translation/TTS API keys | Manual/voice-off route works, no unexpected bill |
| Non-ASCII Vietnamese accents | Correct display in video and UTF-8 SRT |
| Invalid video or oversized file | Safe rejection with Vietnamese message |
| User restarts application | Project state and edits persist |
| Rights not confirmed | Export prevented; source details retained |
| FFmpeg failure | Error captured, retry stage available, no false success |
| 9:16 source | Output aspect ratio preserved |

**DoD:** A user can run the tool from README commands on Windows; one real or generated permitted video can be processed end-to-end; all implemented features pass relevant tests; missing features are explicitly identified; output receives manual visual/audio quality check.

---

## 10. Working protocol for the coding agent

1. **Inspect first**: print repository tree, Python version, OS, whether `ffmpeg` and `ffprobe` are on PATH, and any existing useful modules. Do not assume installed binaries.
2. **Plan**: briefly list exact files to create/change and dependencies, aligned to M0–M4.
3. **Implement a vertical slice**: make minimal runnable UI with upload and one export path, then add OCR, translation and speech services. Do not dump pseudocode claiming completion.
4. **Test every milestone**: run applicable tests and actual CLI/UI smoke checks, log real outputs and failures in `docs/IMPLEMENTATION_LOG.md`.
5. **Fail gracefully**: on missing FFmpeg / large OCR models / unavailable paid credentials, explain setup, make working fallback, and continue other achievable functionality.
6. **Document setup**: include Windows PowerShell commands for creating `.venv`, installing dependencies, `streamlit run app/ui.py`, installing FFmpeg, and downloading any local AI models. Avoid assuming shell-specific bash commands on Windows.
7. **Protect secrets**: `.env`, API keys, imported videos, temporary files and exports must be `.gitignore`d. Do not log sensitive source links unnecessarily.
8. **No silent rights bypass**: do not add downloader, watermark-stripping, unauthorized reposting, or TikTok auto-publish logic in this MVP.
9. **Report honestly**: list what actually works, what was tested, what needs user credentials and what remains incomplete. Never invent passing tests.
10. **Stop scope creep**: concentrate on local single-user MVP and low recurring cost.

### Suggested first commands (Windows PowerShell)

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
# Install project dependencies after creating pyproject.toml
python -m pip install -e ".[dev]"
# Verify FFmpeg is installed separately:
ffmpeg -version
ffprobe -version
streamlit run app/ui.py
```

The precise `pip install` command must match the generated `pyproject.toml`; update README if a different dependency setup is chosen.

### Immediate next action for the agent

**Start Milestone M0 now.** Deliver a runnable Streamlit skeleton, SQLite, video upload/preview, ffprobe metadata, source-rights fields, `.env.example`, and README. Then verify with a synthetic local MP4 fixture. After M0 succeeds, implement M1–M4 incrementally, reporting verified progress and blockers without claiming unfinished work is complete.
