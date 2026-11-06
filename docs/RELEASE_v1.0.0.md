# Fashion AI Localizer v1.0.0

Source release of the verified M0–M4 local Chinese→Vietnamese localization workflow. Requires Windows10/11x64, Python3.11, CPU-capable16GBRAM target, licensed Vietnamese fonts and FFmpeg/FFprobe with CPU H.264/AAC/libass/mov_text. Model/disk needs depend on selected providers; keep several GB free for runtime/models and additional space proportional to imported/generated media. No GPU required. This release is not a standalone Windows executable or installer.

## Install / first start

```powershell
git clone https://github.com/hphuc032/Fashion-AI.git
Set-Location Fashion-AI
git checkout v1.0.0
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-m4.txt
Copy-Item .env.example .env # Fresh install only; never overwrite existing config.
# Install FFmpeg/FFprobe from an official build linked by ffmpeg.org;
# put on PATH or set absolute FFMPEG_PATH and FFPROBE_PATH in .env.
.\.venv\Scripts\python.exe scripts/setup_m1_models.py --ocr --translation
.\.venv\Scripts\python.exe scripts/setup_m3_models.py --whisper --tts
# Set ASR_PROVIDER=whisper in .env for the CPU provider actually verified.
.\.venv\Scripts\python.exe -m streamlit run app/main.py
```

Open the localhost URL printed by Streamlit. Import only authorized MP4/MOV/MKV. Complete OCR/translation review, M2 replacement render, M3 approved dubbing, then Final Export Studio preview/review/final export. Output MP4 H.264/AAC/yuv420p48kmono plus UTF-8 ASS. Default subtitles burn into video; optional acknowledged mov_text track has player/style limitations. Original preset retains dimensions/aspect/FPS; TikTok9:16 uses padding unless crop explicitly confirmed. Manual corrections and rights confirmation are part of the workflow.

## Upgrade / backup

Stop the application and active workers first. Back up the entire existing storage directory and .env to a user-controlled location outside Git (SQLite, originals, models, outputs and local secrets). Never publish the backup. For a consistent SQLite backup while running use SQLite backup API rather than copying a database with active writes; stopping all writers is recommended. Update code/dependencies without replacing .env/storage. Startup performs additive migrations with a pre-upgrade SQLite backup; verify projects/exports before deleting any old code/runtime. To roll back, stop writers and restore the complete matching data/code backup, not just one DB file while retaining incompatible new artifacts.

## Verification / limitations

M4 PR#6 mergece1df24; exact acceptance, audit, tests and CI in M4_FINAL_ACCEPTANCE_REPORT.md/M4_TEST_REPORT.md/IMPLEMENTATION_LOG.md. Full actual-model219tests, real6s540×96025fpsH264/AAC video, browser download and VLC playback/user listening. Migration preserves existing rows. No broad long-form performance, linguistic quality, all-player or clean-machine installation claim. FunASR/Azure/GPU not tested; local Whisper/Argos/review/VAIS1000 route verified. Background separation is not implemented. M5 packaging starts only after this release is published. No credentials, user media, AI weights or generated video attached.
