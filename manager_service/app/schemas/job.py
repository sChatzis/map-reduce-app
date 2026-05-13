from datetime import datetime
from pydantic import BaseModel

from app.models.enums import JobStatus


class JobCreate(BaseModel):
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    user_id: int


class JobOut(BaseModel):
    job_id: int
    status: JobStatus
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    created_at: datetime
    updated_at: datetime
    user_id: int

    model_config = {"from_attributes": True}
