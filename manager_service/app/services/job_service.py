from typing import Optional

from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.enums import JobStatus
from app.schemas.job import JobCreate
from app.utils.utility import is_valid_path

def job_add(req: JobCreate, db: Session) -> Optional[Job]:
    if req.user_id <= 0:
        print(f"[job_service] job_add: user_id not valid [{req.user_id}]")
        return None

    for field_name, value in [
        ("input_files", req.input_files),
        ("output_path", req.output_path),
        ("mapper_code", req.mapper_code),
        ("reducer_code", req.reducer_code),
    ]:
        if not is_valid_path(value):
            print(f"[job_service] job_add: invalid path for {field_name} [{value}]")
            return None

    job = Job(
        status=JobStatus.SUBMITTED,
        input_files=req.input_files,
        output_path=req.output_path,
        mapper_code=req.mapper_code,
        reducer_code=req.reducer_code,
        user_id=req.user_id,
    )

    db.add(job)
    db.commit()
    db.refresh(job)

    return job

def job_get(job_id: int, db: Session) -> Optional[Job]:
    return db.query(Job).filter(Job.job_id == job_id).first()

def job_get_all(db: Session) -> list[Job]:
    return db.query(Job).all()

def job_update_status(job_id: int, new_status: JobStatus, db: Session) -> Optional[Job]:
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if job is None:
        return None
    job.status = new_status
    db.commit()
    db.refresh(job)
    return job
