"""Concurrency test for the MAP→REDUCE phase transition.

Two ``check_for_map_merge`` calls run in parallel on independent
``AsyncSession`` instances against the same Postgres row. Without
``SELECT FOR UPDATE`` they would both read "no reducers yet" and both
create REDUCE tasks → 2N rows. With the lock, exactly one winner
creates them; the loser sees the reducers on its in-lock re-read and
bails. We assert exactly N rows.

Postgres-side, ``SELECT FOR UPDATE`` enforces serialization regardless
of how asyncio interleaves the coroutines, so the test is a true
concurrency assertion even when the event loop happens to schedule the
two tasks sequentially.

Prereqs: ``docker compose up -d jobs_db minio`` — same as the other
integration tests in this directory.
"""
from unittest.mock import patch

import asyncio
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.database import engine
from app.models.enums import JobStatus, TaskStatus, TaskType
from app.models.job import Job
from app.models.task import Task
from app.services.kubernetes_service import check_for_map_merge


@pytest.fixture
def session_factory():
    """Independent ``AsyncSession`` factory bound to the production engine.

    Each ``Session()`` call gets its own DB connection from the pool, so
    two sessions held open simultaneously really do run in two Postgres
    transactions — required for the SELECT FOR UPDATE race to be real.
    """
    return async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def _seed_job_with_completed_maps(
    session_factory,
    num_mappers: int,
    num_reducers: int,
) -> tuple[str, int]:
    """Create one SUBMITTED job whose MAP tasks are all COMPLETED.

    That is the exact precondition ``check_for_map_merge`` looks for —
    all maps done, no reducers yet. The test then races two calls
    against this state.
    """
    async with session_factory() as setup:
        job = Job(
            user_id="1",
            status=JobStatus.SUBMITTED,
            input_files="in/file.txt",
            output_path="out/file.txt",
            mapper_code="mapper.py",
            reducer_code="reducer.py",
            num_mappers=num_mappers,
            num_reducers=num_reducers,
        )
        setup.add(job)
        await setup.commit()
        await setup.refresh(job)

        for idx in range(num_mappers):
            setup.add(Task(
                job_id=job.job_id,
                type=TaskType.MAP,
                status=TaskStatus.COMPLETED,
                input_split=f"in/file_chunks/chunk_{idx}.txt",
                data_location=f"{job.job_id}/map/map_{idx}.txt",
            ))
        await setup.commit()

        return job.job_id, num_reducers


async def test_concurrent_check_for_map_merge_creates_reducers_exactly_once(
    session_factory,
) -> None:
    """Two concurrent ticks must not double-create REDUCE tasks.

    Without SELECT FOR UPDATE on the Job row, both ticks' pre-lock reads
    see "no reducers yet" and both go on to insert N reducer tasks → 2N
    in the table. With the lock, one tick acquires the row first, runs
    the shuffle, inserts N tasks, and commits. The other tick blocks on
    the lock; when it acquires it the in-lock re-read sees the N tasks
    and the tick bails. End state: exactly N REDUCE rows.
    """
    num_mappers, num_reducers = 3, 4
    job_id, _ = await _seed_job_with_completed_maps(
        session_factory, num_mappers, num_reducers
    )

    # Stub MinIO I/O. The race we are testing is a DB race; we do not
    # want real shuffle output muddying it.
    fake_part_paths = [f"{job_id}/part/part_{i}.txt" for i in range(num_reducers)]

    async def one_tick() -> None:
        async with session_factory() as db:
            await check_for_map_merge(db)

    with patch(
        "app.services.kubernetes_service.merge_and_partition_map",
        return_value=fake_part_paths,
    ):
        await asyncio.gather(one_tick(), one_tick())

    async with session_factory() as verify:
        rows = (
            await verify.execute(
                select(Task)
                .where(Task.job_id == job_id)
                .where(Task.type == TaskType.REDUCE)
            )
        ).scalars().all()

    assert len(rows) == num_reducers, (
        f"expected exactly {num_reducers} REDUCE tasks after the race, "
        f"got {len(rows)} — the SELECT FOR UPDATE guard did not hold"
    )
