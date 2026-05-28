from typing import Optional


from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select, func

from app.core.settings import settings
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


async def task_get_all(db: AsyncSession,) -> list[Task]:
    result = await db.execute(select(Task))
    return list(result.scalars().all())


async def task_get_all_idle(
        db: AsyncSession,
        limit: int = settings.MANAGER_MAX_TASKS_PER_CYCLE
) -> list[Task]:
    result = await db.execute(
        select(Task)
        .where(Task.status == TaskStatus.IDLE)
        .where(Task.worker_pod_id.is_(None))
        .limit(limit)
    )
    return list(result.scalars().all())


async def task_get_in_progress(db: AsyncSession) -> list[Task]:
    result = await db.execute(select(Task).where(Task.status == TaskStatus.IN_PROGRESS))
    return list(result.scalars().all())


async def task_get_map_jobs(db: AsyncSession) -> list[str]:
    result = await db.execute(
        select(Task.job_id)
        .distinct()
        .where(Task.type == TaskType.MAP)
    )

    return [row[0] for row in result.all()]


async def task_get_completed_map_tasks_by_jobs(
    job_ids: list[str],
    db: AsyncSession
) -> list[Task]:
    if not job_ids:
        return []

    result = await db.execute(
        select(Task)
        .where(Task.job_id.in_(job_ids))
        .where(Task.type == TaskType.MAP)
        .where(Task.status == TaskStatus.COMPLETED)
    )

    return list(result.scalars().all())


async def task_get_by_job(job_id: str, db: AsyncSession) -> list[Task]:
    if not is_valid_uuid(job_id):
        return []

    result = await db.execute(select(Task).where(Task.job_id == job_id))
    return list(result.scalars().all())


async def task_get_reduce_by_job(job_id: str, db: AsyncSession) -> list[Task]:
    if not is_valid_uuid(job_id):
        return []

    result = await db.execute(
        select(Task)
        .where(Task.job_id == job_id)
        .where(Task.type == TaskType.REDUCE)
        .order_by(Task.task_id)
    )

    return list(result.scalars().all())


async def task_get_by_worker(worker_pod_id: str, db: AsyncSession) -> list[Task]:
    if not is_valid_uuid(worker_pod_id):
        return []

    result = await db.execute(select(Task).where(Task.worker_pod_id == worker_pod_id))
    return list(result.scalars().all())


async def task_get_by_worker_batch(
    worker_pod_ids: list[str],
    db: AsyncSession
) -> list[Task]:
    valid_ids = [wid for wid in worker_pod_ids if is_valid_uuid(wid)]

    if not valid_ids:
        return []

    result = await db.execute(
        select(Task).where(Task.worker_pod_id.in_(valid_ids))
    )

    return list(result.scalars().all())


async def task_update_status(task_id: str, new_status: TaskStatus, db: AsyncSession) -> Optional[Task]:
    if not is_valid_uuid(task_id):
        return None

    result = await db.execute(
        select(Task)
        .where(Task.task_id == task_id)
        .with_for_update()
    )

    task = result.scalar_one_or_none()

    if task is None:
        return None

    task.status = new_status

    await db.commit()
    await db.refresh(task)

    return task


async def task_update_status_batch(
    task_ids: list[str],
    new_status: TaskStatus,
    db: AsyncSession
) -> int:
    valid_ids = [tid for tid in task_ids if is_valid_uuid(tid)]

    if not valid_ids:
        return 0

    result = await db.execute(
        update(Task)
        .where(Task.task_id.in_(valid_ids))
        .where(Task.status != new_status)
        .values(status=new_status)
    )

    await db.commit()

    return result.rowcount or 0


async def task_update_worker(task_id: str, worker_pod_id: str, db: AsyncSession) -> Optional[Task]:
    if not is_valid_uuid(task_id) or not is_valid_uuid(worker_pod_id):
        return None

    result = await db.execute(
        select(Task)
        .where(Task.task_id == task_id)
        .with_for_update()
    )

    task = result.scalar_one_or_none()

    if task is None:
        return None

    task.worker_pod_id = worker_pod_id

    await db.commit()
    await db.refresh(task)

    return task


async def task_update_worker_batch(
    task_ids: list[str],
    worker_pod_ids: list[str],
    db: AsyncSession
) -> int:

    valid_task_ids = [tid for tid in task_ids if is_valid_uuid(tid)]
    valid_worker_ids = [wid for wid in worker_pod_ids if is_valid_uuid(wid)]

    if not valid_task_ids or not valid_worker_ids:
        return 0

    if len(valid_task_ids) != len(valid_worker_ids):
        raise ValueError("task_ids and worker_pod_ids must match one to one")

    updates = list(zip(valid_task_ids, valid_worker_ids))

    result_count = 0

    for task_id, worker_id in updates:
        result = await db.execute(
            update(Task)
            .where(Task.task_id == task_id)
            .where(Task.worker_pod_id.is_(None))
            .values(worker_pod_id=worker_id)
        )
        result_count += result.rowcount or 0

    await db.commit()
    return result_count


async def task_clear_worker(task_id: str, db: AsyncSession) -> bool:
    if not is_valid_uuid(task_id):
        return False

    result = await db.execute(
        select(Task)
        .where(Task.task_id == task_id)
        .with_for_update()
    )

    task = result.scalar_one_or_none()

    if task is None:
        return False

    task.worker_pod_id = None

    await db.commit()
    await db.refresh(task)

    return True


async def task_clear_worker_batch(
    task_ids: list[str],
    db: AsyncSession
) -> int:
    valid_ids = [tid for tid in task_ids if is_valid_uuid(tid)]

    if not valid_ids:
        return 0

    result = await db.execute(
        update(Task)
        .where(Task.task_id.in_(valid_ids))
        .values(worker_pod_id=None)
    )

    await db.commit()

    return result.rowcount or 0


async def task_are_maps_done(job_id: str, db: AsyncSession) -> bool:
    statement = (
        select(func.count())
        .select_from(Task)
        .where(Task.job_id == job_id)
        .where(Task.type == TaskType.MAP)
        .where(Task.status != TaskStatus.COMPLETED)
    )

    result = await db.execute(statement)
    remaining = result.scalar_one()

    return remaining == 0


async def task_are_maps_done_batch(
    job_ids: list[str],
    db: AsyncSession
) -> dict[str, bool]:

    if not job_ids:
        return {}

    statement = (
        select(
            Task.job_id,
            func.count(Task.task_id).label("remaining")
        )
        .where(Task.job_id.in_(job_ids))
        .where(Task.type == TaskType.MAP)
        .where(Task.status != TaskStatus.COMPLETED)
        .group_by(Task.job_id)
    )

    result = await db.execute(statement)

    remaining_map = {row.job_id: row.remaining for row in result.all()}

    return {
        job_id: remaining_map.get(job_id, 0) == 0
        for job_id in job_ids
    }


async def task_get_in_progress_count(db: AsyncSession) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(Task)
        .where(Task.status == TaskStatus.IN_PROGRESS)
    )
    return result.scalar_one()