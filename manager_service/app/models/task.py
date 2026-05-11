from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(10), nullable=False)
    status = Column(String(20), default="IDLE", nullable=False)
    input_split = Column(String(255))
    data_location = Column(String(255))
    job_id = Column(Integer, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.worker_id", ondelete="SET NULL"), nullable=True)

    job = relationship("Job", back_populates="tasks")
    worker = relationship("Worker", back_populates="tasks")
