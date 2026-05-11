from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Worker(Base):
    __tablename__ = "workers"

    worker_id = Column(Integer, primary_key=True, autoincrement=True)
    pod_name = Column(String(255), nullable=False)
    status = Column(String(20), default="IDLE", nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship("Task", back_populates="worker")
