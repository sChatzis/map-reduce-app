from datetime import datetime
from pydantic import BaseModel

from app.models.enums import WorkerStatus

import uuid

class WorkerOut(BaseModel):
    worker_id: uuid.UUID
    pod_name: str
    status: WorkerStatus
    last_heartbeat: datetime

    model_config = {"from_attributes": True}
