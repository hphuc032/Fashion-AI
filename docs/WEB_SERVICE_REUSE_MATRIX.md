# W0 — Service reuse matrix

**VERIFIED** against develop `51f1283`; M5-only rows against `8ac209c`, not dependencies available on W0 branch. All paths are repository-relative. No engine is being rewritten or moved. The callable inventory below is extracted from those immutable trees; semantics in this matrix are source-reviewed. Tests listed are existing coverage, not a claim they were rerun in W0.

Categories: **AS-IS** = REUSE AS-IS; **ADAPTER** = REUSE WITH THIN API ADAPTER; **REFACTOR** = REFACTOR REQUIRED; **NEW** = NEW IMPLEMENTATION REQUIRED; **DEPRECATED** = DEPRECATED / NOT NEEDED for Web runtime (preserved for fallback).

## Capability contracts and integration

| Existing component / category | Exact source / main symbols | Current responsibility and input → output | DB / file dependencies | Web integration and required changes | Existing tests / risk |
|---|---|---|---|---|---|
| Configuration / ADAPTER | `app/core/config.py`: Settings, load_settings | Environment + ROOT/.env → validated Settings, absolute local paths | ROOT/.env on develop; FASHION_AI_ENV_FILE selector only on M5; no DB | Web profile adapter using explicit process env; whitelist public DTO; never return model_dump wholesale | `test_m0.py`; high: settings precedence/root mix-ups |
| Logging / ADAPTER | `app/core/logger.py`: EventFormatter, configure_logging | LogRecord → JSON stderr events | worker log files owned by managers | Add request IDs, secret/path filtering and rotation; don't expose raw worker logs in API | `test_m0.py`; medium: current formatter isn't general secret scrubber |
| Persistence / ADAPTER | `app/database/session.py`: create_database; `migrations.py`: migrate | SQLite URL → session factory; auto additive migration | SQLite/WAL/SHM, pre-upgrade backups, ORM metadata | Runtime init only after schema/profile approval; W1 health must not call factory on live DB | `test_m1_integration.py`, milestone tests; high |
| Validation / AS-IS | `app/utils/validators.py`: SourceInfo, validate_source, validate_filename, UserError | Rights/URL/filename → validated source metadata or safe error | No DB/files | Preserve rules; wrap UserError in typed HTTP mapping | `test_m0.py`; low |
| Video probe / AS-IS | `app/services/video_service.py`: VideoMetadata, parse_metadata, probe_video | Managed video path + suffix + executable → duration/dimensions/fps/codecs/aspect | FFprobe, local file | Bounded probe off async loop; retain container validation and 30s bound | `test_m0.py`; medium: hostile native media parser |
| Import/storage / ADAPTER | `app/services/storage_service.py`: import_video, list_projects, resolve_media | Seekable BinaryIO + filename + SourceInfo + UUID token → persisted Project; list → ORM rows | projects; `projects/{uuid}/source/{uuid}.{ext}` | Spool/stream UploadFile, keep atomic Project creation; add pagination and DTO projection | `test_m0.py`, `test_m1_integration.py`; high: cancellation/partial cleanup |
| CRUD drafts / NEW | No current draft/update/delete project service found | New metadata/archive request → safe persisted outcome | Existing Project non-null source fields and dependent FKs | No empty Project insertion; add controlled metadata update and future archive design, no cascade source deletion | New W2 tests required; high |
| Frame extraction / AS-IS | `app/services/frame_extractor.py`: SampledFrame, extract_frames, source_hash | Project source + times/settings + cancel callback → iterator of cached sampled frames | `projects/{id}/frames/{hash}-v1-{side}/*.png`; FFmpeg/FFprobe | Call only in worker or bounded preview service; retain rotated display coordinate behavior | `test_frame_extractor.py`, `test_m1_real.py`; medium |
| OCR normalization / AS-IS | `app/providers/ocr/paddle_provider.py`: PaddleProvider.detect, normalize_result | SampledFrame → Detection list with original-display pixel bbox/polygon/confidence/time | Paddle mobile det/rec local model dirs | Preserve Python lazy engine and version normalization | `test_ocr_service.py`, `test_m1_real.py`; medium |
| Tracking / AS-IS | `app/services/text_tracker.py`: Detection, Segment, group_detections | Detections + interval/duration/thresholds → grouped timed text segments | No DB; array/JSON bbox `[x,y,width,height]` | Return DTOs without changing detection-time semantics | `test_text_tracking.py`; medium |
| OCR/translate admission / REFACTOR | `app/services/ocr_service.py`: queue_job, run_job, request_cancel, latest_job | Project/kind/selected IDs/replace flag → OCRJob → persisted detections/segments or translations | ocr_jobs, text_segments, ocr_detections; Settings snapshot | Preserve worker, expose transactional admission seam for durable HTTP idempotency (no token parameter today) | `test_ocr_service.py`, `test_job_manager.py`, `test_m1_integration.py`; high |
| Translation / AS-IS | `app/services/translation_service.py`: TranslationService.translate, make_provider | Chinese string + cancel → `(translated_text, provider_identity)` | translation_cache keyed by identity/context/text; local Argos models | Keep timeouts, retries and versioned cache; manual mode stays explicit | `test_translation.py`, `test_m1_real.py`; medium |
| Argos inference / AS-IS | `app/providers/translation/argos_provider.py`: ArgosProvider | zh caption → glossary match or local zh→en→vi output | two translate-*-1_9 packages, CT2 int8 and SentencePiece | No JS translation engine or implied cloud translation | `test_translation.py`, `test_m1_real.py`; medium: semantic quality |
| Text reads/edit / ADAPTER | `app/services/ocr_repository.py`: get_project, project_source, list_segments, list_detections, save_reviews | UUID and edits `{id,revision,...}` → project/rows or atomic edits | projects, OCR/text segments, source identity/size | Add typed whitelist DTOs and pagination; preserve optimistic revisions and project scoping | `test_m1_integration.py`, `test_m1_ui.py`; high: stale edits |
| Smart Review / ADAPTER | `app/services/translation_review_service.py`: evaluate, effective_state, review_batch | Text/confidence → Evaluation; selected revisions/action/confirmation → counts | segment_reviews, review_events, text_segments | Keep partial counts and explicit bulk confirmation; expose effective state separately from legacy review_status | `test_smart_review.py`; high: do not overstate auto approval |
| M2 config / ADAPTER | `app/services/replacement_repository.py`: save_config, snapshot_items, validate_snapshot | Segment ID + ReplacementSettings → persisted config / fingerprinted snapshots | text_replacement_configs, segments, detections, optional review hashes | Typed config adapter preserving pending/tracking/override acknowledgments | `test_m2.py`; high |
| M2 compositor / AS-IS | `app/services/text_compositor.py`: ReplacementSettings, compose, region_at | BGR ndarray + time + item snapshots → BGR frame, warnings | NumPy/OpenCV/Pillow; no DB | Retain same preview/render function, strict final checks | `test_m2.py`; medium |
| Inpainting / AS-IS | `app/services/inpainting_provider.py`: InpaintingProvider, OpenCVInpainting.apply | ROI ndarray + mask + radius → repaired ROI | OpenCV Telea CPU; no downloaded inpaint model | Keep solid/blur/inpaint/overlay; no claim of neural text removal | `test_m2.py`; medium: visual quality |
| Unicode layout / AS-IS | `app/services/text_layout.py`: TextStyle, available_fonts, load_font, text_layer | Text/box/style → RGBA layer/layout report | Windows Arial/Segoe UI or DejaVu, fonttools glyph map | Offer allowlisted font names, never browser font paths | `test_m2.py`, `test_m4.py`; medium |
| M2 preview / ADAPTER | `app/services/render_preview.py`: preview_frame | Project UUID + timestamp → before/after PIL images + warnings | source, current snapshots, bounded preview PNG cache | Encode managed preview asset ID, run off request event loop | `test_m2.py`; medium |
| M2 jobs/render / ADAPTER | `app/services/render_jobs.py`: queue_render, RenderManager, run_render, cancel_render; `video_renderer.py`: render_video | UUID request token + quality/rights/regions → RenderJob → H264 localized MP4 | render_jobs; source SHA; staging partial; FFmpeg decoder+encoder | Lifespan-owned manager and opaque job DTO; preserve transactional publication | `test_m2.py`, `test_m2_real.py`; high |
| M2 output contract / AS-IS | `app/services/replacement_contract.py`: localized_video | Project → validated current M2 artifact dict | completed RenderJob, current config/review/source hashes, FFprobe | Mandatory M4 input, never fall back to original video | `test_m4.py`, `test_m4_real.py`; high |
| Audio extraction / AS-IS | `app/services/audio_extractor.py`: extract_audio, audio_info, ffmpeg | Project + cancellation → original.mka and mono16k ASR WAV | source-hash audio directory, FFmpeg | Worker only; retain original audio and source SHA | `test_m3.py`, `test_m3_real.py`; medium |
| ASR / AS-IS | `app/providers/asr/{base,whisper_provider,funasr_provider}.py`: SpeechPhrase, make_asr, WhisperProvider, FunASRProvider | WAV/chunk + cancellation → timed SpeechPhrase list | local Whisper int8 or timestamp-capable FunASR; optional local VAD/speaker dirs | Keep local_files_only / trust_remote_code=False; missing model is actionable error | `test_m3.py`, `test_m3_real.py`; high: optional FunASR not historically accepted |
| Speech normalization / AS-IS | `app/services/speech_segmentation.py`: normalize_phrases | Chunk-local phrases + offset + duration + previous → validated merged absolute phrases | No DB | Keep overlap/dedup/timestamp checks | `test_m3.py`; medium |
| Speech review / ADAPTER | `app/services/speech_repository.py`: list_speech, save_speech, save_speaker, speaker_settings, fingerprint | Speech revisions/voice settings → atomic rows / voice map | speech_segments, speaker_profiles, dub_jobs | Separate `/speech-segments`, speaker DTOs; clear cloud confirmation on persisted profiles | `test_m3.py`; high |
| Local/cloud TTS / AS-IS | `app/providers/tts/{base,local_tts_provider,azure_tts_provider}.py`: VoiceSettings, make_tts, LocalTTS, AzureTTS | Text + voice + output + cancel → mono WAV | VAIS1000 ONNX/tokens/espeak, or Azure env credentials and HTTPS | Backend-only credentials; explicit per-operation cloud confirmation; no source-media upload provider exists | `test_m3.py`, `test_m3_real.py`; high: external text disclosure |
| Dubbing stages / AS-IS | `app/services/dubbing_service.py`: transcribe, translate_speech, synthesize_cached, generate_audio | Project/job snapshots → phrases/translations/audio rows/master staging WAV | speech/dub tables; audio/tts-cache; original audio and manifests | Worker calls preserved; API only queues operations | `test_m3.py`, `test_m3_real.py`; high |
| Audio sync / AS-IS | `app/services/audio_sync_service.py`: synchronize, assemble_timeline | WAV + slot + VoiceSettings → timing metadata; segments → 24k mono timeline | soundfile block IO, FFmpeg atempo/loudnorm/limiter | Preserve conservative .85–1.2 adjustment and fail long speech rather than truncate | `test_m3.py`; medium |
| M3 jobs / ADAPTER | `app/services/dub_jobs.py`: queue_dub, run_dub, cancel, DubManager | Project/token/kind/voice/IDs/ack → DubJob → audio artifacts | dub_jobs, dubbed_audio_segments, speech; original source hash | Facade maps native stages, supervisor lifespan and guarded retry | `test_m3.py`, `test_m3_real.py`; high |
| M3 output contract / AS-IS | `app/services/dubbing_contract.py`: approved_dub | Project → verified assembled audio manifest | approved speech/current speaker settings/source & audio SHA, complete audio tree | Mandatory M4 input; no original Chinese speech fallback | `test_m4.py`, `test_m4_real.py`; high |
| Final configuration / ADAPTER | `app/services/final_render_config.py`: SubtitleStyle, FinalRenderConfig | Validated config → dimensions/style/render options | No DB until job snapshot | Reuse models behind path-free public DTO; resolve background by opaque asset ID | `test_m4.py`; medium |
| ASS / AS-IS | `app/services/subtitle_service.py`: generate_ass, escape_ass, soft_text_bridge | Approved speech/timing/style/window → UTF8 ASS + layout/overlap/font report | system fonts, job-local ASS; soft bridge SRT | Same layout/escaping/readability gates; keep full ASS download separately | `test_m4.py`, `test_m4_real.py`; medium |
| Final mux / AS-IS | `app/services/video_mux_service.py`: capabilities, timeline_options, run_mux | Valid M2/M3/ASS + config → H264/AAC MP4 + mux report | FFmpeg/libass/mov_text, staging fonts/progress/log | Preserve CPU encoders, faststart and current voice-only/validated-background semantics | `test_m4.py`, `test_m4_real.py`; high |
| Output validation / AS-IS | `app/services/final_output_validation.py`: validate_output, audio_evidence, visual_evidence | Output + references + config → metadata/sync/visual report | FFprobe, decoded audio/frames | Same validation before artifact publication; redact local paths from DTO | `test_m4.py`, `test_m4_real.py`; high |
| Final orchestration / ADAPTER | `app/services/final_render_service.py`: queue_final, run_final, exports, export_contract, move_export; `final_job_manager.py`: FinalManager | Token/project/config/preview ack → FinalRenderJob; export ID → verified artifact | final_render_jobs, subtitle_files, final_exports, all M2/M3 prerequisites | Keep matching preview signature, stale fingerprint checks, soft trash/restore; opaque range-aware streaming | `test_m4.py`, `test_m4_real.py`; high |
| Admission guard / AS-IS | `app/services/workload_guard.py`: ensure_idle | SQLite write-locked session → admission or UserError | all installed native job tables | Global slot across UI/API; M5 download table recognized only in M5 revision | job/M2/M3/M4 tests; high |
| HTTP/WS jobs / NEW | Not found | Public typed operation + idempotency key → job snapshots/events/errors | Future adapter mapping, native job tables | Single owner facade, same-transaction admission, reconnect snapshots, retry lineage; no parallel replacement queue | New W3 tests; high |
| Streamlit UI / DEPRECATED | `app/main.py`, `app/ui/*.py` | Streamlit forms/session state/cache → current interface | Services and DB | Not imported into API; recreate presentation in Next; preserve fallback until acceptance | dashboard/M1UI/M2/M3/M4 tests; medium |
| M5 launcher / REFACTOR (M5 only) | `app/desktop/launcher.py`: InstanceLock, owned_process, child_environment, main | CLI + data profile → managed Streamlit instance / maintenance | AppData lock/status, real CPython, logs | Reuse design/ownership, not current Streamlit-specific process detector/health URL; no W0 changes | `test_m5.py`; high |
| M5 model manager / ADAPTER (M5 only) | `app/desktop/model_manager.py`: inventory, queue_download, install_model; `models.json` | Catalog group + explicit queue → integrity status / model install job | schema60 model_download_jobs; pinned HTTPS/SHA/files | Offline inventory reusable after reviewed integration; thread lifetime needs API owner/recovery | `test_m5.py`, `test_m5_real.py`; high |
| M5 data maintenance / REFACTOR (M5 only) | `app/desktop/runtime.py`: backup_data, restore_data, cleanup_temp | Data root + new backup/destination → validated copy/file count | hardcoded storage/fashion_ai.db, hash manifest | Adapt to explicit Web profile and DB path; keep consistent SQLite backup and empty-target restore | `test_m5.py`; high |
| M5 build / DEPRECATED for W1 | `scripts/build_windows.py`, `requirements-build.txt`, start_windows wrappers | CPython/site-packages/FFmpeg → one-folder binary distribution | PyInstaller/build/dist/licenses | Preserve M5 workstream; Web startup is new native orchestration, no rebuild now | `test_m5.py`, historical packaged QA; medium |
| Health/settings/media transport / NEW | Not found | Authenticated local requests → redacted DTOs or streaming managed artifacts | Future API config/session, existing paths | Host/CORS/CSRF, secrets whitelist, bounded Range/file responses; never return arbitrary path authority | New W1/W2 tests; high |

## Boundary rules

All AS-IS classifications mean reuse the Python algorithm/contract, not expose its raw call signature to browsers. Raw Settings/config snapshots can contain local paths; ORM objects and internal dicts are never serialized implicitly. Thin adapters translate validated DTOs into service parameters and scrub output. Repositories keep project membership, revisions, rights and native transactional publication authoritative. Missing lifecycle/idempotency seams are explicit refactors in later milestones, not hidden W0 changes.

## Verified callable inventory

The following appendix is generated from Python AST at the audited revisions. It records exact entry points and argument names without importing application modules or initializing SQLite.

### Revision 51f1283

- app/core/config.py:12 — class `Settings`
- app/core/config.py:69 — `Settings.review_thresholds(self)`
- app/core/config.py:75 — `Settings.max_bytes(self)`
- app/core/config.py:79 — `load_settings()`

- app/core/logger.py:5 — class `EventFormatter`
- app/core/logger.py:6 — `EventFormatter.format(self, record: logging.LogRecord)`
- app/core/logger.py:12 — `configure_logging(level: str)`

- app/database/final_schema.py:9 — class `FinalRenderJob`
- app/database/final_schema.py:36 — class `SubtitleFile`
- app/database/final_schema.py:51 — class `FinalExport`

- app/database/m1_models.py:10 — class `SchemaMigration`
- app/database/m1_models.py:16 — class `OCRJob`
- app/database/m1_models.py:44 — class `OCRDetection`
- app/database/m1_models.py:67 — class `TextSegment`
- app/database/m1_models.py:95 — class `TranslationCache`

- app/database/migrations.py:18 — `migrate(engine: Engine)`

- app/database/models.py:7 — `utc_now()`
- app/database/models.py:11 — class `Base`
- app/database/models.py:15 — class `Project`

- app/database/render_schema.py:9 — class `ReplacementConfig`
- app/database/render_schema.py:20 — class `RenderJob`

- app/database/review_schema.py:9 — class `ReviewState`
- app/database/review_schema.py:22 — class `ReviewEvent`

- app/database/session.py:13 — `create_database(url: str)`

- app/database/speech_schema.py:10 — class `SpeechSegment`
- app/database/speech_schema.py:32 — class `SpeakerProfile`
- app/database/speech_schema.py:42 — class `DubJob`
- app/database/speech_schema.py:66 — class `DubbedAudioSegment`

- app/main.py:20 — `bootstrap()`

- app/providers/asr/base.py:6 — class `SpeechPhrase`
- app/providers/asr/base.py:14 — class `ASRProvider`
- app/providers/asr/base.py:16 — `ASRProvider.transcribe(self, path, check)`
- app/providers/asr/base.py:19 — `make_asr(settings)`

- app/providers/asr/funasr_provider.py:5 — `parse_funasr(results)`
- app/providers/asr/funasr_provider.py:20 — class `FunASRProvider`
- app/providers/asr/funasr_provider.py:22 — `FunASRProvider.__init__(self, settings)`
- app/providers/asr/funasr_provider.py:36 — `FunASRProvider.transcribe(self, path, check)`

- app/providers/asr/whisper_provider.py:5 — class `WhisperProvider`
- app/providers/asr/whisper_provider.py:7 — `WhisperProvider.__init__(self, settings)`
- app/providers/asr/whisper_provider.py:16 — `WhisperProvider.transcribe(self, path, check)`

- app/providers/ocr/paddle_provider.py:15 — `normalize_result(result: dict, frame: SampledFrame)`
- app/providers/ocr/paddle_provider.py:45 — class `PaddleProvider`
- app/providers/ocr/paddle_provider.py:46 — `PaddleProvider.__init__(self, settings: Settings)`
- app/providers/ocr/paddle_provider.py:76 — `PaddleProvider.detect(self, frame: SampledFrame)`

- app/providers/translation/argos_provider.py:20 — class `ArgosProvider`
- app/providers/translation/argos_provider.py:21 — `ArgosProvider.__init__(self, folder: Path, threads: int=2, use_glossary: bool=True)`
- app/providers/translation/argos_provider.py:38 — `ArgosProvider.identity(self)`
- app/providers/translation/argos_provider.py:59 — `ArgosProvider.translate(self, text: str, context: str)`

- app/providers/translation/base.py:4 — class `Translator`
- app/providers/translation/base.py:6 — `Translator.identity(self)`
- app/providers/translation/base.py:8 — `Translator.translate(self, text: str, context: str)`

- app/providers/tts/azure_tts_provider.py:9 — class `AzureTTS`
- app/providers/tts/azure_tts_provider.py:10 — `AzureTTS.__init__(self, settings)`
- app/providers/tts/azure_tts_provider.py:19 — `AzureTTS.voices(self)`
- app/providers/tts/azure_tts_provider.py:28 — `AzureTTS.synthesize(self, text, voice, output, check)`

- app/providers/tts/base.py:6 — class `VoiceSettings`
- app/providers/tts/base.py:15 — class `TTSProvider`
- app/providers/tts/base.py:17 — `TTSProvider.voices(self)`
- app/providers/tts/base.py:18 — `TTSProvider.synthesize(self, text, voice, output, check)`
- app/providers/tts/base.py:21 — `make_tts(settings, voice)`

- app/providers/tts/local_tts_provider.py:6 — class `LocalTTS`
- app/providers/tts/local_tts_provider.py:7 — `LocalTTS.__init__(self, settings)`
- app/providers/tts/local_tts_provider.py:22 — `LocalTTS.voices(self)`
- app/providers/tts/local_tts_provider.py:25 — `LocalTTS.synthesize(self, text, voice, output, check)`

- app/services/audio_extractor.py:12 — `audio_info(path, settings)`
- app/services/audio_extractor.py:24 — `ffmpeg(settings, args, check=lambda: None, timeout=120)`
- app/services/audio_extractor.py:43 — `extract_audio(sessions, settings, project_id, check=lambda: None)`

- app/services/audio_sync_service.py:11 — `atempo_chain(factor)`
- app/services/audio_sync_service.py:20 — `synchronize(source, output, available, voice, settings, check=lambda: None)`
- app/services/audio_sync_service.py:39 — `assemble_timeline(segments, output, duration, check=lambda: None)`

- app/services/dub_jobs.py:27 — `history(sessions, project_id)`
- app/services/dub_jobs.py:32 — `queue_dub(sessions, settings, project_id, token, kind, selected_ids=None, voice=None, replace_existing=False, rights_confirmed=False, preview_text='Xin chào, đây là giọng đọc tiếng Việt.')`
- app/services/dub_jobs.py:75 — `validate_items(db, items)`
- app/services/dub_jobs.py:81 — `run_dub(sessions, job_id, asr_factory=None, tts_factory=make_tts, translator_factory=None)`
- app/services/dub_jobs.py:164 — `cancel(sessions, job_id)`
- app/services/dub_jobs.py:169 — class `DubManager`
- app/services/dub_jobs.py:170 — `DubManager.__init__(self, settings, sessions)`
- app/services/dub_jobs.py:175 — `DubManager.launch(self, job)`
- app/services/dub_jobs.py:189 — `DubManager.monitor(self)`
- app/services/dub_jobs.py:220 — `DubManager.close(self)`

- app/services/dubbing_contract.py:14 — `approved_dub(sessions, settings, project_id)`

- app/services/dubbing_service.py:22 — `transcribe(sessions, settings, project, folder, check, progress, provider_factory=make_asr)`
- app/services/dubbing_service.py:50 — `translate_speech(sessions, settings, items, check, progress, translator_factory=TranslationService)`
- app/services/dubbing_service.py:63 — `synthesize_cached(sessions, settings, project_id, text, voice, provider, check)`
- app/services/dubbing_service.py:82 — `generate_audio(sessions, settings, job, project, folder, items, check, progress, tts_factory=make_tts)`

- app/services/final_job_manager.py:19 — class `FinalManager`
- app/services/final_job_manager.py:20 — `FinalManager.__init__(self, settings, sessions)`
- app/services/final_job_manager.py:25 — `FinalManager.launch(self, job)`
- app/services/final_job_manager.py:40 — `FinalManager.monitor(self)`
- app/services/final_job_manager.py:79 — `FinalManager.close(self)`

- app/services/final_output_validation.py:16 — `faststart(path)`
- app/services/final_output_validation.py:31 — `validate_metadata(path, options, mode, settings)`
- app/services/final_output_validation.py:54 — `audio_evidence(output, reference, options, config, settings, background, check)`
- app/services/final_output_validation.py:83 — `frame(path, timestamp, target, settings, check, vf=None)`
- app/services/final_output_validation.py:90 — `visual_evidence(output, video, options, config, subtitle_report, settings, check)`
- app/services/final_output_validation.py:112 — `validate_output(output, video, audio, options, config, subtitle_report, settings, background=None, check=lambda: None)`

- app/services/final_render_config.py:5 — class `SubtitleStyle`
- app/services/final_render_config.py:22 — class `FinalRenderConfig`
- app/services/final_render_config.py:41 — `dimensions(width, height, config, is_preview=False)`

- app/services/final_render_service.py:33 — `available_background(sessions, settings, project_id)`
- app/services/final_render_service.py:48 — `retrieve_inputs(sessions, settings, project_id, config)`
- app/services/final_render_service.py:66 — `signature(inputs, config)`
- app/services/final_render_service.py:73 — `final_history(sessions, project_id)`
- app/services/final_render_service.py:78 — `queue_final(sessions, settings, project_id, token, config=None, is_preview=False, rights_confirmed=False, preview_reviewed=False)`
- app/services/final_render_service.py:105 — `cleanup_staging(folder, failed=False)`
- app/services/final_render_service.py:118 — `run_final(sessions, job_id, muxer=run_mux, validator=validate_output)`
- app/services/final_render_service.py:205 — `prune_previews(sessions, settings, project_id, current_id)`
- app/services/final_render_service.py:213 — `cancel_final(sessions, job_id)`
- app/services/final_render_service.py:218 — `exports(sessions, project_id, include_deleted=False)`
- app/services/final_render_service.py:226 — `move_export(sessions, settings, project_id, export_id, confirmed=False, restore=False)`
- app/services/final_render_service.py:242 — `export_contract(sessions, settings, project_id, export_id)`

- app/services/frame_extractor.py:15 — class `Cancelled`
- app/services/frame_extractor.py:19 — `sample_times(duration: float, interval: float, maximum: int)`
- app/services/frame_extractor.py:26 — `source_hash(path: Path)`
- app/services/frame_extractor.py:35 — class `SampledFrame`
- app/services/frame_extractor.py:45 — `display_dimensions(path: Path, settings: Settings)`
- app/services/frame_extractor.py:64 — `extract_frames(path: Path, project_id: str, duration: float, settings: Settings, check_cancel: Callable[[], None]=lambda: None, timestamps: list[float] | None=None)`

- app/services/inpainting_provider.py:8 — class `InpaintingProvider`
- app/services/inpainting_provider.py:9 — `InpaintingProvider.apply(self, image: np.ndarray, mask: np.ndarray, radius: int)`
- app/services/inpainting_provider.py:12 — class `OpenCVInpainting`
- app/services/inpainting_provider.py:13 — `OpenCVInpainting.apply(self, image, mask, radius)`

- app/services/job_manager.py:18 — `worker_process(job)`
- app/services/job_manager.py:33 — `reconcile_jobs(sessions, now=None)`
- app/services/job_manager.py:58 — class `JobManager`
- app/services/job_manager.py:59 — `JobManager.__init__(self, settings, sessions)`
- app/services/job_manager.py:67 — `JobManager.launch(self, job)`
- app/services/job_manager.py:110 — `JobManager.close(self)`

- app/services/ocr_repository.py:13 — `validate_id(value: str)`
- app/services/ocr_repository.py:22 — `get_project(sessions, project_id: str)`
- app/services/ocr_repository.py:31 — `project_source(sessions, project_id: str, settings)`
- app/services/ocr_repository.py:40 — `list_segments(sessions, project_id: str)`
- app/services/ocr_repository.py:47 — `list_detections(sessions, project_id: str)`
- app/services/ocr_repository.py:54 — `save_reviews(sessions, project_id: str, edits: list[dict])`

- app/services/ocr_service.py:24 — `latest_job(sessions, project_id)`
- app/services/ocr_service.py:30 — `queue_job(sessions, settings: Settings, project_id: str, kind='ocr', selected_ids=None, replace_existing=False)`
- app/services/ocr_service.py:66 — `request_cancel(sessions, job_id)`
- app/services/ocr_service.py:74 — `run_job(sessions, job_id: str, provider_factory=PaddleProvider, extractor=extract_frames, translator_factory=TranslationService)`

- app/services/render_jobs.py:27 — `render_history(sessions, project_id)`
- app/services/render_jobs.py:33 — `queue_render(sessions, settings, project_id, token, rights_confirmed=False, regions_confirmed=False, quality='balanced')`
- app/services/render_jobs.py:66 — `run_render(sessions, job_id, renderer=render_video)`
- app/services/render_jobs.py:133 — `cancel_render(sessions, job_id)`
- app/services/render_jobs.py:139 — class `RenderManager`
- app/services/render_jobs.py:140 — `RenderManager.__init__(self, settings, sessions)`
- app/services/render_jobs.py:148 — `RenderManager.launch(self, job)`
- app/services/render_jobs.py:165 — `RenderManager.monitor(self)`
- app/services/render_jobs.py:204 — `RenderManager.close(self)`

- app/services/render_preview.py:14 — `preview_frame(sessions, settings, project_id, timestamp)`

- app/services/replacement_contract.py:13 — `localized_video(sessions, settings, project_id)`

- app/services/replacement_repository.py:14 — `segment_fingerprint(segment)`
- app/services/replacement_repository.py:19 — `assert_review_current(session, segment)`
- app/services/replacement_repository.py:28 — `save_config(sessions, project_id, segment_id, config: ReplacementSettings, enabled=True)`
- app/services/replacement_repository.py:50 — `list_configs(sessions, project_id)`
- app/services/replacement_repository.py:56 — `snapshot_items(sessions, project_id)`
- app/services/replacement_repository.py:82 — `validate_snapshot(sessions, items)`

- app/services/speech_repository.py:12 — `fingerprint(row)`
- app/services/speech_repository.py:16 — `list_speech(sessions, project_id)`
- app/services/speech_repository.py:21 — `save_speech(sessions, project_id, edits)`
- app/services/speech_repository.py:44 — `speaker_settings(sessions, project_id)`
- app/services/speech_repository.py:48 — `save_speaker(sessions, project_id, label, voice)`

- app/services/speech_segmentation.py:7 — `normalize_phrases(phrases, offset, duration, existing=())`

- app/services/storage_service.py:19 — `list_projects(sessions: sessionmaker)`
- app/services/storage_service.py:24 — `resolve_media(root: Path, relative: str)`
- app/services/storage_service.py:32 — `import_video(stream: BinaryIO, filename: str, source: SourceInfo, settings: Settings, sessions: sessionmaker, upload_token: str)`

- app/services/subtitle_service.py:12 — `ass_time(seconds)`
- app/services/subtitle_service.py:19 — `escape_ass(text)`
- app/services/subtitle_service.py:27 — `ass_color(color, alpha=0)`
- app/services/subtitle_service.py:33 — `layout_caption(text, style, width, height)`
- app/services/subtitle_service.py:54 — `generate_ass(segments, path, width, height, duration, style=None, speaker_styles=None, window=None, readability_confirmed=False, soft=False)`
- app/services/subtitle_service.py:111 — `soft_text_bridge(report, path)`

- app/services/text_compositor.py:14 — class `ReplacementSettings`
- app/services/text_compositor.py:32 — `valid_box(box, width, height)`
- app/services/text_compositor.py:41 — `region_at(item, t, width, height)`
- app/services/text_compositor.py:64 — `overlaps(a, b)`
- app/services/text_compositor.py:68 — `compose(frame, t, items, strict=True, inpainting_provider: InpaintingProvider | None=None)`

- app/services/text_layout.py:13 — class `TextStyle`
- app/services/text_layout.py:28 — `available_fonts()`
- app/services/text_layout.py:42 — `glyphs(path)`
- app/services/text_layout.py:48 — `load_font(name, text, size)`
- app/services/text_layout.py:58 — `wrap_text(text, font, width, stroke)`
- app/services/text_layout.py:79 — `text_layer(text, box, style: TextStyle)`

- app/services/text_tracker.py:9 — `normalized(text: str)`
- app/services/text_tracker.py:13 — `contains_chinese(text: str)`
- app/services/text_tracker.py:17 — `box_iou(a: list, b: list)`
- app/services/text_tracker.py:26 — class `Detection`
- app/services/text_tracker.py:40 — class `Segment`
- app/services/text_tracker.py:50 — `group_detections(detections: list[Detection], interval: float, duration: float, min_confidence: float=0.4, similarity: float=0.94, iou: float=0.3)`

- app/services/translation_review_service.py:20 — `content_hash(segment)`
- app/services/translation_review_service.py:25 — class `Evaluation`
- app/services/translation_review_service.py:31 — `evaluate(source, translated, confidence, provider_error=None, settings=None)`
- app/services/translation_review_service.py:65 — `effective_state(segment, state=None)`
- app/services/translation_review_service.py:75 — `record(session, segment, state, mode, method, score, reasons)`
- app/services/translation_review_service.py:92 — `record_editor_action(session, segment)`
- app/services/translation_review_service.py:97 — `review_batch(sessions, project_id, selections, action, settings, confirmed=False, progress=lambda done, total: None)`

- app/services/translation_service.py:18 — `make_provider(settings: Settings)`
- app/services/translation_service.py:27 — `timed_call(callback, timeout: float)`
- app/services/translation_service.py:52 — class `TranslationService`
- app/services/translation_service.py:53 — `TranslationService.__init__(self, settings, sessions, provider=None, sleep=time.sleep, call=timed_call, context=CONTEXT)`
- app/services/translation_service.py:59 — `TranslationService.translate(self, text: str, check_cancel=lambda: None)`

- app/services/video_mux_service.py:15 — `probe_streams(path, settings)`
- app/services/video_mux_service.py:22 — `capabilities(settings)`
- app/services/video_mux_service.py:33 — `geometry_filter(width, height, aspect_mode='fit')`
- app/services/video_mux_service.py:38 — `audio_graph(span, config, voice_index=1, background_index=None)`
- app/services/video_mux_service.py:45 — `timeline_options(video, audio, project_duration, config, settings, is_preview=False)`
- app/services/video_mux_service.py:67 — `run_mux(video, audio, ass_path, output, options, config, settings, subtitle_report, background=None, check=lambda: None, progress=lambda value: None)`

- app/services/video_renderer.py:16 — `stream_info(path, settings)`
- app/services/video_renderer.py:34 — `read_frame(pipe, size)`
- app/services/video_renderer.py:48 — `stop_process(process)`
- app/services/video_renderer.py:57 — `render_video(source, output, items, settings, quality='balanced', check=lambda: None, progress=lambda value: None)`

- app/services/video_service.py:16 — class `VideoMetadata`
- app/services/video_service.py:26 — `parse_metadata(data: dict, suffix: str)`
- app/services/video_service.py:66 — `probe_video(path: Path, executable: str, suffix: str)`

- app/services/workload_guard.py:6 — `ensure_idle(session, exclude='')`

- app/worker.py:11 — `main()`


### Revision 8ac209c

- app/desktop/launcher.py:16 — `bundle_root()`
- app/desktop/launcher.py:20 — `default_data()`
- app/desktop/launcher.py:25 — class `InstanceLock`
- app/desktop/launcher.py:26 — `InstanceLock.__init__(self, root)`
- app/desktop/launcher.py:30 — `InstanceLock.acquire(self)`
- app/desktop/launcher.py:49 — `InstanceLock.close(self)`
- app/desktop/launcher.py:54 — `write_status(root, payload)`
- app/desktop/launcher.py:61 — `read_status(root)`
- app/desktop/launcher.py:68 — `owned_process(status)`
- app/desktop/launcher.py:84 — `healthy(status)`
- app/desktop/launcher.py:96 — `stop_owned(status)`
- app/desktop/launcher.py:115 — `paths(root)`
- app/desktop/launcher.py:124 — `child_environment(root, data, models=None)`
- app/desktop/launcher.py:143 — `initialize_data(data)`
- app/desktop/launcher.py:154 — `main(argv=None)`

- app/desktop/runtime.py:13 — `digest(path)`
- app/desktop/runtime.py:20 — `backup_data(data, destination)`
- app/desktop/runtime.py:43 — `restore_data(backup, data)`
- app/desktop/runtime.py:58 — `cleanup_temp(data, confirmed=False, now=None)`
- app/desktop/runtime.py:68 — `main(argv=None)`

- app/desktop/model_manager.py:20 — `catalog()`
- app/desktop/model_manager.py:23 — `verified(folder, files)`
- app/desktop/model_manager.py:31 — `inventory(root, verify=False)`
- app/desktop/model_manager.py:42 — `download_file(url, target, expected, max_bytes, check, progress)`
- app/desktop/model_manager.py:60 — `staging_root(root, job_id)`
- app/desktop/model_manager.py:70 — `cleanup_download(root, job_id)`
- app/desktop/model_manager.py:76 — `install_model(item, root, check=lambda: None, progress=lambda n: None, job_id=None)`
- app/desktop/model_manager.py:108 — `history(sessions)`
- app/desktop/model_manager.py:112 — `recover_downloads(sessions)`
- app/desktop/model_manager.py:128 — `queue_download(sessions, root, group)`
- app/desktop/model_manager.py:140 — `run_download(sessions, job_id)`

- scripts/build_windows.py:15 — `sha(path)`
- scripts/build_windows.py:22 — `copy_ignore(folder, names)`
- scripts/build_windows.py:27 — `build(runtime, site_packages, ffmpeg, ffprobe, notice, ffmpeg_license, output, archive=True)`

