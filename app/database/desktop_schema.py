from datetime import datetime
from sqlalchemy import CheckConstraint,Index,JSON,Text,text
from sqlalchemy.orm import Mapped,mapped_column
from app.database.models import Base,utc_now


class ModelDownloadJob(Base):
    __tablename__='model_download_jobs'
    __table_args__=(CheckConstraint("status IN ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')"),
        Index('uq_model_download_active','slot',unique=True,sqlite_where=text("status IN ('QUEUED','RUNNING')")),{'info':{'schema_version':60}})
    id:Mapped[str]=mapped_column(primary_key=True)
    slot:Mapped[int]=mapped_column(default=1)
    status:Mapped[str]=mapped_column(default='QUEUED')
    group:Mapped[str]
    models_root:Mapped[str]=mapped_column(Text)
    progress:Mapped[float]=mapped_column(default=0.)
    cancel_requested:Mapped[bool]=mapped_column(default=False)
    pid:Mapped[int]
    process_created:Mapped[float]
    lease_expires:Mapped[float]
    error:Mapped[str|None]=mapped_column(Text,nullable=True)
    result:Mapped[dict|None]=mapped_column(JSON,nullable=True)
    created_at:Mapped[datetime]=mapped_column(default=utc_now)
    completed_at:Mapped[datetime|None]=mapped_column(nullable=True)
