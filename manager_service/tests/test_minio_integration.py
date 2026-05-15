"""Integration tests for the MinIO bucket lifecycle helper.

Require a running MinIO (``docker compose up -d minio``). For portable
unit tests with no infrastructure dependency, see ``test_minio.py``.
"""
import uuid

from app.services.minio_service import client as minio_client, ensure_bucket


def test_ensure_bucket_creates_when_missing_real() -> None:
    """``ensure_bucket`` creates a bucket against real MinIO when it doesn't exist."""
    name = f"test-ensure-{uuid.uuid4().hex[:12]}"
    assert not minio_client.bucket_exists(name)
    try:
        ensure_bucket(name)
        assert minio_client.bucket_exists(name)
    finally:
        if minio_client.bucket_exists(name):
            minio_client.remove_bucket(name)


def test_ensure_bucket_is_idempotent_real() -> None:
    """A second ``ensure_bucket`` call against real MinIO is a no-op."""
    name = f"test-ensure-{uuid.uuid4().hex[:12]}"
    try:
        ensure_bucket(name)
        ensure_bucket(name)  # must not raise
        assert minio_client.bucket_exists(name)
    finally:
        if minio_client.bucket_exists(name):
            minio_client.remove_bucket(name)
