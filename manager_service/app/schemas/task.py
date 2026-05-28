from typing import Optional
from pydantic import BaseModel

from app.models.enums import TaskType, TaskStatus

import uuid

class TaskOut(BaseModel):
    task_id: uuid.UUID
    type: TaskType
    status: TaskStatus
    input_split: Optional[str]
    data_location: Optional[str]
    job_id: uuid.UUID
    worker_id: Optional[uuid.UUID]

    model_config = {"from_attributes": True}
