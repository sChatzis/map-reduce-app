from collections import Counter, defaultdict


from app.core.settings import settings
from app.services.minio_service import (
    write_text_to_file,
    read_file_as_text,
    delete_files
)


import os
import re
import math
import hashlib
import logging
import uuid


_KEY_CHARS = re.compile(r"^[A-Za-z0-9/_\-\.]+$")
_CLEAN = re.compile(r"[^a-z0-9]+")

logger = logging.getLogger(__name__)


def is_valid_uuid(value: str) -> bool:
    try:
        return uuid.UUID(value).version == 4
    except ValueError:
        return False


def is_valid_path(path: str) -> bool:
    """Validate a MinIO object key.

    Rules:
        - non-empty
        - no NUL byte
        - no leading ``/`` — MinIO / ``boto3`` / ``minio-py`` treat leading
          slashes inconsistently (some normalize, some keep them as literal
          first byte), so we reject them up front
        - no ``..`` segments (prevents traversal-style keys)
        - no empty segments (rejects ``a//b`` and trailing slashes)
        - characters limited to ``[A-Za-z0-9/_\\-.]``

    The previous POSIX absolute-path requirement has been dropped — MinIO
    keys are not filesystem paths.
    """
    if not path or "\0" in path:
        return False

    if path.startswith("/"):
        return False

    if any(seg in ("", "..") for seg in path.split("/")):
        return False

    return bool(_KEY_CHARS.match(path))


def partition_for_key(key: str, num_reducers: int) -> int:
    """Stable partition: same ``key`` → same reducer across processes and runs.

    Uses md5 — not Python's ``hash()``, which is salted per-process via
    PYTHONHASHSEED (PEP 456) and so would re-shuffle keys on a manager
    restart, breaking the MapReduce partition invariant. Not a security
    boundary; we just need a deterministic 128-bit spread.
    """
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % num_reducers


def generate_map_output_paths(input_path: str, job_id: int, num_chunks: int) -> list[str]:
    if num_chunks <= 0:
        return []

    base, ext = os.path.splitext(input_path)

    if num_chunks == 1:
        return [f"{job_id}/map/{job_id}_map{ext}"]

    return [
        f"{job_id}/map/{job_id}_map_{idx}{ext}"
        for idx in range(num_chunks)
    ]


def generate_reduce_input_paths(orig_path: str, job_id: int, num_reducers: int) -> list[str]:
    if num_reducers <= 0:
        return []

    base, ext = os.path.splitext(orig_path)

    if num_reducers == 1:
        return [f"{job_id}/part/{job_id}_part{ext}"]

    return [
        f"{job_id}/part/{job_id}_part_{idx}{ext}"
        for idx in range(num_reducers)
    ]


def generate_reduce_output_paths(orig_path: str, job_id: int, num_reducers: int) -> list[str]:
    if num_reducers <= 0:
        return []

    base, ext = os.path.splitext(orig_path)

    if num_reducers == 1:
        return [f"{job_id}/reduce/{job_id}_reduce{ext}"]

    return [
        f"{job_id}/reduce/{job_id}_reduce_{idx}{ext}"
        for idx in range(num_reducers)
    ]


def split_input_file_to_chunks(
    input_object: str,
    job_id: str,
    num_chunks: int,
) -> list[str]:
    """Split a text input into up to ``num_chunks`` line-aligned chunks in MinIO.

    Splits at line boundaries (not bytes) so per-record formats like word
    count cannot be bisected mid-record — OSDI'04 §4.4 requires input splits
    that respect record boundaries.

    If the input has fewer non-empty lines than ``num_chunks``, returns one
    chunk per line (so the returned list can be shorter than ``num_chunks``).
    Callers must use ``len(returned)`` rather than ``num_chunks`` for any
    downstream sizing (see ``add_job`` in the jobs endpoint).
    """
    if num_chunks <= 0:
        return []

    lines = read_file_as_text(input_object).splitlines()

    lines = [line for line in lines if line.strip()]

    if not lines:
        return []

    _, ext = os.path.splitext(input_object)

    if num_chunks == 1:
        chunk_path = f"{job_id}/chunks/{job_id}_chunk{ext}"
        chunk_data = ("\n".join(lines) + "\n").encode("utf-8")

        write_text_to_file(chunk_path, chunk_data)

        logger.info(f"\n[split_input_file_to_chunks] uploaded single chunk {chunk_path}")

        return [chunk_path]

    chunk_size = math.ceil(len(lines) / num_chunks)
    chunks = [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)]

    chunk_paths: list[str] = []

    for idx, chunk in enumerate(chunks):
        chunk_data = ("\n".join(chunk) + "\n").encode("utf-8")
        chunk_path = f"{job_id}/chunks/{job_id}_chunk_{idx}{ext}"

        write_text_to_file(chunk_path, chunk_data)

        chunk_paths.append(chunk_path)

        logger.info(
            f"\n[split_input_file_to_chunks] uploaded chunk {idx} of {len(chunk)} lines {chunk_path}"
        )

    return chunk_paths


def merge_and_partition_map(
    input_object: str,
    job_id: str,
    map_paths: list[str],
    num_reducers: int
) -> list[str]:
    if not map_paths or num_reducers <= 0:
        return []

    parts = [[] for _ in range(num_reducers)]

    for path in map_paths:
        try:
            lines = read_file_as_text(path).splitlines()

            for line in lines:
                line = line.strip()

                if "\t" not in line:
                    continue

                key, value = line.split("\t", 1)

                if not key or not value:
                    continue

                reducer_idx = partition_for_key(key, num_reducers)
                parts[reducer_idx].append((key, value))

        except Exception as ex:
            logger.warning(f"\n[merge_and_partition_map] failed to read\n{path} {ex}\n")

    for part in parts:
        part.sort(key=lambda x: x[0])

    base, ext = os.path.splitext(input_object)

    if num_reducers == 1:
        all_pairs = parts[0]

        part_data = ("\n".join(f"{k}\t{v}" for k, v in all_pairs) + "\n").encode("utf-8")
        part_path = f"{job_id}/part/{job_id}_part{ext}"

        write_text_to_file(part_path, part_data)

        logger.info(f"\n[merge_and_partition_map] uploaded part 0 with {len(all_pairs)} pairs\n{job_id}/part/{job_id}_part{ext}\n")

        return [part_path]

    part_paths = []

    for idx, part in enumerate(parts):
        part_data = ("\n".join(f"{k}\t{v}" for k, v in part) + "\n").encode("utf-8")
        part_path = f"{job_id}/part/{job_id}_part_{idx}{ext}"

        write_text_to_file(part_path, part_data)

        part_paths.append(part_path)

        logger.info(f"\n[merge_and_partition_map] uploaded part {idx} with {len(part)} pairs\n{job_id}/part/{job_id}_part_{idx}{ext}\n")

    return part_paths

def final_reduce_merge(job_id: str, reducer_outputs: list[str], output_path: str):
    if not reducer_outputs:
        logger.warning(f"\n[final_reduce_merge] no reducer outputs for job {job_id}\n")
        return

    merged_lines = []

    for path in reducer_outputs:
        try:
            data = read_file_as_text(path)

            merged_lines.extend(data.splitlines())

        except Exception as ex:
            logger.warning(f"\n[final_reduce_merge] failed reading {path} {ex}\n")

    merged_lines.sort()

    final_data = ("\n".join(merged_lines) + "\n").encode("utf-8")
    write_text_to_file(output_path, final_data)

    logger.info(f"\n[final_reduce_merge] created final output {output_path}\n")


def cleanup_job_files(
    chunk_paths: list[str],
    map_paths: list[str],
    reduce_input_paths: list[str],
    reduce_output_paths: list[str],
) -> None:
    files: list[str] = []

    if chunk_paths:
        files.extend(chunk_paths)

    if map_paths:
        files.extend(map_paths)

    if reduce_input_paths:
        files.extend(reduce_input_paths)

    if reduce_output_paths:
        files.extend(reduce_output_paths)

    if not files:
        logger.info(f"\n[cleanup_job_files] nothing to delete\n")
        return

    try:
        delete_files(files)
        logger.info(f"\n[cleanup_job_files] deleted {len(files)} files\n")

    except Exception as ex:
        logger.warning(f"\n[cleanup_job_files] cleanup failed {ex}\n")


#
# For debugging only
#


def validate_map_outputs(chunk_paths: list[str], map_output_paths: list[str]):
    expected = []

    for chunk_path in chunk_paths:
        text = read_file_as_text(chunk_path)

        for line in text.splitlines():
            for word in line.strip().split():
                cleaned = _CLEAN.sub("", word.lower())

                if cleaned:
                    expected.append(f"{cleaned}\t1")

    actual = []

    for map_path in map_output_paths:
        text = read_file_as_text(map_path)

        actual.extend([
            l.strip()
            for l in text.splitlines()
            if l.strip()
               and "\t" in l
               and l.split("\t", 1)[1]
        ])

    expected_counts = Counter(expected)
    actual_counts = Counter(actual)

    if expected_counts == actual_counts:
        logger.info(f"\n[validate_map_outputs] all mapper outputs valid {len(actual)} pairs across {len(map_output_paths)} chunks\n")
    else:
        logger.info(f"\n[validate_map_outputs] mismatch expected {len(expected)} pairs but got {len(actual)}\n")

        missing = set(expected_counts) - set(actual_counts)
        extra = set(actual_counts) - set(expected_counts)

        if missing:
            logger.info(f" missing {list(missing)[:5]}")

        if extra:
            logger.info(f" extra {list(extra)[:5]}")


def validate_partition(map_paths: list[str], part_paths: list[str], num_reducers: int):
    expected_pairs = []

    for path in map_paths:
        text = read_file_as_text(path)

        for line in text.splitlines():
            line = line.strip()

            if "\t" not in line:
                continue

            key, value = line.split("\t", 1)
            expected_pairs.append((key, value))

    actual_pairs = []
    routing_errors = []

    for idx, path in enumerate(part_paths):
        text = read_file_as_text(path)

        for line in text.splitlines():
            line = line.strip()

            if "\t" not in line:
                continue

            key, value = line.split("\t", 1)
            actual_pairs.append((key, value))

            expected_idx = partition_for_key(key, num_reducers)

            if expected_idx != idx:
                routing_errors.append(
                    f"\n[validate_partition] key {key!r} "
                    f"in part {idx} but hash routes to {expected_idx}\n"
                )

    expected_counts = Counter(expected_pairs)
    actual_counts = Counter(actual_pairs)

    if routing_errors:
        logger.info(f"\n[validate_partition] {len(routing_errors)} routing errors\n")

        for error in routing_errors[:5]:
            logger.info(f"{error}")

    if expected_counts == actual_counts and not routing_errors:
        logger.info(f"\n[validate_partition] partition valid "
                    f"{len(actual_pairs)} pairs across {len(part_paths)} partitions\n")
    else:
        missing = set(expected_counts) - set(actual_counts)
        extra = set(actual_counts) - set(expected_counts)

        logger.info(
            f"\n[validate_partition] partition mismatch expected "
            f"{len(expected_pairs)} pairs but got {len(actual_pairs)}\n"
        )

        if missing:
            logger.info(f" missing {list(missing)[:5]}\n")

        if extra:
            logger.info(f" extra {list(extra)[:5]}\n")


def validate_reducers(part_paths: list[str], reducer_output_paths: list[str]):
    for part_path, output_path in zip(part_paths, reducer_output_paths):
        text = read_file_as_text(part_path)

        expected = defaultdict(int)

        for line in text.splitlines():
            line = line.strip()

            if "\t" not in line:
                continue

            key, value = line.split("\t", 1)
            expected[key] += int(value)

        text = read_file_as_text(output_path)

        actual = {}

        for line in text.splitlines():
            line = line.strip()

            if "\t" not in line:
                continue

            key, value = line.split("\t", 1)
            actual[key] = int(value)

        if dict(expected) == actual:
            logger.info(
                f"\n[validate_reducers] reducer valid\n"
                f"{output_path}\n"
                f"{len(actual)} unique keys\n"
            )
        else:
            mismatched = {k for k in expected if k in actual and expected[k] != actual[k]}
            missing = set(expected) - set(actual)
            extra = set(actual) - set(expected)
            logger.info(f"\n[validate_reducers] reducer mismatch {output_path}\n")

            if missing:
                logger.info(f" missing keys {list(missing)[:5]}\n")

            if extra:
                logger.info(f" extra keys   {list(extra)[:5]}\n")

            if mismatched:
                logger.info(f" count mismatch { {k: (expected[k], actual[k]) for k in list(mismatched)[:5]} }\n")


def validate_map_reduce(input_path: str, output_path: str):
    text = read_file_as_text(input_path)

    expected = Counter()

    for line in text.splitlines():
        for word in line.strip().split():
            cleaned = _CLEAN.sub("", word.lower())

            if cleaned:
                expected[cleaned] += 1

    output_text = read_file_as_text(output_path)

    result = {}

    for line in output_text.splitlines():
        if not line.strip():
            continue
        word, count = line.strip().split("\t")
        result[word] = int(count)

    if dict(expected) == result:
        logger.info(f"\n[validate_map_reduce] valid {len(expected)} unique words match\n")

    else:
        missing = set(expected) - set(result)
        extra = set(result) - set(expected)
        mismatched = {w for w in expected if w in result and expected[w] != result[w]}

        logger.info(f"\n[validate_map_reduce] mismatch\n")

        if missing:
            logger.info(f" missing words {len(missing)}\n")

        if extra:
            logger.info(f" extra words {len(extra)}\n")

        if mismatched:
            logger.info(f" count mismatch {len(mismatched)}\n")

