from datetime import datetime
from pydantic import BaseModel

from app.models.enums import JobStatus

import uuid

class JobCreate(BaseModel):
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    user_id: int
    num_mappers: int = 4
    num_reducers: int = 2

class JobOut(BaseModel):
    job_id: uuid.UUID
    status: JobStatus
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    num_mappers: int
    num_reducers: int
    created_at: datetime
    updated_at: datetime
    user_id: int

    model_config = {"from_attributes": True}
