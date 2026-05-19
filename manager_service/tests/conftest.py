"""Pytest fixtures for manager_service integration tests.

Prereqs to run locally:
    docker compose up -d jobs_db minio
    cd manager_service
    pip install -r requirements-dev.txt
    pytest

Isolation strategy:
    - DB: each test gets a plain ``AsyncSession`` bound to the engine.
      Isolation comes from a function-scoped autouse fixture that issues
      ``TRUNCATE jobs, tasks, workers RESTART IDENTITY CASCADE`` before
      every test, so service-layer commits are real commits that the
      next test cannot see.
    - MinIO: tests that need object storage opt into a per-test uniquely-named
      bucket.
    - K8s: a FakeBatchV1 records ``create_namespaced_job`` calls; no real
      cluster needed. Note: code paths that call ``_get_batch_client()``
      directly bypass the FastAPI dep override; the override only catches
      callers that take ``BatchV1Api`` via ``Depends(get_batch_client)``.
"""
import os

# Set env vars BEFORE any ``from app.*`` import — app.core.settings reads
# os.environ at module load and raises on missing required keys. Names
# match what settings.py reads (post env-var rename), plus the two new
# required keys introduced in the upstream async commit.
os.environ.setdefault("JOBS_DB_USER", "jobs_user")
os.environ.setdefault("JOBS_DB_PASSWORD", "password")
os.environ.setdefault("JOBS_DB_NAME", "jobs_db")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_BUCKET", "jobs")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "password")
os.environ.setdefault("MANAGER_NAMESPACE", "mapreduce-test")
os.environ.setdefault("MANAGER_WORKER_IMAGE_NAME", "map-reduce-app-manager_worker:latest")
os.environ.setdefault("MANAGER_REFRESH_PERIOD", "10")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-prod")

import uuid
from types import SimpleNamespace
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.database import Base, engine, get_db
from app.kubernetes_client import get_batch_client
from app.main import app
from app.services.minio_service import client as minio_client


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_schema() -> AsyncIterator[None]:
    """Create all tables once per session against the async engine."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _truncate_tables() -> AsyncIterator[None]:
    """Wipe jobs/tasks/workers before every test for per-test isolation.

    Issued via ``engine.begin()`` (its own short-lived transaction) so it
    does not contend with the test's session for table locks. ``CASCADE``
    handles foreign-key references; ``RESTART IDENTITY`` is a no-op for
    our UUID-keyed tables but harmless.
    """
    async with engine.begin() as conn:
        await conn.execute(
            text("TRUNCATE TABLE jobs, tasks, workers RESTART IDENTITY CASCADE")
        )
    yield


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """Per-test ``AsyncSession`` bound to the production engine.

    No outer transaction, no SAVEPOINT — service-layer ``await db.commit()``
    is a real commit. Per-test isolation comes from ``_truncate_tables``,
    not from a held-open transaction.
    """
    AsyncTestSession = async_sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )
    session = AsyncTestSession()
    try:
        yield session
    finally:
        await session.close()


class FakeBatchV1:
    """In-memory stand-in for ``kubernetes.client.BatchV1Api``.

    Records ``create_namespaced_job`` calls so tests can assert the manager
    asked K8s to spawn the right Jobs, without touching a real cluster.

    The manager wraps its sync K8s calls in ``asyncio.to_thread(...)``, so
    these methods stay sync — they are invoked from a worker thread.
    """

    def __init__(self) -> None:
        self.created_jobs: list[tuple[str, object]] = []
        self.listed_jobs: list[object] = []

    def create_namespaced_job(self, namespace: str, body: object) -> object:
        self.created_jobs.append((namespace, body))
        return body

    def list_namespaced_job(self, namespace: str) -> SimpleNamespace:
        return SimpleNamespace(items=list(self.listed_jobs))


@pytest.fixture
def fake_k8s() -> FakeBatchV1:
    """Fresh FakeBatchV1 per test."""
    return FakeBatchV1()


@pytest.fixture
def minio_test_bucket() -> Iterator[str]:
    """Uniquely-named MinIO bucket for the test, removed at teardown.

    Opt in only when a test actually uploads/downloads objects; the smoke
    tests do not need it.
    """
    bucket = f"test-{uuid.uuid4().hex[:12]}"
    minio_client.make_bucket(bucket)
    try:
        yield bucket
    finally:
        for obj in minio_client.list_objects(bucket, recursive=True):
            minio_client.remove_object(bucket, obj.object_name)
        minio_client.remove_bucket(bucket)


@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    fake_k8s: FakeBatchV1,
) -> AsyncIterator[AsyncClient]:
    """httpx.AsyncClient over an ASGITransport — DB and K8s deps overridden.

    Using ``ASGITransport`` skips the network and does not run the FastAPI
    lifespan, so the ``safe_monitor_workers`` background task never starts
    during tests.
    """
    async def _override_db() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _override_batch() -> FakeBatchV1:
        return fake_k8s

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_batch_client] = _override_batch
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as http_client:
            yield http_client
    finally:
        app.dependency_overrides.clear()
