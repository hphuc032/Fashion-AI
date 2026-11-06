"""Additive version40; speech never overwrites on-screen captions."""
from datetime import datetime
from sqlalchemy import Boolean,CheckConstraint,ForeignKey,Index,JSON,String,Text,UniqueConstraint,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database.models import Base,utc_now

ACTIVE = ('QUEUED','EXTRACTING_AUDIO','TRANSCRIBING','TRANSLATING','GENERATING_TTS','SYNCHRONIZING','ASSEMBLING')


class SpeechSegment(Base):
    __tablename__='speech_segments'
    __table_args__=(CheckConstraint('start_time>=0 AND end_time>start_time'),
                    CheckConstraint("review_status IN ('pending','approved','rejected')"),
                    CheckConstraint('confidence IS NULL OR (confidence>=0 AND confidence<=1)'),
                    {'info':{'schema_version':40}})
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(ForeignKey('projects.id'),index=True)
    start_time:Mapped[float]
    end_time:Mapped[float]
    original_text:Mapped[str]=mapped_column(Text)
    translated_text:Mapped[str]=mapped_column(Text,default='')
    speaker_id:Mapped[str]=mapped_column(String(80),default='speaker_1')
    asr_provider:Mapped[str]=mapped_column(String(100))
    confidence:Mapped[float|None]=mapped_column(nullable=True)
    review_status:Mapped[str]=mapped_column(default='pending')
    revision:Mapped[int]=mapped_column(default=0)
    warnings:Mapped[list]=mapped_column(JSON,default=list)
    created_at:Mapped[datetime]=mapped_column(default=utc_now)
    updated_at:Mapped[datetime]=mapped_column(default=utc_now,onupdate=utc_now)


class SpeakerProfile(Base):
    __tablename__='speaker_profiles'
    __table_args__=(UniqueConstraint('project_id','speaker_label'),{'info':{'schema_version':40}})
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(ForeignKey('projects.id'),index=True)
    speaker_label:Mapped[str]=mapped_column(String(80))
    speaker_name:Mapped[str]=mapped_column(String(100))
    settings:Mapped[dict]=mapped_column(JSON)


class DubJob(Base):
    __tablename__='dub_jobs'
    __table_args__=(CheckConstraint("status IN ('QUEUED','EXTRACTING_AUDIO','TRANSCRIBING','TRANSLATING','GENERATING_TTS','SYNCHRONIZING','ASSEMBLING','COMPLETED','FAILED','CANCELLED')"),
                    CheckConstraint('active_slot=1'),
                    Index('uq_single_active_dub','active_slot',unique=True,sqlite_where=text("status NOT IN ('COMPLETED','FAILED','CANCELLED')")),
                    {'info':{'schema_version':40}})
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(ForeignKey('projects.id'),index=True)
    request_token:Mapped[str]=mapped_column(String(36),unique=True)
    kind:Mapped[str]=mapped_column(String(20))
    status:Mapped[str]=mapped_column(String(30),default='QUEUED')
    active_slot:Mapped[int]=mapped_column(default=1)
    progress:Mapped[float]=mapped_column(default=0)
    config_snapshot:Mapped[dict]=mapped_column(JSON)
    output_path:Mapped[str|None]=mapped_column(Text,nullable=True)
    output_duration:Mapped[float|None]=mapped_column(nullable=True)
    error_message:Mapped[str|None]=mapped_column(Text,nullable=True)
    pid:Mapped[int|None]=mapped_column(nullable=True)
    cancel_requested:Mapped[bool]=mapped_column(Boolean,default=False)
    lease_expires:Mapped[float]
    created_at:Mapped[datetime]=mapped_column(default=utc_now)
    completed_at:Mapped[datetime|None]=mapped_column(nullable=True)


class DubbedAudioSegment(Base):
    __tablename__='dubbed_audio_segments'
    __table_args__=({'info':{'schema_version':40}},)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    job_id:Mapped[str]=mapped_column(ForeignKey('dub_jobs.id'),index=True)
    speech_segment_id:Mapped[str|None]=mapped_column(ForeignKey('speech_segments.id',ondelete='SET NULL'),nullable=True)
    audio_path:Mapped[str]=mapped_column(Text)
    original_duration:Mapped[float]
    generated_duration:Mapped[float]
    final_duration:Mapped[float]
    sync_factor:Mapped[float]
    metadata_json:Mapped[dict]=mapped_column(JSON)
