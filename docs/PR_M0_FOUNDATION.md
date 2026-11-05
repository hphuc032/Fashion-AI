# feat(m0): add local video import foundation

Base: `develop` · Head: `feature/m0-foundation`

Creators need a persistent local workspace before video localization can be added. This change lets a user upload a local MP4/MOV/MKV, validate its container and metadata through FFprobe, retain the unchanged original and reopen it from a Vietnamese Streamlit dashboard backed by SQLite.

## Changes

- Pydantic environment configuration and JSON console logging; SQLAlchemy 2 project records with SQLite sessions.
- Chunked, size/duration-bounded import into UUID paths, safe filename handling, source-rights metadata and submission-token idempotency.
- Dark dashboard, sidebar navigation, recent projects, metadata and original video preview; browser codec warnings.
- Automated validation/persistence/dashboard tests and a generated synthetic video fixture script.
- Windows setup, architecture plan, actual M0 verification results and local Git workflow documentation.

## Validation

Windows, Python 3.11.18, FFmpeg/FFprobe 9.0.2. Latest complete run on 2026-11-05: **26 passed in 1.75s, zero skipped** (`python -m pytest -q --tb=short`, with real binaries configured).

Real integration test generates a silent vertical H.264 MP4, imports it, checks metadata and unchanged bytes, and rejects corrupt bytes. Other tests cover bad metadata, unsupported/unsafe names, missing executable, file-size and duration limits, unique IDs, retry idempotency, database reopen and Streamlit navigation.

Earlier M0 browser verification: uploaded a synthetic 360×640 / 25 fps / 3-second video through Brave, verified metadata, clicked Play successfully and reopened the same project after restarting the server. Screenshots remain local under ignored docs/screenshots; no media or private project DB is included in Git.

## Limits and scope

FFprobe validates metadata rather than decoding every frame. MOV/MKV browser playback and audio playback have not been verified end to end. Streamlit buffers incoming files in RAM. Power interruption may leave orphan media; schema migrations are deferred. M0 is local single-user only.

No OCR, translation, dubbing, subtitles, export/rendering, downloading or TikTok posting is included. No paid service or credentials required. M1 remains blocked on owner approval of M0.

## Review and integration

Review the diff against develop and confirm ignored secrets, databases, videos, models and local runtimes are absent. After owner approval, merge this PR into **develop** and rerun the suite there. Do not merge into main or publish a release as part of this PR. Once M0 is verified and explicitly approved, propose `v0.1.0` for the approved stable main commit; do not create or publish the tag yet.
