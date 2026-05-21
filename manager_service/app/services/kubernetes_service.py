from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.database import AsyncSessionLocal
from app.models.enums import *
from app.models.job import Job
from app.models.task import Task
from app.models.worker import Worker
from app.services.job_service import job_get_batch
from app.services.task_service import (
    task_get_all_idle,
    task_get_in_progress,
    task_are_maps_done_batch,
    task_update_status_batch,
    task_update_worker_batch,
    task_get_by_worker_batch, task_get_map_jobs, task_get_completed_map_tasks_by_jobs,
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
    await recover_orphaned_tasks(db)
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


# =========================================================
# ORPHAN RECOVERY
# =========================================================

async def _list_alive_worker_ids() -> set[str] | None:
    """Return the worker_ids of every K8s Job currently in the namespace.

    Strips the ``worker-`` prefix so the returned set is directly
    comparable to ``Task.worker_pod_id`` / ``Worker.worker_id`` — same
    convention used in ``get_finished_workers``.

    Returns ``None`` to signal "K8s unreachable" so callers don't treat
    an empty list as "all workers gone" and reset every IN_PROGRESS
    task on a transient network blip.
    """
    try:
        batch_v1 = get_batch_client()
        jobs = await asyncio.to_thread(
            batch_v1.list_namespaced_job,
            namespace=settings.MANAGER_NAMESPACE,
        )
        return {j.metadata.name.replace("worker-", "", 1) for j in jobs.items}

    except Exception as ex:
        logger.warning(f"[orphan-recovery] failed to list jobs: {ex}")
        return None


async def recover_orphaned_tasks(db: AsyncSession):
    """Reset tasks whose K8s Job has vanished (kubectl delete, TTL, node loss).

    Workers are output-idempotent — same task_id/data_location produces
    the same output, so respawning is safe. We reset to IDLE and clear
    ``worker_pod_id``; ``_schedule`` re-spawns on the next tick.

    Per-task SELECT FOR UPDATE serializes the reset across manager
    replicas — same pattern as the MAP→REDUCE guard in
    ``check_for_map_merge``. The loser bails on the in-lock status
    re-check.

    Worker row deletion happens inside the same locked tx as the task
    reset: ``Worker.pod_name`` is ``unique=True`` and worker pod names
    are deterministic (``{task_id}-{type}``), so without deleting the
    stale row the next tick's ``worker_add_batch`` would throw
    ``IntegrityError`` when respawning under the same pod name.
    """
    alive_worker_ids = await _list_alive_worker_ids()

    if alive_worker_ids is None:
        return

    in_progress_tasks = await task_get_in_progress(db)

    # Snapshot ``(task_id, worker_pod_id)`` as plain strings. Iterating
    # ORM objects across a per-task rollback (inside the locked block,
    # on exception) would fault — see the same pattern in
    # ``check_for_map_merge``.
    candidates = [
        (t.task_id, t.worker_pod_id)
        for t in in_progress_tasks
        if t.worker_pod_id and t.worker_pod_id not in alive_worker_ids
    ]

    # End the read tx so per-task ``Session.begin()`` blocks can each
    # open their own. Commit (not rollback) because there's nothing to
    # undo.
    await db.commit()

    for task_id, _ in candidates:
        try:
            async with db.begin():
                locked = (
                    await db.execute(
                        select(Task)
                        .where(Task.task_id == task_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()

                if locked is None or locked.status != TaskStatus.IN_PROGRESS:
                    continue

                # Use the row's CURRENT worker_pod_id, not the snapshot
                # — another replica may have re-assigned the task to a
                # fresh worker between snapshot and lock acquisition. If
                # that fresh worker_id is in our alive set, the task is
                # no longer orphaned and we leave it alone.
                stale_worker_id = locked.worker_pod_id

                if stale_worker_id is None or stale_worker_id in alive_worker_ids:
                    continue

                # Clear the FK from Task → Worker before deleting the
                # Worker row, otherwise the DELETE violates the FK
                # constraint. ``autoflush=False`` on the session means
                # the pending UPDATE isn't auto-pushed before the
                # next ``db.execute``, so flush explicitly.
                locked.worker_pod_id = None
                locked.status = TaskStatus.IDLE
                await db.flush()

                # Inline ``delete`` — NOT ``worker_delete_batch``, which
                # commits internally and would release the row lock
                # mid-transition.
                await db.execute(
                    delete(Worker).where(Worker.worker_id == stale_worker_id)
                )

                logger.info(
                    f"[orphan-recovery] reset task={task_id} type={locked.type} "
                    f"worker={stale_worker_id} (k8s job gone)"
                )

        except Exception as ex:
            logger.warning(f"[orphan-recovery] failed task={task_id}: {ex}")


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

    # Snapshot job IDs as plain strings before closing the read tx. Any
    # later expiry (commit clears the tx but doesn't expire when
    # ``expire_on_commit=False``; rollback inside a per-job locked block
    # on exception WILL expire all attributes regardless) cannot fault
    # plain strings.
    job_ids_to_process = [j.job_id for j in jobs]

    # End the read tx so per-job ``Session.begin()`` blocks can each
    # open their own — ``Session.begin()`` raises if a tx is in progress.
    # Commit (not rollback) because there's nothing to undo; the pre-loop
    # reads did no writes.
    await db.commit()

    for job_id in job_ids_to_process:
        try:
            # SELECT FOR UPDATE on the Job row serializes the
            # read-decide-write across manager replicas. Both
            # MAP→REDUCE (shuffle + create reducers) and
            # REDUCE→COMPLETED (final merge + status flip) run
            # under the same lock; the pre-loop reads above are
            # only a fast path, the in-lock re-reads are what the
            # race guard rests on.
            #
            # Note: ``merge_and_partition_map`` and
            # ``final_reduce_merge`` do MinIO I/O while the row lock
            # is held. At our scale this is acceptable; a production
            # system would stage outside the lock and only do DB
            # writes inside it.
            async with db.begin():
                locked_job = (
                    await db.execute(
                        select(Job)
                        .where(Job.job_id == job_id)
                        .with_for_update()
                    )
                ).scalar_one_or_none()

                if locked_job is None or locked_job.status == JobStatus.COMPLETED:
                    continue

                map_paths = job_to_paths.get(locked_job.job_id, [])

                if len(map_paths) != int(locked_job.num_mappers):
                    logger.warning(
                        f"[map-merge] skipping job={locked_job.job_id} "
                        f"expected={locked_job.num_mappers} found={len(map_paths)}"
                    )
                    continue

                reduce_tasks = list((
                    await db.execute(
                        select(Task)
                        .where(Task.job_id == locked_job.job_id)
                        .where(Task.type == TaskType.REDUCE)
                        .order_by(Task.task_id)
                    )
                ).scalars().all())

                if reduce_tasks:
                    if all(t.status == TaskStatus.COMPLETED for t in reduce_tasks):
                        finalize_job(locked_job, reduce_tasks, map_paths)
                        locked_job.status = JobStatus.COMPLETED
                    continue

                part_paths = merge_and_partition_map(
                    input_object=locked_job.input_files,
                    job_id=locked_job.job_id,
                    map_paths=map_paths,
                    num_reducers=int(locked_job.num_reducers),
                )

                if not part_paths:
                    logger.warning(f"[map-merge] no partitions job={locked_job.job_id}")
                    continue

                reduce_output_paths = generate_reduce_output_paths(
                    orig_path=locked_job.input_files,
                    job_id=locked_job.job_id,
                    num_reducers=int(locked_job.num_reducers),
                )

                # Invariant previously enforced inside ``task_add_batch`` —
                # inlining the writes (to keep them under the row lock) drops
                # that check, so reassert it here.
                assert len(part_paths) == len(reduce_output_paths), (
                    f"shuffle/output-path length mismatch for job={locked_job.job_id}: "
                    f"{len(part_paths)} != {len(reduce_output_paths)}"
                )

                # Inline ``db.add`` — NOT ``task_add_batch``, which commits
                # internally and would release the FOR UPDATE lock mid-
                # transition. The outer ``async with db.begin()`` block
                # commits everything atomically on exit.
                for input_split, data_location in zip(part_paths, reduce_output_paths):
                    db.add(Task(
                        job_id=locked_job.job_id,
                        type=TaskType.REDUCE,
                        status=TaskStatus.IDLE,
                        input_split=input_split,
                        data_location=data_location,
                    ))

                logger.info(
                    f"[map-merge] created reducers job={locked_job.job_id} "
                    f"maps={len(map_paths)} reducers={len(reduce_output_paths)}"
                )

        except Exception as ex:
            logger.warning(f"[map-merge] failed job={job_id}: {ex}")


def finalize_job(job: Job, tasks: list[Task], map_paths: list[str]) -> None:
    """MinIO I/O for job completion. Caller commits ``job.status``.

    Separated from the DB write so it can run inside a SELECT FOR UPDATE
    block — ``job_update_status`` commits internally and would release
    the row lock, defeating the race guard.
    """
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
        reduce_output_paths=reducer_outputs,
    )


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