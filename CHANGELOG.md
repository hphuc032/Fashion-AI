# Changelog

## 1.1.0.dev0 — Unreleased M5 preview

- One-folder PyInstaller launcher with managed CPython3.11/dependencies/FFmpeg; external models and persistent AppData.
- Single-instance ownership/health checks, clean stop/restart, curated diagnostics/version/data directory display.
- Additive schema60 model-download history; explicit CPU model catalog with pinned SHA256, safe staging/cancel/recovery and shared heavy-work exclusion.
- Desktop & Models page, checksum verification, source/license/download sizes; no startup model download.
- Private backup/restore with SQLite checkpoint and manifest verification; expired top-level temp cleanup only. Data survives code folder relocation/upgrades.
- Windows build/first-run/upgrade/uninstall/troubleshooting instructions and actual packaged-runtime tests. Clean Windows/installer/signing qualification remains NOT TESTED; no installer orv1.1.0 published.

## 1.0.0 — 2026-11-06

First complete M0–M4 source release. M4 PR#6 merged into develop as ce1df24f20a46b9bb8a1fab6f5ed6381fc911e15 after five green CI jobs on67b8ffb and user-confirmed interactive acceptance.

- Import authorized MP4/MOV/MKV, metadata, immutable originals, SQLite project library.
- Local Chinese PaddleOCR, Argos zh→en→vi translation, manual review and conservative Smart Auto Review.
- M2 masking/Vietnamese on-screen replacement and preview/render jobs.
- M3 Whisper CPU recognition, editable/approved speech, local Vietnamese TTS, synchronized WAV master.
- M4 styled UTF-8 ASS, libass burn-in, acknowledged mov_text soft MP4 plus ASS sidecar, H.264/AAC export, original/TikTok presets, previews and persistent export library.
- Additive SQLite migrations/backups; managed paths, local workers, safe cancel/recovery, no silent model download or automatic platform publishing.
- CI official HTTPS Ubuntu media mirror with bounded retries; all required suites remain gated with zero skips.

Verified Windows CPU environment: Python3.11.18, FFmpeg/FFprobe9.0.2. Required hosted counts26/79/31/38/41 passed; full actual-model local219 tests passed before release candidate retest. Browser downloads and VLC playback verified on original licensed/synthetic fixture; user confirmed clear audio. Release candidate exact rerun recorded in implementation log.

Limitations: source install still requires Python/dependencies/FFmpeg/model setup; Windows desktop packaging is M5 and is not included. Translation/ASR require review; no general accuracy/naturalness benchmark. Soft MP4 does not preserve all ASS styling across players. No automatic dialogue/music separation, scraping or social publishing. Actual FunASR/Azure/GPU and clean Windows machine installation not tested for this release. No media/model/credentials bundled.

## 0.1.0

Previously approved M0 foundation release. Intermediate milestones integrated through reviewed feature PRs on develop; historical verification remains in docs.
