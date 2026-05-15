from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.job import JobCreate, JobOut
from app.models.enums import JobStatus, TaskType
from app.services import job_service
from app.services import task_service
from app.utils import utility

router = APIRouter()

@router.post("/jobs", response_model=JobOut, status_code=201)
def add_job(req: JobCreate, db: Session = Depends(get_db)):
    print("[jobs.py] add_job")
    job = job_service.job_add(req, db)

    if job is None:
        raise HTTPException(status_code=500, detail="Job insert failed")

    input_split = utility.split_input_file_to_chunks(job.input_files, 4)
    output_split = utility.generate_map_output_paths(job.input_files, 4)

    tasks = task_service.task_add_batch(job.job_id, TaskType.MAP, input_split, output_split, db)

    if tasks is None:
        raise HTTPException(status_code=500, detail="Map tasks insert failed")

    input_split = utility.generate_reduce_input_paths(job.input_files, 2)
    output_split = utility.generate_reduce_output_paths(job.input_files, 2)

    tasks = task_service.task_add_batch(job.job_id, TaskType.REDUCE, input_split, output_split, db)

    if tasks is None:
        raise HTTPException(status_code=500, detail="Reduce tasks insert failed")

    return job


@router.get("/jobs", response_model=list[JobOut])
def get_jobs(db: Session = Depends(get_db)):
    print("[jobs.py] get_jobs")
    return job_service.job_get_all(db)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    print(f"[jobs.py] get_job: job_id [{job_id}]")
    job = job_service.job_get(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")
    return job


@router.get("/jobs/{job_id}/result")
def get_job_result(job_id: int, db: Session = Depends(get_db)):
    print(f"[jobs.py] get_job_result: job_id [{job_id}]")
    job = job_service.job_get(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is not completed yet (status: {job.status})")
    return {"output_path": job.output_path}


@router.post("/jobs/{job_id}/recover")
def recover_job(job_id: int, db: Session = Depends(get_db)):
    print(f"[jobs.py] recover_job: job_id [{job_id}]")
    job = job_service.job_get(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")
    return {"message": f"Recovered job {job_id}"}
