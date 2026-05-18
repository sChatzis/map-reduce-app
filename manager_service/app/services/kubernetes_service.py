from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.database import AsyncSessionLocal
from app.models.enums import *
from app.models.job import Job
from app.models.task import Task
from app.models.worker import Worker
from app.services.job_service import job_get_batch, job_update_status
from app.services.task_service import (
    task_get_all_idle,
    task_are_maps_done_batch,
    task_update_status_batch,
    task_update_worker_batch,
    task_get_by_worker_batch, task_get_map_jobs, task_get_completed_map_tasks_by_jobs, task_add_batch,
    task_get_reduce_by_job
)
from app.services.worker_service import (
    worker_update_status_batch,
    worker_add_batch,
    worker_get_batch,
)
from app.kubernetes_client import (
    create_worker_job,
    get_batch_client,
    get_core_client,
)
from app.utils.utility import merge_and_partition_map, generate_reduce_output_paths, final_reduce_merge, cleanup_job_files

import asyncio
import logging

logger = logging.getLogger(__name__)

# =========================================================
# MAIN LOOP
# =========================================================

async def safe_monitor():
    try:
        await monitor()
    except Exception as ex:
        logger.exception(f"[kubernetes_service.py]: monitor crashed [{ex}]")


async def monitor():
    while True:
        try:
            await schedule()
            await monitor_running_workers()
        except Exception as ex:
            logger.warning(f"[kubernetes_service.py]: Exception occurred: {ex}")

        await asyncio.sleep(settings.MANAGER_REFRESH_PERIOD)


async def schedule():
    async with AsyncSessionLocal() as db:
        await _schedule(db)


# =========================================================
# SCHEDULER
# =========================================================

async def _schedule(db: AsyncSession):
    logger.info(
        f"[kubernetes_service.py]: Monitoring kubernetes workers "
        f"at period {settings.MANAGER_REFRESH_PERIOD}s"
    )

    await update_finished_workers(db)
    await check_for_map_merge(db)

    new_tasks, new_pod_names = await create_worker_names_for_idle_tasks(db)
    new_workers = await worker_add_batch(new_pod_names, db)

    new_workers = await worker_get_batch([w.worker_id for w in new_workers], db)

    await task_update_worker_batch(
        [t.task_id for t in new_tasks],
        [w.worker_id for w in new_workers],
        db
    )

    job_ids = list({t.job_id for t in new_tasks})
    jobs = await job_get_batch(job_ids, db)
    job_map = {j.job_id: j for j in jobs}

    for task, worker in zip(new_tasks, new_workers):
        job = job_map.get(task.job_id)

        script = job.mapper_code if task.type == TaskType.MAP else job.reducer_code

        await create_worker_job(
            worker_id=worker.worker_id,
            pod_name=worker.pod_name,
            script_fpath=script,
            in_fpath=task.input_split,
            out_fpath=task.data_location,
            task_type=task.type,
        )

    await update_new_workers_and_tasks(new_workers, new_tasks, db)


# =========================================================
# STATUS UPDATES
# =========================================================

async def update_new_workers_and_tasks(
    workers: list[Worker],
    tasks: list[Task],
    db: AsyncSession,
):
    worker_result = await worker_update_status_batch(
        [w.worker_id for w in workers],
        WorkerStatus.ACTIVE,
        db,
    )

    task_result = await task_update_status_batch(
        [t.task_id for t in tasks],
        TaskStatus.IN_PROGRESS,
        db,
    )

    logger.info(
        f"[kubernetes_service.py]: workers ACTIVE {worker_result}/{len(workers)}, "
        f"tasks IN_PROGRESS {task_result}/{len(tasks)}"
    )


# =========================================================
# TASK CREATION
# =========================================================

async def create_worker_names_for_idle_tasks(
    db: AsyncSession
) -> tuple[list[Task], list[str]]:
    tasks = await task_get_all_idle(db)

    workers: list[str] = []
    new_tasks: list[Task] = []

    for task in tasks:
        workers.append(f"{task.task_id}-{task.type.value.lower()}")
        new_tasks.append(task)

    return new_tasks, workers


# =========================================================
# FINISHED WORKERS
# =========================================================

async def update_finished_workers(db: AsyncSession):
    successful_workers, failed_workers = await get_finished_workers()

    successful_tasks = await task_get_by_worker_batch(successful_workers, db)
    failed_tasks = await task_get_by_worker_batch(failed_workers, db)

    await worker_update_status_batch(
        successful_workers,
        WorkerStatus.IDLE,
        db
    )

    await task_update_status_batch(
        [t.task_id for t in successful_tasks],
        TaskStatus.COMPLETED,
        db
    )

    await worker_update_status_batch(
        failed_workers,
        WorkerStatus.FAILED,
        db
    )

    await task_update_status_batch(
        [t.task_id for t in failed_tasks],
        TaskStatus.FAILED,
        db
    )


async def get_finished_workers() -> tuple[list[str], list[str]]:
    try:
        batch_v1 = get_batch_client()

        jobs = await asyncio.to_thread(
            batch_v1.list_namespaced_job,
            namespace=settings.MANAGER_NAMESPACE,
        )

        successful: list[str] = []
        failed: list[str] = []

        for job in jobs.items:
            name = job.metadata.name

            if getattr(job.status, "succeeded", 0):
                successful.append(name.replace("worker-", "", 1))

            elif getattr(job.status, "failed", 0):
                failed.append(name.replace("worker-", "", 1))

        return successful, failed

    except Exception as ex:
        logger.warning(f"[kubernetes_service.py]: Exception occurred [{ex}]")
        return [], []


async def check_for_map_merge(db: AsyncSession):
    job_ids = await task_get_map_jobs(db)

    if not job_ids:
        return

    done_map = await task_are_maps_done_batch(job_ids, db)

    ready_job_ids = [jid for jid, done in done_map.items() if done]

    if not ready_job_ids:
        return

    jobs = await job_get_batch(ready_job_ids, db)

    if not jobs:
        return

    jobs = [job for job in jobs if job.status != JobStatus.COMPLETED]

    if not jobs:
        return

    map_tasks = await task_get_completed_map_tasks_by_jobs(ready_job_ids, db)

    if not map_tasks:
        return

    job_to_paths: dict[str, list[str]] = {}

    for task in map_tasks:
        if task.data_location:
            job_to_paths.setdefault(task.job_id, []).append(task.data_location)

    for job in jobs:
        try:
            map_paths = job_to_paths.get(job.job_id, [])

            if len(map_paths) != int(job.num_mappers):
                logger.warning(
                    f"[map-merge] skipping job={job.job_id} "
                    f"expected={job.num_mappers} found={len(map_paths)}"
                )
                continue

            existing_reduce_tasks = await task_get_reduce_by_job(job.job_id, db)

            if existing_reduce_tasks:
                reducer_done = all(t.status == TaskStatus.COMPLETED for t in existing_reduce_tasks)

                if reducer_done:
                    await finalize_job(job, existing_reduce_tasks, map_paths, db)

                continue

            part_paths = merge_and_partition_map(
                input_object=job.input_files,
                job_id=job.job_id,
                map_paths=map_paths,
                num_reducers=int(job.num_reducers),
            )

            if not part_paths:
                logger.warning(f"[map-merge] no partitions job={job.job_id}")
                continue

            reduce_output_paths = generate_reduce_output_paths(
                orig_path=job.input_files,
                job_id=job.job_id,
                num_reducers=int(job.num_reducers),
            )

            await task_add_batch(
                job_id=job.job_id,
                task_type=TaskType.REDUCE,
                input_splits=part_paths,
                data_locations=reduce_output_paths,
                db=db,
            )

            logger.info(
                f"[map-merge] created reducers job={job.job_id} "
                f"maps={len(map_paths)} reducers={len(reduce_output_paths)}"
            )

        except Exception as ex:
            logger.warning(f"[map-merge] failed job={job.job_id}: {ex}")


async def finalize_job(job: Job, tasks: list[Task], map_paths: list[str], db: AsyncSession):
    final_reduce_merge(
        job_id=job.job_id,
        reducer_outputs=[t.data_location for t in tasks],
        output_path=job.output_path,
    )

    reducer_outputs = [t.data_location for t in tasks if t.data_location]

    reducer_inputs = [t.input_split for t in tasks if t.input_split]

    cleanup_job_files(
        job_id=job.job_id,
        map_paths=map_paths,
        reduce_input_paths=reducer_inputs,
        reduce_output_paths=reducer_outputs
    )

    await job_update_status(job.job_id, JobStatus.COMPLETED, db)


# =========================================================
# LOG MONITORING
# =========================================================


async def monitor_running_workers():
    try:
        batch_v1 = get_batch_client()
        core_v1 = get_core_client()

        jobs = await asyncio.to_thread(
            batch_v1.list_namespaced_job,
            namespace=settings.MANAGER_NAMESPACE,
        )

        for job in jobs.items:
            job_name = job.metadata.name

            if getattr(job.status, "succeeded", 0) or getattr(job.status, "failed", 0):
                continue

            pods = await asyncio.to_thread(
                core_v1.list_namespaced_pod,
                namespace=settings.MANAGER_NAMESPACE,
                label_selector=f"job-name={job_name}",
            )

            for pod in pods.items:
                try:
                    logs = await asyncio.to_thread(
                        core_v1.read_namespaced_pod_log,
                        name=pod.metadata.name,
                        namespace=settings.MANAGER_NAMESPACE,
                        tail_lines=50,
                    )

                    logger.info(f"[k8s job={job_name} pod={pod.metadata.name}]\n{logs}")

                except Exception as log_ex:
                    logger.warning(
                        f"[kubernetes_service.py]: log fetch failed for {pod.metadata.name}: {log_ex}"
                    )

    except Exception as ex:
        logger.warning(f"[kubernetes_service.py]: Exception occurred [{ex}]")