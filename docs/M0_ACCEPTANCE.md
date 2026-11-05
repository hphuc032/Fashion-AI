# M0 acceptance report — 2026-11-05

All source and docs are under Fashion-AI. No existing source was overwritten (directory started empty). Parent video is untouched. Files created:

```text
AGENT_MVP_SPEC.md                  Copy of parent reference
.env.example, .env                 Defaults / gitignored portable local settings
.gitignore, .streamlit/config.toml Theme, localhost, privacy defaults
requirements.txt, pytest.ini
README.md
app/__init__.py, app/main.py
app/core/{__init__,config,logger}.py
app/database/{__init__,models,session}.py
app/services/{__init__,video_service,storage_service}.py
app/ui/{__init__,dashboard,components}.py
app/utils/{__init__,validators}.py
tests/test_m0.py, tests/test_dashboard.py
scripts/generate_test_video.py
docs/M0_IMPLEMENTATION_PLAN.md
docs/IMPLEMENTATION_LOG.md
docs/M0_ACCEPTANCE.md
docs/screenshots/{m0-dashboard,m0-library}.jpg
```

Generated/ignored artifacts: .venv (exploratory 3.14), .venv311 (validated Python 3.11.18), .tools (portable Python/FFmpeg), storage (SQLite, synthetic fixture and one browser-uploaded synthetic project), Python/test caches.

| Acceptance criterion | Result | Evidence |
|---|---|---|
| Application starts on Windows | PASS | Python 3.11.18, Streamlit bound to 127.0.0.1:8501 |
| Dashboard loads correctly | PASS | Brave navigation + dark UI screenshots + AppTest |
| Valid video upload | PASS | Actual browser upload of generated 3-second vertical MP4 |
| FFprobe extracts metadata | PASS | Real FFprobe 9.0.2; 360×640, 25 fps, H.264, silent, 9:16 |
| Browser preview for supported codec | PASS | H.264 fixture loaded, error=null, clicked Play, paused=false |
| SQLite stores metadata | PASS | Browser library + persistence tests |
| Recent projects appear | PASS | Overview count 1 and selector with synthetic.mp4 |
| Invalid/corrupted files rejected | PASS | Unit/mocked failure and real corrupted bytes in integration test |
| Reopen preserves projects | PASS | Server stopped/restarted and browser reloaded; same project retained |
| Automated tests pass | PASS | 26 passed, zero skips on Python 3.11; final run 1.96s |
| No paid AI APIs required | PASS | No AI/API client or credentials used |
| HTTP server health | PASS | Approved localhost health request returned ok |
| MOV/MKV real upload/playback | NOT TESTED | Extension/container logic exists; browser codec support varies |
| Audio playback | NOT TESTED | Synthetic fixture is silent; no-audio handling tested |
| Windows 10 specifically / other browsers | NOT TESTED | Verification on current Windows machine with Brave |
| Disk-full/power-loss recovery | NOT TESTED | Cleanup implemented for caught exceptions; interrupted orphan cleanup deferred |

No acceptance failure remains in the tested M0 flow. PASS does not imply untested codecs/operating-system variants work. Original bytes preserved in real import integration assertion. Filename/path limits, size/duration rejection, missing FFprobe, source validation, IDs and idempotency covered by automated suite.

## Run on this prepared machine

```powershell
Set-Location 'D:\tiktok\Fashion-AI'
.\.venv311\Scripts\python.exe -m streamlit run app/main.py
```

Already running on http://127.0.0.1:8501 at handoff; don't start a second process on the same port. Stop using Ctrl+C in the launching terminal when needed. Re-run tests:

```powershell
.\.venv311\Scripts\python.exe -m pytest -q
```

Fresh installation commands and configuration documented in README.md. M0 limitations: no AI, rendering/export or transcoding; local single-user use; metadata validation only; no migrations. Stop after M0.
