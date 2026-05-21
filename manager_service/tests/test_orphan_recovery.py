"""Tests for orphaned-task recovery (assignment requirement 8).

Covers ``recover_orphaned_tasks`` in three shapes:
    1. K8s Job vanished → task resets to IDLE, worker row deleted
    2. K8s Job still alive → task untouched
    3. Two concurrent recovery loops → task ends up IDLE exactly once,
       worker deleted exactly once (no IntegrityError, no double-spawn)

Prereqs: ``docker compose up -d jobs_db minio`` — same as the other
integration tests in this directory.
"""
from types import SimpleNamespace
from unittest.mock import patch

import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.database import engine
from app.models.enums import JobStatus, TaskStatus, TaskType, WorkerStatus
from app.models.job import Job
from app.models.task import Task
from app.models.worker import Worker
from app.services.kubernetes_service import recover_orphaned_tasks


@pytest.fixture
def session_factory():
    return async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class _FakeBatchV1:
    """Stand-in for ``BatchV1Api`` returning a fixed alive-worker set.

    Each ``list_namespaced_job`` call returns Jobs named
    ``worker-{wid}`` for each ``wid`` passed in — matching the naming
    convention from ``create_worker_job``.
    """

    def __init__(self, alive_worker_ids: list[str]) -> None:
        self.alive_worker_ids = alive_worker_ids

    def list_namespaced_job(self, namespace: str) -> SimpleNamespace:
        return SimpleNamespace(items=[
            SimpleNamespace(metadata=SimpleNamespace(name=f"worker-{wid}"))
            for wid in self.alive_worker_ids
        ])


async def _seed_in_progress_task(session_factory) -> tuple[str, str]:
    """Create one job + one IN_PROGRESS task with a matching Worker row.

    Returns ``(task_id, worker_id)`` as plain strings.
    """
    async with session_factory() as setup:
        job = Job(
            user_id="1",
            status=JobStatus.SUBMITTED,
            input_files="in/file.txt",
            output_path="out/file.txt",
            mapper_code="mapper.py",
            reducer_code="reducer.py",
            num_mappers=1,
            num_reducers=1,
        )
        setup.add(job)
        await setup.commit()
        await setup.refresh(job)

        worker = Worker(
            pod_name=f"placeholder-{job.job_id}",
            status=WorkerStatus.ACTIVE,
        )
        setup.add(worker)
        await setup.commit()
        await setup.refresh(worker)

        task = Task(
            job_id=job.job_id,
            type=TaskType.MAP,
            status=TaskStatus.IN_PROGRESS,
            worker_pod_id=worker.worker_id,
            input_split="in/file_chunks/chunk_0.txt",
            data_location=f"{job.job_id}/map/map_0.txt",
        )
        setup.add(task)
        await setup.commit()
        await setup.refresh(task)

        return task.task_id, worker.worker_id


async def test_orphan_resets_to_idle_when_k8s_job_missing(session_factory) -> None:
    """K8s reports no Jobs at all → IN_PROGRESS task resets to IDLE.

    Asserts:
        - task.status flipped IDLE
        - task.worker_pod_id cleared (else the next worker_add_batch
          for the deterministic pod name fails with IntegrityError)
        - Worker row deleted (same reason — pod_name has unique=True)
    """
    task_id, worker_id = await _seed_in_progress_task(session_factory)

    with patch(
        "app.services.kubernetes_service.get_batch_client",
        return_value=_FakeBatchV1(alive_worker_ids=[]),
    ):
        async with session_factory() as db:
            await recover_orphaned_tasks(db)

    async with session_factory() as verify:
        task = (
            await verify.execute(select(Task).where(Task.task_id == task_id))
        ).scalar_one()
        worker = (
            await verify.execute(select(Worker).where(Worker.worker_id == worker_id))
        ).scalar_one_or_none()

    assert task.status == TaskStatus.IDLE, (
        f"expected task IDLE after recovery, got {task.status}"
    )
    assert task.worker_pod_id is None, (
        f"expected worker_pod_id cleared, got {task.worker_pod_id!r}"
    )
    assert worker is None, (
        "expected stale Worker row to be deleted — Worker.pod_name has "
        "unique=True, so leaving it would break the next worker_add_batch"
    )


async def test_alive_worker_is_untouched(session_factory) -> None:
    """K8s still reports the Job → recovery is a no-op for this task."""
    task_id, worker_id = await _seed_in_progress_task(session_factory)

    with patch(
        "app.services.kubernetes_service.get_batch_client",
        return_value=_FakeBatchV1(alive_worker_ids=[worker_id]),
    ):
        async with session_factory() as db:
            await recover_orphaned_tasks(db)

    async with session_factory() as verify:
        task = (
            await verify.execute(select(Task).where(Task.task_id == task_id))
        ).scalar_one()
        worker = (
            await verify.execute(select(Worker).where(Worker.worker_id == worker_id))
        ).scalar_one_or_none()

    assert task.status == TaskStatus.IN_PROGRESS, (
        f"expected task IN_PROGRESS (alive), got {task.status}"
    )
    assert task.worker_pod_id == worker_id, (
        "worker_pod_id should be unchanged when the K8s Job is alive"
    )
    assert worker is not None, "Worker row should not be deleted for an alive job"


async def test_concurrent_orphan_recovery_resets_once(session_factory) -> None:
    """Two concurrent recovery loops do not double-mutate or duplicate-delete.

    Without the per-task SELECT FOR UPDATE, both ticks would:
        - both see the task IN_PROGRESS in their pre-loop read,
        - both try to set IDLE (harmless), but
        - both try to DELETE the Worker row — the second would no-op
          (already gone), but if the order interleaves badly the second
          might race with worker_add_batch from a separate _schedule
          path and double-spawn.
    With the lock, the loser's in-lock status re-check fails and it
    bails before the DELETE.
    """
    task_id, worker_id = await _seed_in_progress_task(session_factory)

    async def one_tick() -> None:
        async with session_factory() as db:
            await recover_orphaned_tasks(db)

    with patch(
        "app.services.kubernetes_service.get_batch_client",
        return_value=_FakeBatchV1(alive_worker_ids=[]),
    ):
        await asyncio.gather(one_tick(), one_tick())

    async with session_factory() as verify:
        task = (
            await verify.execute(select(Task).where(Task.task_id == task_id))
        ).scalar_one()
        worker = (
            await verify.execute(select(Worker).where(Worker.worker_id == worker_id))
        ).scalar_one_or_none()

    assert task.status == TaskStatus.IDLE
    assert task.worker_pod_id is None
    assert worker is None
