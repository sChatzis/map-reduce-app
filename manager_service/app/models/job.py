from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.db.database import Base


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

    tasks = relationship("Task", back_populates="job", cascade="all, delete-orphan")
