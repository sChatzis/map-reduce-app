"""Unit tests for ``is_valid_path``.

Pure-function tests — no MinIO, no DB, no fixtures.
"""
import pytest

from app.utils.utility import is_valid_path


@pytest.mark.parametrize(
    "key",
    [
        "in/file.txt",
        "jobs/abc-def-123/chunks/chunk_0.txt",
        "a",
        "a/b/c",
        "_under.scored-key",
        "1234567890/file",
        "in/file_chunks/file_chunk_0.txt",  # shape produced by split_input_file_to_chunks
    ],
)
def test_is_valid_path_accepts_valid_keys(key: str) -> None:
    """Well-formed relative MinIO keys are accepted."""
    assert is_valid_path(key) is True


@pytest.mark.parametrize(
    "key,reason",
    [
        ("", "empty"),
        ("with\0null", "NUL byte"),
        ("/leading-slash", "leading slash"),
        ("../escape", "traversal segment at start"),
        ("in/../etc/passwd", "traversal segment in middle"),
        ("a//b", "empty segment"),
        ("a/b/", "trailing slash gives empty segment"),
        ("has space.txt", "space is not allowed"),
        ("weird$char", "$ is not allowed"),
        ("αβγ.txt", "non-ASCII is not allowed"),
    ],
)
def test_is_valid_path_rejects_invalid_keys(key: str, reason: str) -> None:
    """Empty, traversal, leading-slash, and disallowed-char keys are rejected."""
    assert is_valid_path(key) is False, f"expected rejection: {reason}"
