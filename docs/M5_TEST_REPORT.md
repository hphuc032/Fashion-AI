# M5 verification — local Windows checks PASS; clean-machine qualification IN PROGRESS

Delivery date: 2026-11-07 (Asia/Saigon). Local implementation/build tests completed; no claim that clean Windows/installer acceptance is complete.

Base approved develop51f12832e8feb13b0db12374292e2d6d2284ae64; v1.0.0 released onmain9c13cb0 viaPR#8, annotatedtag verified remotely. M4PR#6mergece1df24. Required release CIrun28allfivejobs success; fresh actual-model release candidate219passed153.44s. M5 plan committed first5c387e1. No M5 merge/main modification/tagv1.1.0/installer publication authorized.

Architecture: PyInstaller6.22.0 one-folder launcher + managed relocatable CPython3.11/pinned site-packages, actual Streamlit resources/native libraries, application code and FFmpeg/FFprobe. Existing -m worker architecture retained by using a real bundled interpreter. Models/data/config/logs external. Build manifest/SHA/third-party notices, not model weights/media/secrets. launcher lock/readiness/ownership/shutdown, data backup/restore/temp cleanup, explicit checksum-pinned model catalog/downloader/persistent work slot and Desktop & Models status page added. Files/commands: M5_IMPLEMENTATION_PLAN.md and WINDOWS_INSTALLATION.md.

## Exact automated results

- Initial source full run: **242 passed in182.58s**, all M1–M5 real flags enabled, before final WAL/cleanup regressions were added.
- Intermediate packaged run: **243 passed in249.47s**, before final WAL backup regression.
- Final packaged-runtime full run: **244 passed in235.04s**, zero failures/errors/skips. Counts:219 approved M0–M4 +24 deterministic M5 +1 real HTTPS model download. All M1_RUN_REAL/M2_RUN_REAL/M3_RUN_REAL/M4_RUN_REAL/M5_RUN_REAL=1. Ignored JUnit storage/temp/m5-packaged-final.junit.xml.
- Final runtime is the actual relocated distribution at dist/Fashion AI Localizer QA/_runtime/python.exe; app/pytest/CTranslate2 import paths were asserted to be under the distribution, app.core.config.ROOT=_code. PATH contains only Windows/System32, not developer Python or FFmpeg. Tests themselves are external QA source files, not shipped test assets; app/native dependencies and FFmpeg are loaded from the package. Existing production subprocess workers run with that real packaged interpreter and code directory.
- Real OCR/Argos/Whisper/Vietnamese TTS/M2/M4 end-to-end tests passed using external verified model storage. Original licensed/synthetic6sChinese fixture→reviewed M2/M3→preview/final MP4/cancel/reopen ran through actual packaged workers, not mocked AI. M4 output H264/AAC/yuv420p,540×96025fps,6s,48kmono,faststart, decoded waveform/frames validated. Model/linguistic quality limitations remain those of M3/M4.
- M5 unit checks cover lock exclusion, startup/config/database/media preservation, scoped loopback readiness, unrelated/reused PID protection, backups/restore/path/hash/WAL behavior, temp-only cleanup, offline inventory/corrupt model, HTTPS/hash/cancel/partial cleanup, download job exclusion/dead recovery, staged ownership cleanup, UI no-startup-download and build filter retaining native model modules while excluding weights/media.

## Actual Windows executable / data / model checks

PyInstaller6.22.0 build ran on Windowsx64 (reported Windows10.0.26300) with CPython3.11.18. One-folder executable built successfully; managed runtime/libraries/Streamlit resources/tools assembled with licenses/dependency inventory/file SHA manifest. Initial complete payload20,585files/1,411,274,183bytes before QA refinements. Subsequent fixes rebuilt the launcher and refreshed only allowlisted code/docs in the stopped local QA artifact, regenerated manifest; final packaged full suite above passed. Runtime was not replaced by a developer venv.

Actual executable --check succeeded with CPUlibx264/AAC/libass/mov_text and system Arial/Segoe UI. First launch with empty data/models initialized SQLite, reported six missing supported models, served dashboard and opened the default browser. UI v1.1.0.dev0/paths/status visible. No model download on startup. Explicit UI OCR download was acknowledged, completed, progress persisted and both models showed **verified** after SHA check. Separate real download test also passed1test in4.54s. Models reside outside the distribution.

Actual default %LOCALAPPDATA%/FashionAILocalizer was initialized/checked; no prior config/database overwritten. Package folder moved to **dist/Fashion AI Localizer QA** (spaces in path); executable restarted successfully, same config/database/downloaded OCR retained. Second launch reused identical server PID rather than starting another server. --stop returned0, launcher returned0, status=stopped; immediate backup after stop returned0 after fixing a lock-release race. Browser starts only after token-scoped loopback health passes. No public port binding or OS service/registry install.

Actual private backup→restore→environment check passed:12files in final tested backup/restore, original source data left intact. Restore uses a new empty destination and validates manifest. Early real WAL backup failed because sqlite3 context managers did not close/checkpoint before manifest hashing; fixed using explicit closing/checkpoint and excluding transient DB sidecars, with regression test. Invalid backup was not accepted. Backup may include private config/API keys and must remain local/private.

Legacy upgrade experiment: SQLite-consistent copy of populated M4 demo DB/media (source not replaced), package initialized schema60 and exactlyone pre-v60backup. Compared every row/value against that pre-migration snapshot: **16pre-existing tables/56rows identical**. Schemas1/20/30/40/50/60 coexist. Comparison uses the captured pre-upgrade snapshot to keep the baseline immutable. Actual packaged dashboard reopened original project and both M4 exports; video readyState4/duration6/error absent. Ignored UI proof docs/screenshots/m5-packaged-models.jpg and m5-packaged-export-history.jpg.

## Build / maintenance commands

Complete build instructions and first-run/upgrade/source-data migration/uninstall guidance: WINDOWS_INSTALLATION.md. Build tools pinned in requirements-build.txt; FFmpeg binaries, full license and corresponding source/build notice supplied explicitly. Final folder/ZIP/checksum remain under ignored dist; no binary/model/media uploaded to GitHub or attached to a Release. Distribution ZIP includes only manifest-listed files, excludes QA bytecode/cache/data and is CRC-verified; final archive size/SHA recorded below after archive completes.

```powershell
# Run the local QA build; default AppData also tested separately.
& '.\dist\Fashion AI Localizer QA\FashionAILocalizer.exe' --data-dir '.\storage\m5-first-run' --check
& '.\dist\Fashion AI Localizer QA\FashionAILocalizer.exe' --data-dir '.\storage\m5-first-run'
& '.\dist\Fashion AI Localizer QA\FashionAILocalizer.exe' --data-dir '.\storage\m5-first-run' --stop
# Use new backup/restore destinations; never overwrite an existing data directory.
& '.\dist\Fashion AI Localizer QA\FashionAILocalizer.exe' --data-dir '.\storage\m5-first-run' --backup '.\storage\private-new-backup'
& '.\dist\Fashion AI Localizer QA\FashionAILocalizer.exe' --data-dir '.\storage\fresh-restored' --restore '.\storage\private-new-backup'
```

## Status matrix

| Area | Status | Limit |
|---|---|---|
|Packaging architecture/build/executable launch|COMPLETED local|One-folder managed runtime, no installer|
|First run, FFmpeg/fonts/Streamlit/native resources|PASS local|Developer Windows host, isolated data is not clean OS|
|Duplicate/stop/restart/relocation|PASS|Owned process checks; unrelated processes untouched|
|SQLite/config/media upgrade/backup/restore|PASS|Snapshot16tables/56rows, WAL regression fixed|
|Model discovery/explicit OCR download/SHA|PASS|Other supported artifacts pinned from verified models; do not claim every remote download was repeated in UI|
|OCR/translation/TTS/M2/M4 packaged functions|PASS|Real-model worker tests, controlled fixture|
|Portable code removal/data separation|PASS by relocation/data preservation|Actual installer/uninstaller NOT TESTED|
|Clean Windows10/11 install/upgrade/uninstall|NOT TESTED|No clean VM/image available|
|Signing/SmartScreen/public binary licensing qualification|NOT TESTED|Development artifact only; full public redistribution qualification outstanding|
|M5 feature PR|Prepared after audit/checks|Retain Draft, no review-ready/merge orv1.1.0 publication|

Clean Windows10/11VM, installer/uninstaller, OS integration/SmartScreen/signing, arbitrary machines/fonts/long videos and general model-quality benchmarks: **NOT TESTED**. An isolated data folder on the developer host is not a clean Windows environment. No installer will be published without that gate. The local distribution is a development artifact only.

## Final local artifact and audit

Local ZIP: **dist/FashionAILocalizer-1.1.0-dev-win64.zip**, **504,765,230bytes**, **19,620files**, creation/CRC verification414.98s on this host (not a generalized performance benchmark). SHA256 **2dd01effe5c653185d6372e18d485c5639df0683536bb13adf549ad64003c8f7**, also in sibling.zip.sha256. ZIP includes only manifest-listed files and distribution-manifest.json; QA bytecode/cache excluded. Extracted root name FashionAILocalizer-1.1.0-dev-win64; current QA folder dist/Fashion AI Localizer QA. Local ZIP/executable remain ignored and unpublished. BAT start wrapper and PowerShell environment-check wrapper both exercised in the package with --check, exit0.

Final source/config/docs audit **150paths**: no credentials/private media/databases/downloaded weights/runtime binaries/generated ZIP/screenshots, no file>1MiB; credential-pattern scan and whitespace checks clean. Distribution sources/model catalog are metadata/code, not downloaded model weights. WindowsSandbox.exe absent and no VBoxManage/vmrun found on PATH; no clean Windows VM available, no OS virtualization/security feature enabled to manufacture a clean-install claim.

Implementation commits:5c387e1(plan),0de9ed1(external data/models),cd70b0f(runtime/launcher/build),5fe3547(UI),367f4f9(tests/CI); final documentation/publication commit and PR URL recorded in PR/handoff. M5 remains IN PROGRESS for clean-machine qualification; Draft PR only, no review-ready request, auto-merge, main modification orv1.1.0 release. CI keeps all five old suites/count gates and adds24deterministic M5 checks without skips; remote results reported on the final pushed head.

Normal feature push published implementation/docs head8c8614fdd6893bf196cebec3547e371d719adf05. Created open/unmerged **Draft [PR#10](https://github.com/hphuc032/Fashion-AI/pull/10)** targeting develop. [Branch](https://github.com/hphuc032/Fashion-AI/tree/feature/m5-windows-packaging). Final docs-only publication commit/check results are in PR/final handoff. No reviewers requested while clean-machine gate remains unverified; no binary asset uploaded or M5 merge/tag.
