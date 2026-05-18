from typing import Optional
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update, select, delete
from sqlalchemy.orm import selectinload

from app.models.worker import Worker
from app.models.task import Task
from app.models.enums import WorkerStatus
from app.utils.utility import is_valid_uuid

import logging

logger = logging.getLogger(__name__)

async def worker_add(pod_name: str, db: AsyncSession) -> Optional[Worker]:
    if not pod_name:
        return None

    worker = Worker(
        pod_name=pod_name,
        status=WorkerStatus.IDLE,
    )

    db.add(worker)
    await db.commit()
    await db.refresh(worker)

    return worker


async def worker_add_batch(pod_names: list[str], db: AsyncSession) -> list[Worker]:
    if not pod_names:
        return []

    workers = []

    for pod_name in pod_names:
        worker = Worker(
            pod_name=pod_name,
            status=WorkerStatus.IDLE,
        )
        db.add(worker)
        workers.append(worker)

    await db.commit()

    for worker in workers:
        await db.refresh(worker)

    return workers


async def worker_get(worker_id: str, db: AsyncSession) -> Optional[Worker]:
    if not is_valid_uuid(worker_id):
        return None

    result = await db.execute(select(Worker).where(Worker.worker_id == worker_id))
    return result.scalar_one_or_none()


async def worker_get_batch(worker_ids: list[str], db: AsyncSession) -> list[Worker]:
    valid_ids = [wid for wid in worker_ids if is_valid_uuid(wid)]
    if not valid_ids:
        return []

    stmt = (
        select(Worker)
        .where(Worker.worker_id.in_(valid_ids))
        .options(
            selectinload(Worker.tasks).selectinload(Task.job)
        )
    )

    result = await db.execute(stmt)

    return list(result.scalars().all())


async def worker_get_all(db: AsyncSession) -> list[Worker]:
    result = await db.execute(select(Worker))
    return list(result.scalars().all())


async def worker_update_status(worker_id: str, new_status: WorkerStatus, db: AsyncSession) -> Optional[Worker]:
    if not is_valid_uuid(worker_id):
        return None

    result = await db.execute(
        select(Worker)
        .where(Worker.worker_id == worker_id)
        .with_for_update()
    )

    worker = result.scalar_one_or_none()

    if worker is None:
        return None

    worker.status = new_status
    worker.last_heartbeat = datetime.now(UTC)

    await db.commit()
    await db.refresh(worker)

    return worker


async def worker_update_status_batch(
    worker_ids: list[str],
    new_status: WorkerStatus,
    db: AsyncSession
) -> int:
    valid_ids = [wid for wid in worker_ids if is_valid_uuid(wid)]

    if not valid_ids:
        return 0

    result = await db.execute(
        update(Worker)
        .where(Worker.worker_id.in_(valid_ids))
        .where(Worker.status != new_status)
        .values(
            status=new_status,
            last_heartbeat=datetime.now(UTC)
        )
    )

    await db.commit()

    return result.rowcount or 0


async def worker_delete_batch(worker_id: list[str], db: AsyncSession):
    valid_ids = [wid for wid in worker_id if is_valid_uuid(wid)]

    if not valid_ids:
        return 0

    result = await db.execute(
        delete(Worker).where(Worker.worker_id.in_(valid_ids))
    )

    await db.commit()

    return result.rowcount or 0