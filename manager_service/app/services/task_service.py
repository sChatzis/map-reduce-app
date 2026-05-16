from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.task import Task
from app.models.enums import TaskType, TaskStatus
from app.utils.utility import is_valid_uuid

import logging

logger = logging.getLogger(__name__)

async def task_add(
        job_id: str,
        task_type: TaskType,
        input_split: str,
        data_location: str,
        db: AsyncSession
) -> Optional[Task]:
    if not is_valid_uuid(job_id):
        return None

    task = Task(
        job_id=job_id,
        type=task_type,
        status=TaskStatus.IDLE,
        input_split=input_split,
        data_location=data_location,
    )

    db.add(task)

    await db.commit()
    await db.refresh(task)

    return task


async def task_add_batch(
        job_id: str,
        task_type: TaskType,
        input_splits: list[str],
        data_locations: list[str],
        db: AsyncSession
) -> list[Task]:
    if not input_splits or not data_locations:
        return []

    if len(input_splits) != len(data_locations):
        return []

    if not is_valid_uuid(job_id):
        return []

    tasks = []

    for input_split, data_location in zip(input_splits, data_locations):
        task = Task(
            job_id=job_id,
            type=task_type,
            status=TaskStatus.IDLE,
            input_split=input_split,
            data_location=data_location,
        )
        db.add(task)
        tasks.append(task)

    await db.commit()

    for task in tasks:
        await db.refresh(task)

    return tasks


async def task_get(task_id: str, db: AsyncSession) -> Optional[Task]:
    if not is_valid_uuid(task_id):
        return None

    result = await db.execute(select(Task).where(Task.task_id == task_id))
    return result.scalar_one_or_none()


async def task_get_all(db: AsyncSession) -> list[Task]:
    result = await db.execute(select(Task))
    return list(result.scalars().all())


async def task_get_by_job(job_id: str, db: AsyncSession) -> list[Task]:
    if not is_valid_uuid(job_id):
        return []

    result = await db.execute(select(Task).where(Task.job_id == job_id))
    return list(result.scalars().all())


async def task_update_status(task_id: str, new_status: TaskStatus, db: AsyncSession) -> Optional[Task]:
    if not is_valid_uuid(task_id):
        return None

    async with db.begin_nested():
        result = await db.execute(
            select(Task)
            .where(Task.task_id == str(task_id))
            .with_for_update()
        )

        task = result.scalar_one_or_none()

        if task is None:
            return None

        task.status = new_status

    await db.commit()
    await db.refresh(task)

    return task
