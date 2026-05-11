import uuid
from sqlalchemy import Column, String, Enum, ForeignKey
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.models.enums import TaskType, TaskStatus


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String, ForeignKey("jobs.job_id"), nullable=False)
    type = Column(Enum(TaskType), nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.IDLE, nullable=False)
    worker_pod_id = Column(String, ForeignKey("workers.worker_id"), nullable=True)
    input_split = Column(String, nullable=True)   # MinIO path to this task's input split
    data_location = Column(String, nullable=True) # MinIO path to intermediate/output data

    job = relationship("Job", back_populates="tasks")
    worker = relationship("Worker", back_populates="tasks")
