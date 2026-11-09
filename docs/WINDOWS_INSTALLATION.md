# Windows distribution — M5 development build

One-folder package, Windows10/11x64, CPU/16GBRAM target. No system Python/pip/FFmpeg setup for users: the folder contains a PyInstaller launcher, managed CPython3.11/pinned application libraries including Streamlit static resources, code and FFmpeg/FFprobe. Keep the whole folder together. Model weights are downloaded explicitly into external user data, never bundled. This local test build is **not a clean-Windows-qualified installer**; do not publish it as one.

## First run

1. Extract the complete ZIP to a writable application/version folder; verify ZIP SHA256 against its sibling.sha256 file. Do not mix files from different builds.
2. Run FashionAILocalizer.exe (or scripts/start_windows.bat). Console shows status/data/log path; browser opens only after the loopback server is healthy. Keep console open. A second launch reuses the same data-root instance.
3. Default data is %LOCALAPPDATA%\FashionAILocalizer. config.env created once, never overwritten; SQLite/media/outputs under storage, external models under models, diagnostics under logs. Version shown in sidebar. Data is separate from code. --data-dir and --models-dir can select explicit existing local locations, not required for normal first use.
4. Open Desktop & Models: inspect missing models, source/licenses/download sizes; explicitly acknowledge and download OCR/translation/ASR/TTS groups. View progress/cancel/error; use SHA check to validate installed content. CPU defaults Whisperbase/local VAIS1000/Argos. Download interruption never replaces a valid installation. Unsupported FunASR remains manual.
5. Import an authorized video, complete M1 review→M2 render→M3 speech review/dub→M4 preview/final. Downloads use browser save destination. Source/creator attribution must be preserved.

Some first-use package/native DLL behavior requires clean-machine qualification; if a DLL is missing see troubleshooting, do not disable Windows protection. Licensed Arial/Segoe UI normally present on Windows; DejaVu Sans fallback supported. Runtime/models need multiple GB plus space for every imported/generated video; actual build/model sizes and timings are in M5_TEST_REPORT.md, not a hardware benchmark. Keep enough free disk for staging and backups. No GPU required.

## Stop / status

Ctrl+C in launcher stops only its owned server/worker tree. Or run:

```powershell
.\FashionAILocalizer.exe --stop
.\FashionAILocalizer.exe --check
```

Use the same --data-dir if overridden. desktop-status.json records local status/URL/PID ownership; do not edit it. A stale PID is not killed unless executable/create-time/token match. Startup recovers dead job states; verify failed/cancelled jobs and retry explicitly.

## Upgrade, backup and restore

Migrating from the v1.0 source checkout: stop its Streamlit/workers, keep a private backup, then copy the existing storage folder into a **new** M5 data directory as its storage subfolder. Keep the original unchanged. Copy reviewed provider/secret settings into the new config.env without replacing STORAGE_ROOT/DATABASE_URL with old code paths. Existing models can stay external: launch with --models-dir pointing to the old storage/models, or copy its contents into the new data/models. Startup adds schema60 with a pre-upgrade DB backup; verify original projects/exports before removing old code. This is a file migration, not an automatic import or a reason to overwrite a populated destination.

Stop all writers. Keep old application folder and entire data directory until validation completes. Extract new build to a separate version folder and start it with the same data directory; it reuses config and performs additive migrations with SQLite backup. Never copy a packaged database over user data. Do not run older versions against a newly upgraded database without restoring its matching backup.

```powershell
# Choose new backup/restore paths outside the active data directory.
.\FashionAILocalizer.exe --backup 'D:\FashionAIBackups\before-upgrade'
.\FashionAILocalizer.exe --data-dir 'D:\FashionAIRestored' --restore 'D:\FashionAIBackups\before-upgrade'
.\FashionAILocalizer.exe --data-dir 'D:\FashionAIRestored'
```

Backup includes local config (which may contain API credentials), DB and artifacts/models, so keep it private. SQLite backup API and file SHA manifest are used; restore refuses nonempty destinations and invalid hashes/paths. This can be large; never publish a backup or add it to Git.

Safe optional cleanup, only while stopped:

```powershell
.\FashionAILocalizer.exe --clean-temp --confirm
```

Only top-level storage/temp .tmp/.part files older than24h are removed; no project/original/audio/model/export deletion. Nested project caches remain user data. Uninstall portable application by removing its application/version folder after stopping; **retain the external data folder**. No registry uninstaller/service/system-wide install provided. Clean-machine installer/upgrade/uninstall qualification remains explicitly NOT TESTED until a clean Windows VM is available.

## Build from source (maintainers)

Use Windowsx64/Python3.11 and a relocatable CPython runtime with the same pinned application libraries as requirements-m4.txt. Install build requirements only in the build environment. Supply a trusted FFmpeg/FFprobe build and a notice including its license and corresponding source/build URL. Third-party licenses remain in runtime/.dist-info; dependencies inventory and distribution SHA manifest are generated.

```powershell
python -m pip install -r requirements-m4.txt -r requirements-build.txt
python scripts/build_windows.py --python-home 'D:\CPython311' --site-packages 'D:\BuildEnv\Lib\site-packages' --ffmpeg 'D:\FFmpeg\bin\ffmpeg.exe' --ffprobe 'D:\FFmpeg\bin\ffprobe.exe' --ffmpeg-notice 'D:\FFmpeg\source-and-build-notice.txt' --ffmpeg-license 'D:\FFmpeg\LICENSE' --output 'D:\BuildOutput\FashionAILocalizer-1.1.0-dev-win64'
```

Output folder must be new; no overwriting. Build emits folder/ZIP/ZIP.sha256 and distribution-manifest.json; no models, project data or.env copied. Test the executable and workers in the final extracted/relocated folder before review/publication. Current M5 branch targets1.1.0 but releasev1.1.0/installer publication is not authorized.
