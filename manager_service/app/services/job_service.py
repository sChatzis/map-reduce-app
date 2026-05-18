from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select

from app.models.job import Job
from app.models.enums import JobStatus
from app.schemas.job import JobCreate
from app.utils.utility import is_valid_path, is_valid_uuid
from app.services.minio_service import file_exists

import logging

logger = logging.getLogger(__name__)

async def job_add(req: JobCreate, db: AsyncSession) -> Optional[Job]:
    if req.user_id <= 0:
        logger.warning(f"[job_service] job_add: user_id not valid [{req.user_id}]")
        return None

    for field_name, value in [
        ("input_files", req.input_files),
        ("mapper_code", req.mapper_code),
        ("reducer_code", req.reducer_code),
    ]:
        if not is_valid_path(value):
            logger.warning(f"[job_service] job_add: invalid path for {field_name} [{value}]")
            return None
        try:
            if not file_exists(value):
                logger.warning(f"[job_service] job_add: file doesn't exist [{value}]")
                return None
        except Exception as ex:
            logger.warning(f"[job_service] job_add: exception occurred with minio client [{ex}]")
            return None

    if (req.output_path != "") and not is_valid_path(req.output_path):
        logger.warning(f"[job_service] job_add: invalid output path[{value}]")
        return None

    output_path = req.output_path

    job = Job(
        status=JobStatus.SUBMITTED,
        input_files=req.input_files,
        output_path=output_path,
        mapper_code=req.mapper_code,
        reducer_code=req.reducer_code,
        user_id=str(req.user_id),
        num_mappers=req.num_mappers,
        num_reducers=req.num_reducers,
    )

    db.add(job)

    await db.commit()
    await db.refresh(job)

    return job


async def job_get(job_id: str, db: AsyncSession) -> Optional[Job]:
    if not is_valid_uuid(job_id):
        return None

    result = await db.execute(select(Job).where(Job.job_id == job_id))
    return result.scalar_one_or_none()


async def job_get_batch(job_ids: list[str], db: AsyncSession) -> list[Job]:
    if not job_ids:
        return []

    if not all(is_valid_uuid(jid) for jid in job_ids):
        return []

    result = await db.execute(
        select(Job).where(Job.job_id.in_(job_ids))
    )

    return list(result.scalars().all())


async def job_get_all(db: AsyncSession) -> list[Job]:
    result = await db.execute(select(Job).offset(0).limit(100))
    return list(result.scalars().all())


async def job_get_submitted(db: AsyncSession) -> list[Job]:
    result = await db.execute(select(Job).where(Job.status == JobStatus.SUBMITTED))
    return list(result.scalars().all())


async def job_update_status(job_id: str, new_status: JobStatus, db: AsyncSession) -> Optional[Job]:
    if not is_valid_uuid(job_id):
        return None

    result = await db.execute(
        select(Job)
        .where(Job.job_id == job_id)
        .with_for_update()
    )

    job = result.scalar_one_or_none()

    if job is None:
        return None

    job.status = new_status

    await db.commit()
    await db.refresh(job)

    return job


async def job_update_status_batch(
    job_ids: list[str],
    new_status: JobStatus,
    db: AsyncSession
) -> int:

    valid_ids = [
        job_id
        for job_id in job_ids
        if is_valid_uuid(job_id)
    ]

    if not valid_ids:
        return 0

    await db.execute(
        update(Job)
        .where(Job.job_id.in_(valid_ids))
        .where(Job.status != new_status)
        .values(status=new_status)
    )

    await db.commit()

    return len(valid_ids)