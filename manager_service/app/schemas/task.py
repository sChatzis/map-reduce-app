from typing import Optional
from pydantic import BaseModel

from app.models.enums import TaskType, TaskStatus


class TaskOut(BaseModel):
    task_id: int
    type: TaskType
    status: TaskStatus
    input_split: Optional[str]
    data_location: Optional[str]
    job_id: int
    worker_id: Optional[int]

    model_config = {"from_attributes": True}
