# W0 — Database and storage migration audit

Status: schema/source inspection **VERIFIED**; future migrations **PROPOSED**, **NOT TESTED**. W0 did not call `create_database`/`migrate`, open a write connection, alter schema, relocate files or remove user data.

## Existing persistence

`app/database/session.py::create_database` creates a synchronous SQLAlchemy engine with SQLite timeout 30 s, `check_same_thread=False`, foreign_keys ON and WAL, then immediately calls `migrations.migrate`. It is not a read-only inspection API. Migration discovers `*_schema.py` modules, infers required versions from ORM table.info, takes a SQLite backup before upgrading an existing projects DB and executes metadata.create_all/version insertion under BEGIN IMMEDIATE. It does not implement arbitrary ALTER TABLE or backwards migration. [SQLAlchemy SQLite guidance](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html) explains transaction-specific caveats; do not change isolation behavior casually.

| Version | Tables introduced / source |
|---|---|
| M0, no schema ledger yet | projects, `models.py` |
| 1 | schema_migrations, ocr_jobs, ocr_detections, text_segments, translation_cache; `m1_models.py` |
| 20 | segment_reviews, review_events; `review_schema.py` |
| 30 | text_replacement_configs, render_jobs; `render_schema.py` |
| 40 | speech_segments, speaker_profiles, dub_jobs, dubbed_audio_segments; `speech_schema.py` |
| 50 | final_render_jobs, subtitle_files, final_exports; `final_schema.py` |
| 60, M5 only | model_download_jobs; `desktop_schema.py` at M5 `8ac209c` |

### Actual independent data profiles, read-only observations

| Existing relative path | Tables | Recorded versions |
|---|---:|---|
| storage/fashion_ai.db | 6 | 1 |
| storage/m1-demo/app.db | 10 | 1,20,30 |
| storage/m3-demo/app.db | 14 | 1,20,30,40 |
| storage/m4-demo/m4.db | 18 | 1,20,30,40,50,60 |
| storage/m5-migrated-demo/storage/fashion_ai.db | 18 | 1,20,30,40,50,60 |

These are distinct DBs, not sequential filenames for the same live DB. Additional pre-upgrade/QA backup DBs were found. W0 reads table/version metadata only; no row content, transcript, secret or project media is included in the audit. Do not auto-pick the newest DB or merge these profiles. `%LOCALAPPDATA%\FashionAILocalizer` is M5's possible additional profile, not audited as the chosen Web source. No active-user profile was selected for future migration.

Additional read-only PRAGMA evidence (includes SQLite automatic indexes): default profile 13 indexes / 6 FKs; M1 demo 22 / 12; M3 demo 33 / 17; M4 demo 46 / 22. Each existing approved table's column-name set matches the corresponding audited ORM definition; M5's extra table is separate. No row-value, foreign-key integrity or full database integrity test was executed. Compiled ORM DDL below supplies typed definitions; observed PRAGMA metadata confirms present entities, not a guarantee every historical constraint has been rebuilt identically.

## Entity relationships and constraints

All project, OCR/text/speech segment, native job, config and export identifiers are UUID strings; translation_cache uses a hash key; review_events has an autoincrement integer PK; schema_migrations uses integer version PK; segment_reviews uses segment_id PK/FK. UUID-looking speaker labels are not required: speaker_id is a free label with separate unique `(project_id,speaker_label)` profile association, not a declared FK.

Project owns OCR/render/dub/final jobs, OCR/text/speech segments, configs, review events, speaker profiles, subtitle rows and export rows through project_id FKs. OCR detections refer to OCR job and optionally text segment; TextSegment refers to its producing OCR job. Replacement config segment FK cascades, as does segment_reviews; review_events segment FK SET NULL retains segment_key audit identity. DubbedAudioSegment references DubJob and optionally speech segment with SET NULL. SubtitleFile.job_id and FinalExport.render_job_id each uniquely reference final_render_jobs. There is no general project ON DELETE CASCADE. Never implement project deletion as an unreviewed SQL delete.

Existing unique upload_token / request_token prevent duplicates in import/render/dub/final; OCR lacks request token. Native job active-slot partial unique indexes serialize each class; cross-class exclusion is `ensure_idle` under SQLite write lock. Review/time/confidence/bounding-box/progress CHECK constraints differ by table and must remain intact. Full typed columns, PK/FK/unique/index/check definitions are appended below from actual ORM metadata at both revisions, without connecting to any DB.

## Can the schema be reused?

**VERIFIED/INFERRED:** reuse existing projects, segments, rights, native jobs, artifacts and reviews directly through adapters. No ORM replacement or PostgreSQL is necessary. Existing M0–M4 models remain the baseline. Future generic API idempotency/retry lineage requires a small additive table; optional project archiving needs either an additive archive table or an explicit column migration. No new generic duplicate jobs table is proposed. Settings can initially be validated private configuration, not a speculative app_settings table. Durable WebSocket history is deferred; snapshot resync does not require job_events.

**PROPOSED future version 70**, reserved only after checking latest develop/M5 versions: `web_request_bindings` with UUID idempotency_key PK, operation, project_id FK, canonical request digest, native_kind, native_job_id, optional retry_of_kind/retry_of_id, created_at; unique operation/key semantics and atomic native admission. Define native table linkage in application validation (polymorphic ID cannot have one conventional FK). Never store tokens, credentials or binary media in this table. Exact DDL/indexes and transaction seam are W3 work. W1 adds no DB table. Archive/delete UX/schema needs separate W2 decision and tests, not speculative writes in W0.

Schema detection before opening a production session: inspect in read-only mode first, support recognized 1/20/30/40/50/60 variants, refuse unknown future versions with an actionable message. Keep extra known M5 tables intact even when M5 code is absent. Do not claim that approved develop supports managing schema60 model jobs. Existing factory does not enforce this version guard; add it at Web lifecycle boundary before migration-capable initialization in future work.

## Storage contract and future target

```text
%LOCALAPPDATA%\FashionAI\
  database/fashion_ai.db
  uploads/                    reserved upload staging, not final source authority
  models/                     explicit model roots, never packed in DB
  cache/                      disposable entries with managed index
  temp/                       per-operation UUID staging
  exports/                    optional future export root
  logs/
  storage/projects/{project_id}/
    source/                   immutable original filename UUID
    frames/                   OCR cached samples
    preview/m2/               compositor previews
    exports/                  existing M2 outputs
    audio/                    original, ASR, TTS cache, jobs and manifests
    final/{job_id}/            final.mp4, subtitles.ass, report.json
```

Preserve a compatibility `storage/projects` subtree because existing engine constructs those paths, and JSON manifests/snapshots contain relative artifact paths. Merely moving them into top-level uploads/exports would break contracts. Extra named top-level directories define future managed responsibilities, not authority to move current projects. Until an explicit StorageService refactor is accepted, set storage_root to this compatibility storage folder; separate DB URL and model roots are explicit absolute settings. Root `uploads` is only staging; final `import_video` still writes project/source. Keep one authoritative copy per adopted profile, no automatic dual-write.

Source defaults: ROOT/storage and SQLite URL ROOT/storage/fashion_ai.db. M5: data/storage/fashion_ai.db, data/models, data/config.env, data/logs; workers additionally write data/storage/logs and Paddle may create data/storage/models/paddlex-cache. Thus not every runtime cache follows the M5 models root. `load_dotenv(override=False)` means explicit process env wins over dotenv: approved develop loads ROOT/.env, while only M5 supports selecting FASHION_AI_ENV_FILE. API profile must set all engine root/model/tool fields consistently through explicit process environment on the approved base; workers receive the same validated configuration. Never copy secret env values into documents or public diagnostics.

## Future adoption / relocation procedure — not executed

1. User selects one source profile by opaque UI selection, confirms intended DB/storage/model paths and separately approves relocation. List estimated size/free disk and license requirements; don't combine demo DBs. Shut down source Streamlit/portable/Web writers with owned-process checks and lock the profile.
2. Inspect schema version/readiness read-only. Inventory every referenced relative artifact and absolute setting/JSON path; enumerate reparse points and reject unsafe roots. SQLite WAL is authoritative state: use SQLite backup API, never copy only a live `.db`. See [SQLite WAL documentation](https://sqlite.org/wal.html).
3. Create new target on the same local NTFS user disk, outside source and repository; refuse nonempty/overlapping target. Copy DB with backup API into staging; close/checkpoint destination, then hash. Copy source/artifacts preserving relative hierarchy, verify SHA256/size of originals and completed exports; never infer successful copy from filenames alone. Models may remain at an explicitly configured original root to avoid duplicate large downloads.
4. Run approved forward migrations on the COPY. Compare all pre-existing PK sets, FK relationships, row values, native job configs and artifact references; only explicitly approved mappings may differ. Adapt root-dependent absolute paths in copied config/snapshots/manifests by a documented mapping, preserve source hash identity and validate M2/M3/M4 contracts. Invalidate stale cache/readiness explicitly; don't silently alter reviewed content or falsify manifests.
5. Check SQLite integrity/foreign keys, required tools/fonts/models, source SHA, export SHA/playback, UUID identity, review revisions and restart recovery. Verify cold Web restart opens the same profile and no automatic source modification occurred. Record old/new schema and manifest in private backup.
6. Atomically select target profile only after verification and user approval. Retain original profile and a validated backup; avoid running both writer stacks simultaneously. Failure leaves target quarantined and source/profile selection unchanged. Rollback before new writes means select original; after target writes, first back up new work and reconcile/export explicitly—switching back blindly would lose new work.

M5 backup utility has the right SQLite close/checkpoint/hash principle but hardcodes storage/fashion_ai.db; it cannot directly back up arbitrary demo names or Web database/fashion_ai.db without adaptation. Restore is only into a new empty root. Backup contains private config/media; never commit/upload it. Encryption/access control and backup retention need owner policy. No expiry task deletes original sources or completed exports.

## Required future copy tests

Parameterized M0/no-ledger, v1,20,30,40,50,60 fixtures; inconsistent/unknown version; populated reviews/FKs/JSON; WAL data present; Unicode/path with spaces; source and target overlap/reparse point; disk-full/cancel/corrupt backup; missing artifact; no overwrite on nonempty target; all old values/IDs preserved; each M2/M3/M4 contract reopens; rollback after partial migration; originals byte-identical. W0 does not execute these migrations. Full live-data integrity and media verification are NOT TESTED here.

## Exact ORM schema appendix — VERIFIED

The definitions below are compiled offline from the audited SQLAlchemy metadata. They document every column, type/nullability, PK, FK, unique constraint, CHECK and explicit index. This is evidence, not a migration script to execute.

### Approved develop 51f1283 — 17 tables

#### dub_jobs

```sql
CREATE TABLE dub_jobs (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	request_token VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	status VARCHAR(30) NOT NULL, 
	active_slot INTEGER NOT NULL, 
	progress FLOAT NOT NULL, 
	config_snapshot JSON NOT NULL, 
	output_path TEXT, 
	output_duration FLOAT, 
	error_message TEXT, 
	pid INTEGER, 
	cancel_requested BOOLEAN NOT NULL, 
	lease_expires FLOAT NOT NULL, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CHECK (status IN ('QUEUED','EXTRACTING_AUDIO','TRANSCRIBING','TRANSLATING','GENERATING_TTS','SYNCHRONIZING','ASSEMBLING','COMPLETED','FAILED','CANCELLED')), 
	CHECK (active_slot=1), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	UNIQUE (request_token)
);
CREATE INDEX ix_dub_jobs_project_id ON dub_jobs (project_id);
CREATE UNIQUE INDEX uq_single_active_dub ON dub_jobs (active_slot) WHERE status NOT IN ('COMPLETED','FAILED','CANCELLED');
```

#### dubbed_audio_segments

```sql
CREATE TABLE dubbed_audio_segments (
	id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	speech_segment_id VARCHAR(36), 
	audio_path TEXT NOT NULL, 
	original_duration FLOAT NOT NULL, 
	generated_duration FLOAT NOT NULL, 
	final_duration FLOAT NOT NULL, 
	sync_factor FLOAT NOT NULL, 
	metadata_json JSON NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(job_id) REFERENCES dub_jobs (id), 
	FOREIGN KEY(speech_segment_id) REFERENCES speech_segments (id) ON DELETE SET NULL
);
CREATE INDEX ix_dubbed_audio_segments_job_id ON dubbed_audio_segments (job_id);
```

#### final_exports

```sql
CREATE TABLE final_exports (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	render_job_id VARCHAR(36) NOT NULL, 
	filename TEXT NOT NULL, 
	file_path TEXT NOT NULL, 
	file_size INTEGER NOT NULL, 
	duration FLOAT NOT NULL, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	deleted_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	UNIQUE (render_job_id), 
	FOREIGN KEY(render_job_id) REFERENCES final_render_jobs (id)
);
CREATE INDEX ix_final_exports_project_id ON final_exports (project_id);
```

#### final_render_jobs

```sql
CREATE TABLE final_render_jobs (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	request_token VARCHAR(36) NOT NULL, 
	active_slot INTEGER NOT NULL, 
	status VARCHAR NOT NULL, 
	progress FLOAT NOT NULL, 
	is_preview BOOLEAN NOT NULL, 
	cache_key VARCHAR(64) NOT NULL, 
	render_config JSON NOT NULL, 
	inputs JSON NOT NULL, 
	output_path TEXT, 
	report JSON, 
	error_message TEXT, 
	cancel_requested BOOLEAN NOT NULL, 
	pid INTEGER, 
	lease_expires FLOAT NOT NULL, 
	created_at DATETIME NOT NULL, 
	started_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CHECK (status IN ('QUEUED','PREPARING','GENERATING_SUBTITLES','MUXING','VALIDATING','COMPLETED','FAILED','CANCELLED')), 
	CHECK (active_slot=1), 
	CHECK (progress>=0 AND progress<=1), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	UNIQUE (request_token)
);
CREATE INDEX ix_final_render_jobs_cache_key ON final_render_jobs (cache_key);
CREATE INDEX ix_final_render_jobs_project_id ON final_render_jobs (project_id);
CREATE UNIQUE INDEX uq_single_active_final ON final_render_jobs (active_slot) WHERE status NOT IN ('COMPLETED','FAILED','CANCELLED');
```

#### ocr_detections

```sql
CREATE TABLE ocr_detections (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	segment_id VARCHAR(36), 
	frame_index INTEGER NOT NULL, 
	timestamp FLOAT NOT NULL, 
	frame_width INTEGER NOT NULL, 
	frame_height INTEGER NOT NULL, 
	source_text TEXT NOT NULL, 
	confidence FLOAT NOT NULL, 
	bounding_box JSON NOT NULL, 
	polygon JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (confidence >= 0 AND confidence <= 1), 
	CHECK (timestamp >= 0 AND frame_index >= 0 AND frame_width > 0 AND frame_height > 0), 
	CHECK (json_array_length(bounding_box) = 4 AND json_extract(bounding_box,'$[0]') >= 0 AND json_extract(bounding_box,'$[1]') >= 0 AND json_extract(bounding_box,'$[2]') > 0 AND json_extract(bounding_box,'$[3]') > 0), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(job_id) REFERENCES ocr_jobs (id), 
	FOREIGN KEY(segment_id) REFERENCES text_segments (id)
);
CREATE INDEX ix_detection_project_time ON ocr_detections (project_id, timestamp);
CREATE INDEX ix_ocr_detections_job_id ON ocr_detections (job_id);
CREATE INDEX ix_ocr_detections_segment_id ON ocr_detections (segment_id);
```

#### ocr_jobs

```sql
CREATE TABLE ocr_jobs (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(16) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	active_slot INTEGER NOT NULL, 
	config JSON NOT NULL, 
	completed_frames INTEGER NOT NULL, 
	total_frames INTEGER NOT NULL, 
	stage VARCHAR(32) NOT NULL, 
	cancel_requested BOOLEAN NOT NULL, 
	pid INTEGER, 
	lease_expires FLOAT NOT NULL, 
	error_message TEXT, 
	warning_message TEXT, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (status IN ('QUEUED','PROCESSING','COMPLETED','FAILED','CANCELLED')), 
	CHECK (kind IN ('ocr','translate')), 
	CHECK (active_slot = 1), 
	CHECK (completed_frames >= 0 AND total_frames >= completed_frames), 
	FOREIGN KEY(project_id) REFERENCES projects (id)
);
CREATE INDEX ix_ocr_jobs_project_id ON ocr_jobs (project_id);
CREATE UNIQUE INDEX uq_single_active_ocr ON ocr_jobs (active_slot) WHERE status IN ('QUEUED','PROCESSING');
```

#### projects

```sql
CREATE TABLE projects (
	id VARCHAR(36) NOT NULL, 
	upload_token VARCHAR(36) NOT NULL, 
	original_filename VARCHAR(255) NOT NULL, 
	stored_filename VARCHAR(255) NOT NULL, 
	source_url TEXT, 
	creator_name VARCHAR(255), 
	rights_status VARCHAR(32) NOT NULL, 
	rights_notes TEXT, 
	file_path TEXT NOT NULL, 
	file_size INTEGER NOT NULL, 
	duration FLOAT NOT NULL, 
	width INTEGER NOT NULL, 
	height INTEGER NOT NULL, 
	fps FLOAT NOT NULL, 
	video_codec VARCHAR(64) NOT NULL, 
	audio_codec VARCHAR(64), 
	aspect_ratio VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (upload_token)
);
CREATE INDEX ix_projects_created_at ON projects (created_at);
```

#### render_jobs

```sql
CREATE TABLE render_jobs (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	request_token VARCHAR(36) NOT NULL, 
	active_slot INTEGER NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	progress FLOAT NOT NULL, 
	config_snapshot JSON NOT NULL, 
	output_path TEXT, 
	error_message TEXT, 
	pid INTEGER, 
	cancel_requested BOOLEAN NOT NULL, 
	lease_expires FLOAT NOT NULL, 
	created_at DATETIME NOT NULL, 
	started_at DATETIME, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CHECK (status IN ('QUEUED','PROCESSING','COMPLETED','FAILED','CANCELLED')), 
	CHECK (active_slot=1), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	UNIQUE (request_token)
);
CREATE INDEX ix_render_jobs_project_id ON render_jobs (project_id);
CREATE UNIQUE INDEX uq_single_active_render ON render_jobs (active_slot) WHERE status IN ('QUEUED','PROCESSING');
```

#### review_events

```sql
CREATE TABLE review_events (
	id INTEGER NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	segment_id VARCHAR(36), 
	segment_key VARCHAR(36) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	mode VARCHAR(32) NOT NULL, 
	method VARCHAR(16) NOT NULL, 
	score FLOAT NOT NULL, 
	reasons JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(segment_id) REFERENCES text_segments (id) ON DELETE SET NULL
);
CREATE INDEX ix_review_events_project_id ON review_events (project_id);
```

#### schema_migrations

```sql
CREATE TABLE schema_migrations (
	version INTEGER NOT NULL, 
	applied_at DATETIME NOT NULL, 
	PRIMARY KEY (version)
);
```

#### segment_reviews

```sql
CREATE TABLE segment_reviews (
	segment_id VARCHAR(36) NOT NULL, 
	state VARCHAR(32) NOT NULL, 
	mode VARCHAR(32) NOT NULL, 
	method VARCHAR(16) NOT NULL, 
	score FLOAT NOT NULL, 
	reasons JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	reviewed_at DATETIME NOT NULL, 
	PRIMARY KEY (segment_id), 
	FOREIGN KEY(segment_id) REFERENCES text_segments (id) ON DELETE CASCADE
);
```

#### speaker_profiles

```sql
CREATE TABLE speaker_profiles (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	speaker_label VARCHAR(80) NOT NULL, 
	speaker_name VARCHAR(100) NOT NULL, 
	settings JSON NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (project_id, speaker_label), 
	FOREIGN KEY(project_id) REFERENCES projects (id)
);
CREATE INDEX ix_speaker_profiles_project_id ON speaker_profiles (project_id);
```

#### speech_segments

```sql
CREATE TABLE speech_segments (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	start_time FLOAT NOT NULL, 
	end_time FLOAT NOT NULL, 
	original_text TEXT NOT NULL, 
	translated_text TEXT NOT NULL, 
	speaker_id VARCHAR(80) NOT NULL, 
	asr_provider VARCHAR(100) NOT NULL, 
	confidence FLOAT, 
	review_status VARCHAR NOT NULL, 
	revision INTEGER NOT NULL, 
	warnings JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (start_time>=0 AND end_time>start_time), 
	CHECK (review_status IN ('pending','approved','rejected')), 
	CHECK (confidence IS NULL OR (confidence>=0 AND confidence<=1)), 
	FOREIGN KEY(project_id) REFERENCES projects (id)
);
CREATE INDEX ix_speech_segments_project_id ON speech_segments (project_id);
```

#### subtitle_files

```sql
CREATE TABLE subtitle_files (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	file_path TEXT NOT NULL, 
	subtitle_format VARCHAR NOT NULL, 
	subtitle_mode VARCHAR NOT NULL, 
	language VARCHAR NOT NULL, 
	style_config JSON NOT NULL, 
	report JSON NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES final_render_jobs (id)
);
CREATE INDEX ix_subtitle_files_project_id ON subtitle_files (project_id);
```

#### text_replacement_configs

```sql
CREATE TABLE text_replacement_configs (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	segment_id VARCHAR(36) NOT NULL, 
	settings JSON NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (project_id, segment_id), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(segment_id) REFERENCES text_segments (id) ON DELETE CASCADE
);
CREATE INDEX ix_text_replacement_configs_project_id ON text_replacement_configs (project_id);
```

#### text_segments

```sql
CREATE TABLE text_segments (
	id VARCHAR(36) NOT NULL, 
	project_id VARCHAR(36) NOT NULL, 
	job_id VARCHAR(36) NOT NULL, 
	source_text TEXT NOT NULL, 
	translated_text TEXT NOT NULL, 
	start_time FLOAT NOT NULL, 
	end_time FLOAT NOT NULL, 
	bounding_box JSON NOT NULL, 
	confidence FLOAT NOT NULL, 
	detection_status VARCHAR(32) NOT NULL, 
	translation_provider VARCHAR(255) NOT NULL, 
	review_status VARCHAR(16) NOT NULL, 
	translation_error TEXT, 
	revision INTEGER NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CHECK (review_status IN ('pending','approved','rejected')), 
	CHECK (confidence >= 0 AND confidence <= 1), 
	CHECK (start_time >= 0 AND end_time > start_time), 
	CHECK (revision >= 0), 
	CHECK (json_array_length(bounding_box) = 4 AND json_extract(bounding_box,'$[0]') >= 0 AND json_extract(bounding_box,'$[1]') >= 0 AND json_extract(bounding_box,'$[2]') > 0 AND json_extract(bounding_box,'$[3]') > 0), 
	FOREIGN KEY(project_id) REFERENCES projects (id), 
	FOREIGN KEY(job_id) REFERENCES ocr_jobs (id)
);
CREATE INDEX ix_segment_project_time ON text_segments (project_id, start_time);
```

#### translation_cache

```sql
CREATE TABLE translation_cache (
	"key" VARCHAR(64) NOT NULL, 
	provider VARCHAR(255) NOT NULL, 
	translated_text TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY ("key")
);
```

### Separate M5 8ac209c — optional eighteenth table

```sql
CREATE TABLE model_download_jobs (
	id VARCHAR NOT NULL, 
	slot INTEGER NOT NULL, 
	status VARCHAR NOT NULL, 
	"group" VARCHAR NOT NULL, 
	models_root TEXT NOT NULL, 
	progress FLOAT NOT NULL, 
	cancel_requested BOOLEAN NOT NULL, 
	pid INTEGER NOT NULL, 
	process_created FLOAT NOT NULL, 
	lease_expires FLOAT NOT NULL, 
	error TEXT, 
	result JSON, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	CHECK (status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED'))
);
CREATE UNIQUE INDEX uq_model_download_active ON model_download_jobs (slot) WHERE status IN ('QUEUED','RUNNING');
```
