# W0 — Proposed Local API contract v1

**PROPOSED / NOT IMPLEMENTED.** Derived from inspected SQLAlchemy entities and service signatures, not generated from existing REST routes (none found). W1 implements only health, local-session exchange and redacted system status. Other endpoints belong to W2–W6. No endpoint below is declared operational.

## Transport, access and common schemas

Backend is `http://127.0.0.1:8000`; exact browser origin `http://127.0.0.1:3000`. All requests enforce explicit Host allowlist and reject forwarded host authority. Codes **H** health-only, **B** one-time bootstrap, **R** authenticated read, **W** authenticated mutation + exact Origin + CSRF header. Cookies are HttpOnly, host-only, SameSite=Strict, Path=/api, no Domain; HTTP loopback has no Secure cookie guarantee. Session expires/revokes on restart. Origin is mandatory on mutations/bootstrap and browser WebSocket; reads require session and enforce exact Origin when present. CORS allows credentials only for exact frontend origin; no wildcard/null/file origin. Preflight does not authorize mutation. Same-user native malware is outside isolation claims.

W routes require JSON Content-Type except bounded multipart upload. Unknown fields rejected (`extra=forbid` in future request DTOs), finite numbers only, UUIDs canonical lower-case, maximum item/string lengths enforced. Never accept browser file paths, executable names, SQL fragments, shell args or raw Settings. Every project/segment/job/export lookup verifies membership; arbitrary UUID is not authority. Request IDs generated server-side. Mutations doing async work require Idempotency-Key UUID, returning same operation/project/payload outcome on repeat and 409 on payload mismatch. Upload maps key to existing unique upload_token. OCR needs the durable transaction seam from the architecture before release.

HTTP 202 means persisted job acceptance, not completed processing. Known terminal duplicate may return 200 with original job. Pages use `{items:[T], next_cursor:string|null}` with limit default20/max100; opaque validated cursor based on `(created_at,id)` and fixed ordering. UTC ISO8601 timestamps; duration/time in seconds; progress fraction0–1; bbox `[x,y,width,height]` in original display pixels; no normalized/thumbnail coordinate confusion.

Public error shape (all endpoints): `{error:{code,message,request_id,details?}}`. Details are whitelisted field errors, never stack traces, environment, absolute paths, raw worker config or credentials. Codes: 400 INVALID_REQUEST, 401 SESSION_REQUIRED/EXPIRED, 403 ORIGIN_REJECTED/CSRF_REJECTED/CONSENT_REQUIRED, 404 NOT_FOUND (also wrong project membership), 409 JOB_BUSY/REVISION_CONFLICT/IDEMPOTENCY_CONFLICT/STALE_ARTIFACT/REVIEW_REQUIRED/PREVIEW_REQUIRED/SCHEMA_UNSUPPORTED, 413 UPLOAD_TOO_LARGE, 415 UNSUPPORTED_MEDIA, 422 VALIDATION_ERROR/MODEL_MISSING, 503 DEPENDENCY_UNAVAILABLE, 507 INSUFFICIENT_STORAGE, 500 INTERNAL_ERROR. Map service UserError by known operation-specific conditions, not fragile Vietnamese string matching; introduce typed adapter error taxonomy as needed without changing engine meaning.

### Named DTO schemas

| DTO | Fields / important exclusions |
|---|---|
| Health | `{status:'ok', api_version:'v1', instance_id:uuid}`; no paths, user data or model loads |
| BootstrapIn / SessionOut | `{bootstrap_secret:string}` / `{csrf_token:string, expires_at:timestamp}` plus Set-Cookie; one-use, short expiry, no secret echo |
| SystemStatus | `{version, readiness:'ready'|'degraded', tools:{ffmpeg:boolean,ffprobe:boolean,ass:boolean}, database:{configured:boolean,schema_status:string}, models_available:boolean, active_job:JobRef|null}`; DB state `not_inspected` allowed in W1 |
| Project | `{id,original_filename,source_url?,creator_name?,rights_status,rights_notes?,file_size,duration,width,height,fps,video_codec,audio_codec?,aspect_ratio,status,created_at,updated_at}`; exclude file_path/stored_filename/upload_token |
| SourceMetadata | SourceInfo fields; rights_status unknown/owned/licensed/permission_granted; URL http/https metadata only, never automatically fetched |
| ProjectPatch | Optional source_url/creator_name/rights_status/rights_notes only; optimistic adapter precondition required; no direct status/path/ID change |
| TextSegment | `{id,project_id,source_text,translated_text,start_time,end_time,bounding_box,confidence,translation_provider,review_status,revision,effective_review_state,reasons:[]}`; review_status remains pending/approved/rejected |
| TextEdit | `{project_id,revision,source_text?,translated_text?,start_time?,end_time?,bounding_box?,review_status?}`; source≤1000, translation≤2000; approved needs nonempty translation |
| Detection | `{id,segment_id?,timestamp,frame_index,frame_width,frame_height,source_text,confidence,bounding_box,polygon}` |
| ReviewIn / ReviewOut | `{selections:[{id,revision}],action:'smart'|'approve_all'|'approve_selected'|'revert',confirmed:boolean}` / `{changed,unchanged,failed}`; max100 unique selections; `failed` count is not whole-request success |
| JobRef | `{kind:'ocr'|'replace'|'dub'|'final',id:uuid}`; model kind gated on later M5 integration |
| Job | `{...JobRef,project_id,operation,state:'QUEUED'|'RUNNING'|'CANCEL_REQUESTED'|'COMPLETED'|'FAILED'|'CANCELLED',native_state,stage,progress,cancel_requested,created_at,updated_at?,completed_at?,warning?,error_code?,error_message?,retry_of:JobRef|null,artifacts:Asset[]}`; no pid/config_snapshot/lease/settings |
| Asset | `{id:string,kind:'source'|'frame'|'preview'|'audio'|'mp4'|'ass',project_id,content_type,bytes?,url:string}`; opaque lookup to managed root, never browser-selected path |
| ReplacementIn | Existing ReplacementSettings fields (solid/blur/inpaint/overlay, boxes, fixed_box, padding0–100, opacity0–1, radius1–15, TextStyle, override/approval/tracking flags, optional timing); no font filesystem path |
| SpeechSegment | `{id,project_id,start_time,end_time,original_text,translated_text,speaker_id,asr_provider,confidence?,review_status,revision,warnings:[]}`; separate resource from TextSegment |
| SpeechEdit | `{project_id,revision,original_text?,translated_text?,start_time?,end_time?,speaker_id?,review_status?}`; same length/timing/revision rules as speech_repository |
| Voice | Existing VoiceSettings `{provider:'local'|'azure',voice,rate:.8–1.2,pitch:-10–10,volume:.1–1.5,cloud_confirmed:boolean}`; local pitch must0; cloud permission not silently inherited from saved speaker |
| FinalIn | `{config:FinalConfig,rights_confirmed:boolean,preview_reviewed:boolean}`; config mirrors FinalRenderConfig except background_path replaced by background_asset_id; current preview evidence validated server-side |
| FinalConfig | preset original/tiktok/compact; tiktok_resolution1080x1920/720x1280; fit/crop + ack; fast/balanced/high; source/24/25/30/60 FPS; burn/soft/none + compatibility ack; SubtitleStyle and speaker styles; readability ack; voice volume0–1.5; validated separated background asset/volume0–1; preview_start≥0, preview_seconds>0≤30 and settings cap |
| Export | `{id,project_id,render_job_id,filename,file_size,duration,width,height,sha256,subtitle_mode,created_at,deleted_at?,mp4:Asset,ass:Asset|null,validation:RedactedReport}`; no raw render snapshots or local font paths |
| SettingsPublic / SettingsPatch | allowlisted non-secret provider selections/limits/voice preferences; `{azure_configured:boolean}` only, no key/region environment dump; paths selected as private profiles not posted raw from browser |
| ModelAvailability | `{id,group,status:'missing'|'present_unverified'|'verified'|'corrupt'|'unsupported',license,source_url?,download_bytes?,verification_at?}`; no local path; availability is not inference quality |

## Endpoint inventory

Every row inherits common validation/errors and its access code. Listed errors are additional material expected cases. Service paths below are under `app/services/` unless qualified. No route bypasses business checks because a browser says it has reviewed/owns content.

| Method / URL | Request → response / success | Validation / errors | Relevant service / adapter | Access / milestone |
|---|---|---|---|---|
| GET `/health` | none → Health200 | correct Host; bounded, no dependency side effects; 503 only API unready | New app factory, no engine bootstrap | H / W1 |
| POST `/api/v1/session/bootstrap` | BootstrapIn → SessionOut200 + cookie | constant-time compare, one-use, short expiry; 401 invalid/expired,403 Origin; rate bound | New runtime session store | B / W1 |
| GET `/api/v1/session` | cookie → `{csrf_token,expires_at}`200 | existing session, no secret echo; 401 | New session service, recovery after page reload | R / W1 |
| DELETE `/api/v1/session` | no body →204 | revoke current session; 403 CSRF | New session service | W / W1 |
| GET `/api/v1/system/status` | none → SystemStatus200 | redact; health-safe checks only; missing tool reported degraded, no model startup/download/DB upgrade | New diagnostics adapter, validated config; M4 capabilities later | R / W1 |
| GET `/api/v1/system/diagnostics` | none → `{checks:[{name,status,message}],disk_free_bytes}`200 | curated keys, cached bounded probes; no raw logs/env/process command | video_service, text_layout, tool probes | R / W2 |
| GET `/api/v1/projects` | cursor/limit → Page<Project>200 | cursor and fixed sort;503 DB unavailable | storage_service.list_projects needs paginated query | R / W2 |
| POST `/api/v1/projects` | multipart `video` + `metadata` JSON SourceMetadata; Idempotency-Key → Project201 | seekable spool,≤500MiB,≤180s, filename/container/probe/rights;413/415/422/507,409 key mismatch | storage_service.import_video; creates project WITH video | W / W2 |
| GET `/api/v1/projects/{id}` | UUID → Project200 | membership,404 | ocr_repository.get_project | R / W2 |
| PATCH `/api/v1/projects/{id}` | ProjectPatch + If-Match adapter revision → Project200 | no active mutation, rights enum, metadata limits;409 revision/job conflict | New short transaction update; existing model has no revision field, design concurrency token before shipping | W / W2 |
| DELETE `/api/v1/projects/{id}` | `{confirmed:true,mode:'archive'}` →204 | archive only; no physical source delete;409 active job;422 until archive schema approved | NEW archive service/schema decision; do not implement raw SQL delete | W / later W2 |
| POST `/api/v1/projects/{id}/upload` | not supported in first contract | no empty draft/replacement semantics;405 METHOD_NOT_ALLOWED | Deliberate difference from initial plan; use atomic POST projects; replacement-source versioning deferred | W / deferred |
| GET `/api/v1/projects/{id}/source` | optional Range → media200/206 | managed source only;404/416 range; correct mime, no active scripts | ocr_repository.project_source + new streaming Asset adapter | R / W2 |
| POST `/api/v1/projects/{id}/ocr` | `{replace_existing:false}` + key → Job202 | confirm replacement if segments exist; model preflight;409 busy/review state,422 model | ocr_service.queue_job(kind=ocr) + atomic idempotency seam | W / W3 |
| POST `/api/v1/projects/{id}/translate` | `{selected_ids:[uuid]}` + key → Job202 | nonempty unique IDs, project membership, unapproved only, bounded chars;409/422 | ocr_service.queue_job(kind=translate) | W / W3 |
| GET `/api/v1/projects/{id}/segments` | cursor/limit → Page<TextSegment>200 | scoped records, computed effective review,404 | ocr_repository.list_segments + review effective_state | R / W3 |
| GET `/api/v1/projects/{id}/detections` | time range/cursor → Page<Detection>200 | finite0≤start<end≤duration, bounded page | ocr_repository.list_detections | R / W3 |
| PATCH `/api/v1/segments/{id}` | TextEdit → TextSegment200 | bbox fits displayed dimensions; revision and ownership;409 stale/OCR active;422 timing | ocr_repository.save_reviews | W / W3 |
| POST `/api/v1/projects/{id}/review` | ReviewIn → ReviewOut200 | max100, explicit bulk ack, current revisions, possible partial failures;409 active work | translation_review_service.review_batch | W / W3 |
| GET `/api/v1/projects/{id}/replacement-configs` | none → `{items:[{segment_id,enabled,config}]}`200 | project UUID/membership | replacement_repository.list_configs | R / W4 |
| PUT `/api/v1/projects/{id}/replacement-configs/{segment_id}` | `{enabled,config:ReplacementIn}` → same200 | valid bbox/timing/segment and ack;422/409 stale | replacement_repository.save_config; future config concurrency guard | W / W4 |
| POST `/api/v1/projects/{id}/replacement-preview` | `{timestamp}` → `{before:Asset,after:Asset,warnings:[]}`200 | finite timestamp in source, bounded worker/thread admission,409 busy | render_preview.preview_frame + encode asset adapter | W / W4 |
| POST `/api/v1/projects/{id}/replace-text` | `{quality:'draft'|'balanced'|'high',rights_confirmed,regions_confirmed}` + key → Job202 | selected valid snapshots, rights + tracking/override ack;409 REVIEW_REQUIRED/JOB_BUSY | render_jobs.queue_render | W / W4 |
| GET `/api/v1/projects/{id}/speech-segments` | cursor → Page<SpeechSegment>200 | separate speech source of truth | speech_repository.list_speech | R / W5 |
| PATCH `/api/v1/speech-segments/{id}` | SpeechEdit → SpeechSegment200 | revisions/timing/text/speaker/current ASR;409/422 | speech_repository.save_speech | W / W5 |
| GET `/api/v1/projects/{id}/speakers` | none → `{items:[{speaker_label,voice:Voice}]}`200 | saved consent always false on profiles | speech_repository.speaker_settings | R / W5 |
| PUT `/api/v1/projects/{id}/speakers/{label}` | Voice → saved speaker200 | label≤80, valid voice/provider; no persistent consent | speech_repository.save_speaker | W / W5 |
| GET `/api/v1/voices` | provider local/azure → `{items:[{id,name,pitch}]}`200 | Azure list may contact provider; explicit provider config, no silent startup call;503/422 | make_tts(...).voices via bounded diagnostics adapter | R / W5 |
| POST `/api/v1/projects/{id}/dub` | `{kind:'asr'|'translate'|'tts'|'assemble'|'preview',selected_ids?,voice?,replace_existing?,rights_confirmed?,preview_text?}` + key → Job202 | match queue_dub kinds, revisions/approved speech/rights/current source, per-op cloud ack;403/409/422 | dub_jobs.queue_dub; voice defaults backend controlled | W / W5 |
| POST `/api/v1/projects/{id}/final-preview` | FinalIn + key → Job202 | current validated M2+M3; window≤settings cap; config compact allowed;409 stale inputs | final_render_service.queue_final(is_preview=True) | W / W6 |
| POST `/api/v1/projects/{id}/render` | FinalIn + key → Job202 | matching completed preview signature + rights, no compact final;409 PREVIEW_REQUIRED/STALE_ARTIFACT;422 crop/soft/readability | final_render_service.queue_final(is_preview=False) | W / W6 |
| GET `/api/v1/jobs/{kind}/{id}` | typed ref → Job200 | kind registry + project check;404; no arbitrary table name | New JobFacade projecting native rows | R / W3+ |
| POST `/api/v1/jobs/{kind}/{id}/cancel` | `{}` → Job202 or terminal Job200 | idempotent cancellation request; never declare cancelled until process stops | request_cancel / cancel_render / dub_jobs.cancel / cancel_final | W / W3+ |
| POST `/api/v1/jobs/{kind}/{id}/retry` | `{accept_current_inputs:true}` + new key → new Job202 | only failed/cancelled, current validation/rights/reviews;409 busy/stale; require fresh cloud ack separately | New retry facade invoking native queue, durable lineage | W / W3+ |
| GET `/api/v1/exports` | optional project_id/cursor → Page<Export>200 | scoped cross-project pagination, exclude trashed | final_render_service.exports + paginated repository | R / W6 |
| GET `/api/v1/exports/{id}` | UUID → Export200 | validated owner/project;404/409 artifact mismatch | export_contract + safe DTO | R / W6 |
| GET `/api/v1/exports/{id}/download` | format=mp4/ass; optional Range → media200/206 | derived known artifact path, attachment filename sanitized;404/409 invalid artifact,416 range | export_contract; SubtitleFile path bound to same final job | R / W6 |
| POST `/api/v1/exports/{id}/trash` | `{confirmed:true}` → Export200 | no input deletion, active-job/source preserved;409 target conflict | move_export(restore=False) | W / W6 |
| POST `/api/v1/exports/{id}/restore` | `{confirmed:true}` → Export200 | existing trash, no overwrite;409 | move_export(restore=True) | W / W6 |
| GET `/api/v1/assets/{asset_id}` | optional Range → media200/206 | resolver binds opaque id→project/job/type/root; no absolute/relative path parameter | New managed media registry/derived lookup | R / W2+ |
| GET `/api/v1/settings` | none → SettingsPublic200 | whitelist; report configured boolean only for secrets | New Settings projection, config.py | R / W2 |
| PATCH `/api/v1/settings` | SettingsPatch → SettingsPublic200 | allowlisted knobs; no engine roots/executables/keys via arbitrary JSON;409 active-job changes | New private config transaction/application adapter | W / W2+ |
| GET `/api/v1/models` | group? → `{items:[ModelAvailability]}`200 | offline file presence; don't claim SHA verified unless checked; no download/inference | Approved-base model probe adapter; later M5 inventory after reviewed reuse | R / W2 |
| POST `/api/v1/models/{group}/download` | `{confirmed:true}` + key → Job202 | allowlisted pinned catalog group; no URL/path input;409 heavy busy,507 space | Deferred M5 integration, not present on W0 base | W / separately approved |
| WS `/api/v1/ws/jobs/{kind}/{id}` | session cookie + exact Origin → JobEvent stream | authenticate before accept; bounded connections;4401/4403/4404 close codes, no query token | New JobFacade subscription with short DB reads | R / W3+ |

Review native queue kinds against the callable appendix before implementation. `queue_dub` accepts `preview`, `asr`, `translate`, `tts`, `assemble`; no invented `dub_all` operation. Configs must preserve each native confirmation gate, not invent an automatic chain.

## Realtime and streaming contract

JobEvent: `{event:'job.snapshot'|'job.progress'|'job.terminal',sequence:int>=0,snapshot_at:timestamp,job:Job}`. Client reconnects and replaces state from fresh snapshot; sequence is local to connection, not promised durable event replay. An absent native updated_at field is not fabricated; emit snapshot_at and observed status/progress. Browser disconnect affects subscription only. Explicit cancel is POST. GET job polling remains available when WS fails; use bounded backoff with jitter.

Source/preview/audio/export responses stream managed files with Content-Type, Content-Disposition, nosniff, private/no-store policy appropriate to private media and single-range support. Validate Range bounds, return416 with valid Content-Range; no complete video read_bytes on API path. Token/session is not encoded into artifact URLs. Resolve symlink/reparse/canonical-root containment before opening, and bind opened handle/metadata to verified artifact to reduce check/open races. Never mount storage as unauthenticated StaticFiles or a Next public directory.

## Acceptance examples

- Repeated same render key/body returns same native job; same key changed config returns409, not second render.
- Revision12 edit against saved13 returns409 without overwriting13; source edits reset approval by existing repository semantics.
- Current M2/M3 input changed after preview: final POST returns409; no original video/audio fallback.
- Browser payload `background_path`, `ffmpeg_path`, `database_url`, extra `pid` or model download URL is422; API derives resources internally.
- Untrusted Origin/Host, absent session/CSRF, `null` origin, cross-project segment or encoded traversal never reaches side-effect service.
- Authorized upload creates Project only after valid file/probe; failed upload has no half-created project and cannot delete a prior source.

All examples are future test criteria, **NOT TESTED** as API behavior in W0.
