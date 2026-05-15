"""Unit tests for ``ensure_bucket`` — verify branching with a mocked client.

These tests run without any running MinIO. The companion file
``test_minio_integration.py`` covers the same function against a real bucket.
"""
from unittest.mock import MagicMock, patch

from app.services.minio_service import ensure_bucket


@patch("app.services.minio_service.client")
def test_ensure_bucket_skips_when_exists(mock_client: MagicMock) -> None:
    """When ``bucket_exists`` returns True, ``make_bucket`` is not called."""
    mock_client.bucket_exists.return_value = True

    ensure_bucket("my-bucket")

    mock_client.bucket_exists.assert_called_once_with("my-bucket")
    mock_client.make_bucket.assert_not_called()


@patch("app.services.minio_service.client")
def test_ensure_bucket_creates_when_missing(mock_client: MagicMock) -> None:
    """When ``bucket_exists`` returns False, ``make_bucket`` is called once with the name."""
    mock_client.bucket_exists.return_value = False

    ensure_bucket("my-bucket")

    mock_client.bucket_exists.assert_called_once_with("my-bucket")
    mock_client.make_bucket.assert_called_once_with("my-bucket")
