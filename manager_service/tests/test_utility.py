"""Unit tests for pure functions in ``app.utils.utility``.

No MinIO, no DB, no fixtures. The cross-process hash-seed test launches
subprocesses but stays self-contained — no external services.
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.utils.utility import is_valid_path, partition_for_key


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


@pytest.mark.parametrize(
    "key, num_reducers",
    [
        ("foo", 4),
        ("bar", 4),
        ("baz", 4),
        ("foo", 1),
        ("", 4),
        ("ünïcödé", 4),
        ("a_long_key_with_underscores_and-dashes", 8),
    ],
)
def test_partition_for_key_matches_md5_formula(key: str, num_reducers: int) -> None:
    """``partition_for_key`` is exactly ``md5(key.utf8) mod num_reducers``.

    Expected value is the spelled-out formula rather than a magic int, so
    this test checks the function against the spec — not against itself. A
    breaking change (e.g. reverting to ``hash()``, or switching to sha256)
    will fail this test and force the wire-format change to be explicit.
    """
    expected = int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % num_reducers
    assert partition_for_key(key, num_reducers) == expected


_MANAGER_DIR = Path(__file__).resolve().parent.parent


def _partition_in_subprocess(key: str, num_reducers: int, hashseed: str) -> int:
    """Run ``partition_for_key`` in a fresh interpreter with ``PYTHONHASHSEED=<hashseed>``."""
    code = (
        "from app.utils.utility import partition_for_key; "
        f"print(partition_for_key({key!r}, {num_reducers}))"
    )
    env = {**os.environ, "PYTHONHASHSEED": hashseed}
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_MANAGER_DIR),
        check=False,
    )
    assert result.returncode == 0, (
        f"subprocess failed (PYTHONHASHSEED={hashseed}):\n"
        f"stdout: {result.stdout!r}\nstderr: {result.stderr!r}"
    )
    return int(result.stdout.strip())


def test_partition_is_stable_across_python_hash_seeds() -> None:
    """``PYTHONHASHSEED`` must not change the partition.

    Python's built-in ``hash(str)`` is salted per-process via this env var
    (PEP 456). Running the partition in subprocesses with different seeds
    is the test that actually proves we are not using ``hash()`` — a pure
    in-process parametrize table would silently pass even if the function
    reverted to randomized hashing.

    Seeds: ``0`` and ``1`` are deterministic per-spec; ``random`` is the
    live randomized seed. All three must agree.
    """
    key = "stability-canary"
    num_reducers = 8
    results = [
        _partition_in_subprocess(key, num_reducers, seed)
        for seed in ("0", "1", "random")
    ]
    assert len(set(results)) == 1, (
        f"partitions differ across PYTHONHASHSEEDs: {results}"
    )
