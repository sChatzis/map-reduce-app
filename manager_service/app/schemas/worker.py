from datetime import datetime
from pydantic import BaseModel

from app.models.enums import WorkerStatus


class WorkerOut(BaseModel):
    worker_id: int
    pod_name: str
    status: WorkerStatus
    last_heartbeat: datetime

    model_config = {"from_attributes": True}
