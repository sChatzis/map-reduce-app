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
    logger.info("\n/jobs [add_job]\n")

    if req.num_mappers < 1:
        raise HTTPException(status_code=400, detail="num_mappers must be >= 1")

    if req.num_reducers < 1:
        raise HTTPException(status_code=400, detail="num_reducers must be >= 1")

    job = await job_service.job_add(req, db)

    if job is None:
        raise HTTPException(status_code=500, detail="Job insert failed")

    # NOTE: step 7 of the orchestration plan will move chunking + MAP-task
    # spawn into the K8s Job spawn flow. Until then, derive ``actual_mappers``
    # from the split result, not the request: ``split_input_file_to_chunks``
    # returns fewer chunks than requested when the input has fewer non-empty
    # lines than ``num_mappers``. Using the request value would produce a
    # paths/inputs length mismatch in ``task_add_batch``.
    map_inputs = utility.split_input_file_to_chunks(
        job.input_files, job.job_id, job.num_mappers
    )
    actual_mappers = len(map_inputs)
    map_outputs = utility.generate_map_output_paths(
        job.input_files, job.job_id, actual_mappers
    )

    map_tasks = await task_service.task_add_batch(
        job.job_id, TaskType.MAP, map_inputs, map_outputs, db
    )

    if not map_tasks:
        raise HTTPException(status_code=500, detail="Map tasks insert failed")

    return job


@router.get("/jobs", response_model=list[JobOut])
async def get_jobs(db: AsyncSession = Depends(get_db)):
    logger.info("\n/jobs [get_jobs]\n")
    return await job_service.job_get_all(db)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"\n/jobs/{job_id} [get_job]\n")
    job = await job_service.job_get(job_id, db)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")

    return job


@router.get("/jobs/{job_id}/result")
async def get_job_result(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"\n/jobs/{job_id}/result [get_job_result]\n")
    job = await job_service.job_get(job_id, db)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is not completed yet (status: {job.status.value})")

    return {"output_path": job.output_path}


@router.post("/jobs/{job_id}/recover")
async def recover_job(job_id: str, db: AsyncSession = Depends(get_db)):
    logger.info(f"\n/jobs/{job_id}/recover [recover_job]\n")

    job = await job_service.job_get(job_id, db)

    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")

    return {"message": f"Recovered job {job_id}"}
