from app.core.settings import settings
from app.kubernetes_client import _get_batch_client

import asyncio
import logging

import app.db as db

logger = logging.getLogger(__name__)

async def monitor_workers():
    while True:
        try:
            batch_v1 = _get_batch_client()

            k8s_workers = await asyncio.to_thread(
                batch_v1.list_namespaced_job,
                namespace=settings.MANAGER_NAMESPACE,
            )

            for job in k8s_workers.items:
                name = job.metadata.name
                status = job.status

                if (status.succeeded or 0) > 0:
                    logger.info(f"[kubernetes_service.py] {name} succeeded")

                elif (status.failed or 0) > 0:
                    logger.info(f"[kubernetes_service.py] {name} failed")

        except Exception as ex:
            logger.warning(f"[kubernetes_service.py] Exception occurred: {ex}")

        await asyncio.sleep(10)


async def safe_monitor_workers():
    try:
        await monitor_workers()
    except Exception as ex:
        logger.exception(f"monitor_workers crashed: {ex}")