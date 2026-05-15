"""Pytest fixtures for manager_service integration tests.

Prereqs to run locally:
    docker compose up -d jobs_db minio
    cd manager_service
    pip install -r requirements-dev.txt
    pytest

Isolation strategy:
    - DB: each test runs inside a transaction that rolls back at teardown.
    - MinIO: tests that need object storage opt into a per-test uniquely-named bucket.
    - K8s: a FakeBatchV1 records ``create_namespaced_job`` calls; no real cluster needed.
"""
import os

# Set env vars BEFORE any ``from app.*`` import — app.core.settings reads
# os.environ at module load and crashes on missing required keys. Defaults
# match docker-compose's ${JOBS_DB_*} mappings; setdefault lets the caller win.
os.environ.setdefault("POSTGRES_USER", "jobs_user")
os.environ.setdefault("POSTGRES_PASSWORD", "password")
os.environ.setdefault("POSTGRES_DB", "jobs_db")
os.environ.setdefault("POSTGRES_SERVER", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5433")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_BUCKET", "jobs")
os.environ.setdefault("MINIO_ACCESS_KEY", "minio")
os.environ.setdefault("MINIO_SECRET_KEY", "password")
os.environ.setdefault("MANAGER_NAMESPACE", "mapreduce-test")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-not-for-prod")

import uuid
from types import SimpleNamespace
from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base, engine, get_db
from app.kubernetes_client import get_batch_client
from app.main import app
from app.services.minio_service import client as minio_client


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> None:
    """Ensure all tables exist on the test DB once per session."""
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def db_session() -> Iterator[Session]:
    """Per-test SQLAlchemy session inside a transaction that rolls back on teardown.

    API writes are visible to the test through the dependency override and gone
    after the fixture completes.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=connection)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


class FakeBatchV1:
    """In-memory stand-in for ``kubernetes.client.BatchV1Api``.

    Records ``create_namespaced_job`` calls so tests can assert the manager
    asked K8s to spawn the right Jobs, without touching a real cluster.
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


@pytest.fixture
def client(db_session: Session, fake_k8s: FakeBatchV1) -> Iterator[TestClient]:
    """FastAPI TestClient with DB and K8s dependencies overridden.

    Deliberately skips ``with TestClient(app)`` so the lifespan-managed
    ``monitor_workers`` polling loop never starts during tests.
    """
    def _override_db() -> Iterator[Session]:
        yield db_session

    def _override_batch() -> FakeBatchV1:
        return fake_k8s

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_batch_client] = _override_batch
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
