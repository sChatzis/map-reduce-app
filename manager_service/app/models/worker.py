from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.db.database import Base
import uuid
from datetime import datetime, UTC
from sqlalchemy import Column, String, Enum, DateTime
from sqlalchemy.orm import relationship
from app.db.database import Base
from app.models.enums import WorkerStatus


class Worker(Base):
    __tablename__ = "workers"

    worker_id = Column(Integer, primary_key=True, autoincrement=True)
    pod_name = Column(String(255), nullable=False)
    status = Column(String(20), default="IDLE", nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now())
    worker_id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    pod_name = Column(String, nullable=False, unique=True)
    status = Column(Enum(WorkerStatus), default=WorkerStatus.IDLE, nullable=False)
    last_heartbeat = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)

    tasks = relationship("Task", back_populates="worker")
