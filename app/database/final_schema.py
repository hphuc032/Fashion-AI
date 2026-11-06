from datetime import datetime
from sqlalchemy import Boolean,CheckConstraint,ForeignKey,Index,JSON,String,Text,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database.models import Base,utc_now

ACTIVE=('QUEUED','PREPARING','GENERATING_SUBTITLES','MUXING','VALIDATING')


class FinalRenderJob(Base):
    __tablename__='final_render_jobs'
    __table_args__=(CheckConstraint("status IN ('QUEUED','PREPARING','GENERATING_SUBTITLES','MUXING','VALIDATING','COMPLETED','FAILED','CANCELLED')"),
                    CheckConstraint('active_slot=1'),CheckConstraint('progress>=0 AND progress<=1'),
                    Index('uq_single_active_final','active_slot',unique=True,sqlite_where=text("status NOT IN ('COMPLETED','FAILED','CANCELLED')")),
                    {'info':{'schema_version':50}})
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(ForeignKey('projects.id'),index=True)
    request_token:Mapped[str]=mapped_column(String(36),unique=True)
    active_slot:Mapped[int]=mapped_column(default=1)
    status:Mapped[str]=mapped_column(default='QUEUED')
    progress:Mapped[float]=mapped_column(default=0.)
    is_preview:Mapped[bool]=mapped_column(Boolean,default=False)
    cache_key:Mapped[str]=mapped_column(String(64),index=True)
    render_config:Mapped[dict]=mapped_column(JSON)
    inputs:Mapped[dict]=mapped_column(JSON)
    output_path:Mapped[str|None]=mapped_column(Text,nullable=True)
    report:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    error_message:Mapped[str|None]=mapped_column(Text,nullable=True)
    cancel_requested:Mapped[bool]=mapped_column(Boolean,default=False)
    pid:Mapped[int|None]=mapped_column(nullable=True)
    lease_expires:Mapped[float]
    created_at:Mapped[datetime]=mapped_column(default=utc_now)
    started_at:Mapped[datetime|None]=mapped_column(nullable=True)
    completed_at:Mapped[datetime|None]=mapped_column(nullable=True)


class SubtitleFile(Base):
    __tablename__='subtitle_files'
    __table_args__=({'info':{'schema_version':50}},)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(ForeignKey('projects.id'),index=True)
    job_id:Mapped[str]=mapped_column(ForeignKey('final_render_jobs.id'),unique=True)
    file_path:Mapped[str]=mapped_column(Text)
    subtitle_format:Mapped[str]=mapped_column(default='ass')
    subtitle_mode:Mapped[str]
    language:Mapped[str]=mapped_column(default='vie')
    style_config:Mapped[dict]=mapped_column(JSON)
    report:Mapped[dict]=mapped_column(JSON)
    created_at:Mapped[datetime]=mapped_column(default=utc_now)


class FinalExport(Base):
    __tablename__='final_exports'
    __table_args__=({'info':{'schema_version':50}},)
    id:Mapped[str]=mapped_column(String(36),primary_key=True)
    project_id:Mapped[str]=mapped_column(ForeignKey('projects.id'),index=True)
    render_job_id:Mapped[str]=mapped_column(ForeignKey('final_render_jobs.id'),unique=True)
    filename:Mapped[str]=mapped_column(Text)
    file_path:Mapped[str]=mapped_column(Text)
    file_size:Mapped[int]
    duration:Mapped[float]
    width:Mapped[int]
    height:Mapped[int]
    sha256:Mapped[str]=mapped_column(String(64))
    deleted_at:Mapped[datetime|None]=mapped_column(nullable=True)
    created_at:Mapped[datetime]=mapped_column(default=utc_now)
