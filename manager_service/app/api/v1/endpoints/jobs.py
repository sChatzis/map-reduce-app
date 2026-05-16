from fastapi import APIRouter, HTTPException, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.schemas.job import JobCreate, JobOut
from app.models.enums import JobStatus, TaskType
from app.services import job_service
from app.services import task_service
from app.utils import utility

import logging

router = APIRouter()

logger = logging.getLogger(__name__)

@router.post("/jobs", response_model=JobOut, status_code=201)
async def add_job(req: JobCreate, db: AsyncSession = Depends(get_db)):
    logger.info("[jobs.py] add_job")
    job = await job_service.job_add(req, db)

    if job is None:
        raise HTTPException(status_code=500, detail="Job insert failed")

    num_chunks = utility.calculate_num_chunks(job.input_files)
    num_partitions = utility.calculate_num_partitions(num_chunks)

    input_split = utility.split_input_file_to_chunks(job.input_files, job.job_id)
    output_split = utility.generate_map_output_paths(job.input_files, job.job_id, num_chunks)

    tasks = await task_service.task_add_batch(job.job_id, TaskType.MAP, input_split, output_split, db)

    if len(tasks) == 0:
        raise HTTPException(status_code=500, detail="Map tasks insert failed")

    input_split = utility.generate_reduce_input_paths(job.input_files, job.job_id, num_partitions)
    output_split = utility.generate_reduce_output_paths(job.input_files, job.job_id, num_partitions)

    tasks = await task_service.task_add_batch(job.job_id, TaskType.REDUCE, input_split, output_split, db)

    if len(tasks) == 0:
        raise HTTPException(status_code=500, detail="Reduce tasks insert failed")

    return job


@router.get("/jobs", response_model=list[JobOut])
async def get_jobs(db: AsyncSession = Depends(get_db)):
    logger.info("[jobs.py] get_jobs")
    return await job_service.job_get_all(db)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"[jobs.py] get_job: job_id [{job_id}]")
    job = await job_service.job_get(job_id, db)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")

    return job


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"[jobs.py] get_job_result: job_id [{job_id}]")
    job = await job_service.job_get(job_id, db)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is not completed yet (status: {job.status})")

    return {"output_path": job.output_path}


@router.post("/jobs/{job_id}/recover")
async def recover_job(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"[jobs.py] recover_job: job_id [{job_id}]")

    job = await job_service.job_get(job_id, db)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")

    return {"message": f"Recovered job {job_id}"}
