from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.db.database import Base
import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, Enum, DateTime
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.models.enums import JobStatus


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), default="SUBMITTED", nullable=False)
    input_files = Column(String(255), nullable=False)
    output_path = Column(String(255), nullable=False)
    mapper_code = Column(String(255), nullable=False)
    reducer_code = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_id = Column(Integer, nullable=False)
    job_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False)  # JWT sub — no FK across service boundaries
    status = Column(Enum(JobStatus), default=JobStatus.SUBMITTED, nullable=False)
    input_files = Column(String, nullable=False)      # MinIO path to input file
    output_path = Column(String, nullable=True)       # MinIO path to output (set on completion)
    mapper_code = Column(String, nullable=False)      # MinIO path to mapper .py
    reducer_code = Column(String, nullable=False)     # MinIO path to reducer .py
    num_mappers = Column(String, nullable=False, default="1")
    num_reducers = Column(String, nullable=False, default="1")
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC),
                        onupdate=lambda: datetime.now(UTC), nullable=False)

    tasks = relationship("Task", back_populates="job", cascade="all, delete-orphan")
