# M4 final acceptance — 2026-11-06

PR [#6](https://github.com/hphuc032/Fashion-AI/pull/6), feature/m4-final-rendering → develop. Inspected head48792430fbfd0189f1a4421f8884194af43bb537, base3809a4cd71a60d3ecf4a1e5c9ca84ec265b78936. All ten feature commits and22changed files inspected. No submitted reviews or unresolved review threads at inspection. The master task explicitly authorizes merge after gates pass, stable release through a main PR, annotated v1.0.0 and GitHub Release; M5 remains gated on that release.

## Acceptance evidence

| Criterion | Result | Evidence |
|---|---|---|
|M2/M3 integration|PASS|Completed current same-project contracts, original/M2/M3 bytes preserved|
|Valid ASS/Unicode|PASS|UTF-8, correct accents in real libass output and VLC; timing0–1.42s|
|M3 timing/AV sync|PASS|Decoded waveform correlation0.9999840997308738, duration difference0s, stream starts0|
|Styles/burn-in|PASS|Glyph-checked layout/speaker/overlap tests, actual representative frames|
|Soft mode|PASS|Actual mov_text payload/language verified; ASS sidecar retained, style limitations disclosed|
|Dialogue exclusion|PASS|Explicit M3-only audio mapping, original-vs-dub regression, user listening|
|H264/AAC/FFprobe|PASS|Real6s540×96025fpsMP4,yuv420p48kmono,faststart,full video decode|
|TikTok9:16/Original|PASS|Real1080×1920fit/padding and original-size exports; crop confirmation tested|
|Preview/UI/history|PASS|Actual Final Export Studio, new preview and completed final job, persisted library|
|MP4/ASS download|PASS|Actual browser download events; both downloaded files byte-identical to render artifacts|
|Persistent jobs/library|PASS|SQLite reopen, retry/cancel/dead worker, reversible export trash tests|
|Previous features|PASS|Fresh complete219-test M0–M4 run, no failures/errors/skips|
|Real E2E/manual playback|PASS|Production Paddle→Argos/review→M2→Whisper→Argos/review→VAIS1000→M3→M4; browser and VLC playback|

Interactive run verified on the inspected runtime head in this conversation: selected original.mp4 project2aaccfc3-de1b-46aa-8b1b-90a419c31a55; generated6s preview5a3a541d, played to ended=true/currentTime6/duration6, unmuted/errorfree. User confirmed “Nghe rõ, không có vấn đề”. Rights/review acknowledged, final job3ef6e3bf COMPLETED, export2 opened, MP4/ASS downloaded through Streamlit buttons. Opened exact downloaded MP4 with official hash/signature-verified VLC3.0.24 portable, played to terminal pause, inspected early speech subtitle and later M2 captions. User confirmed “VLC phát rõ, không có vấn đề”. These are user hearing confirmations; no assistant claim of hearing system speaker audio.

Final download46015B; ASS667B. SHA25613f4f1d19e6873762f8e6cc7e9f6978999cf8db643aa951ace9fc3b8a06996e5. Existing completed job/report/SHA rechecked during master task. Full validation metadata and exact commands in M4_TEST_REPORT.md. Local ignored proof m4-final-download.jpg/m4-vlc-final.png; videos remain ignored, not release assets.

## Repository audit and limitations

127tracked paths audited before this report: zero credential-pattern hits, forbidden database/model/media/runtime files or files>1MiB. Reviewed .env.example contains placeholder keys only. .gitignore excludes local secrets, user storage, SQLite, audio/video/ASS, models, logs and binaries; no user media removed. Complete diff whitespace check passed.

Soft MP4 uses mov_text, not native ASS; player/style support varies. No background separation; only provenanced separated tracks can mix, otherwise disabled. Argos garment detail was manually corrected before approval. Actual FunASR/Azure/GPU, arbitrary long videos, all mobile players and general language/naturalness benchmarks remain NOT TESTED. Controlled-fixture acceptance does not imply these capabilities.

## Final checks / merge gate

Latest inspected run20 on4879243: M0/M3/M4 already succeeded, M1job127961838322 and M2job127961837950 still installing dependencies at inspection. Monitor to terminal, inspect logs on failure; never bypass these gates. Final local rerun and final report-head CI result will be recorded before merge. A report-only commit must also pass required hosted checks. Expected-head SHA protection is required for merge; no branch deletion.

Fresh local verification on inspected head: **219 passed in192.25s**, all M1_RUN_REAL/M2_RUN_REAL/M3_RUN_REAL/M4_RUN_REAL enabled, explicit portable FFmpeg9.0.2 paths. JUnit kept only at storage/temp/m4-final-acceptance.junit.xml. All18criteria in M4_TEST_REPORT.md verified for controlled fixture, including manual follow-up; no test changed to suppress failure. Report-only publication does not change runtime. Final hosted result/merge SHA are recorded in PR and implementation log handoff after gates finish.

Run20 ended cancelled while M1/M2 downloaded FFmpeg dependencies from azure.archive.ubuntu.com; logs contain repeated Ign/retries followed by “The operation was canceled”, before application tests. Run21 passed M0/M1/M2/M3, but live M4 logs reproduced stalled HTTP Azure downloads (libcodec2/libdav1d). Added reusable setup-media composite action selecting official HTTPS archive.ubuntu.com with signature checks unchanged, bounded30s network timeout/3retries, and --no-install-recommends. All five original suites/count/no-skip gates stay intact. This addresses observed runner setup failures, not a test failure suppression; verify the new head's full CI before merge.

Final merge gate satisfied on **67b8ffb9886c4c8cc757244b01da4260a1e577eb**, [run22](https://github.com/hphuc032/Fashion-AI/actions/runs/42241677009): allfivejobs SUCCESS, actual log totals26/79/31/38/41 with zero failures/errors/skips. No unresolved reviews/threads; head and develop target rechecked. Marked ready, merged with expected-head protection and normal merge commit **ce1df24f20a46b9bb8a1fab6f5ed6381fc911e15**. PR API confirms merged=true; fetched origin/develop contains it. Feature branch retained. Release candidate release/v1.0.0 starts from this exact merge; main integration is separately gated through a release PR and full retest, not a direct main push.

## Report A — M4 and v1.0.0 COMPLETED

Fresh actual-model release candidate retest **219passed153.44s**, zero skips/failures/errors. Release metadata/version/source-install instructions entered develop through PR#7 after five green jobs. Historical M0 README/log conflicts with stable main were resolved on release branch, preserving all records; docs-only PR#9 passed five jobs and merged into develop **51f12832e8feb13b0db12374292e2d6d2284ae64**. No runtime/test difference from verified candidate.

Release [PR#8](https://github.com/hphuc032/Fashion-AI/pull/8) develop→main passed all five required jobs on exacthead51f1283 ([run28](https://github.com/hphuc032/Fashion-AI/actions/runs/42244336198)); no unresolved reviews/threads, normal expected-head merge **9c13cb0fc26cbdb43e9bb21e31a58dbb330ec9d3**. Main subsequent push CI [42244772335](https://github.com/hphuc032/Fashion-AI/actions/runs/42244772335) also completed success. Version1.0.0 is shared by package/UI; README/CHANGELOG/install/backup/known-limitations updated.

Annotated tag **v1.0.0**, tagobjectfb5574aabf9cc80dc39a9c584348dc4516494a26, peeled to exactlymain9c13cb0; pushed and remote refs verified. [Fashion AI Localizer v1.0.0](https://github.com/hphuc032/Fashion-AI/releases/tag/v1.0.0) published, not draft/prerelease, releaseid436674171; creation and GET retrieval verified. Source release only: no Windows installer/executable/models/private user media attached. All feature branches retained, no force push or direct main commit. M5 began only after this release was confirmed and is separately unmerged/unreleased.

Known release limitations remain: reviewed/manual corrections needed for language accuracy, soft mov_text styling/player variance, no automatic background separation, no actual FunASR/Azure/GPU/general long-form/clean Windows installer benchmark. All specified M4 criteria were verified on the controlled original/licensed fixture, including actual downloads/VLC/user listening; this does not remove those broader limitations.
