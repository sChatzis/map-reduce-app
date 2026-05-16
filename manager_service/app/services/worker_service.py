from typing import Optional
from datetime import datetime, UTC

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.worker import Worker
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


async def worker_get(worker_id: str, db: AsyncSession) -> Optional[Worker]:
    if not is_valid_uuid(worker_id):
        return None

    result = await db.execute(select(Worker).where(Worker.worker_id == worker_id))
    return result.scalar_one_or_none()


async def worker_get_all(db: AsyncSession) -> list[Worker]:
    result = await db.execute(select(Worker))
    return list(result.scalars().all())


async def worker_update_status(worker_id: str, new_status: WorkerStatus, db: AsyncSession) -> Optional[Worker]:
    if not is_valid_uuid(worker_id):
        return None

    async with db.begin_nested():
        result = await db.execute(
            select(Worker)
            .where(Worker.worker_id == str(worker_id))
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