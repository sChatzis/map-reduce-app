import os
import io
import re
import math
import hashlib
import logging
import uuid

from app.core.settings import settings
from app.services.minio_service import delete_files
from app.services.minio_service import client as minio_client

_KEY_CHARS = re.compile(r"^[A-Za-z0-9/_\-\.]+$")

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
    bucket: str = settings.MINIO_BUCKET,
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

    resp = minio_client.get_object(bucket, input_object)
    lines = resp.read().decode("utf-8").splitlines()
    resp.close()

    lines = [line for line in lines if line.strip()]
    if not lines:
        return []

    _, ext = os.path.splitext(input_object)

    if num_chunks == 1:
        chunk_path = f"{job_id}/chunks/{job_id}_chunk{ext}"
        chunk_data = ("\n".join(lines) + "\n").encode("utf-8")
        minio_client.put_object(
            bucket,
            chunk_path,
            data=io.BytesIO(chunk_data),
            length=len(chunk_data),
            content_type="text/plain",
        )
        logger.debug(f"[utility.py] uploaded single chunk → {chunk_path}")
        return [chunk_path]

    chunk_size = math.ceil(len(lines) / num_chunks)
    chunks = [lines[i : i + chunk_size] for i in range(0, len(lines), chunk_size)]

    chunk_paths: list[str] = []
    for idx, chunk in enumerate(chunks):
        chunk_data = ("\n".join(chunk) + "\n").encode("utf-8")
        chunk_path = f"{job_id}/chunks/{job_id}_chunk_{idx}{ext}"
        minio_client.put_object(
            bucket,
            chunk_path,
            data=io.BytesIO(chunk_data),
            length=len(chunk_data),
            content_type="text/plain",
        )
        chunk_paths.append(chunk_path)
        logger.debug(
            f"[utility.py] uploaded chunk {idx} of {len(chunk)} lines → {chunk_path}"
        )

    return chunk_paths


def partition_for_key(key: str, num_reducers: int) -> int:
    """Stable partition: same ``key`` → same reducer across processes and runs.

    Uses md5 — not Python's ``hash()``, which is salted per-process via
    PYTHONHASHSEED (PEP 456) and so would re-shuffle keys on a manager
    restart, breaking the MapReduce partition invariant. Not a security
    boundary; we just need a deterministic 128-bit spread.
    """
    return int(hashlib.md5(key.encode("utf-8")).hexdigest(), 16) % num_reducers


def merge_and_partition_map(
    input_object: str,
    job_id: str,
    map_paths: list[str],
    num_reducers: int,
    bucket: str = settings.MINIO_BUCKET
) -> list[str]:
    if not map_paths or num_reducers <= 0:
        return []

    parts = [[] for _ in range(num_reducers)]

    for path in map_paths:
        try:
            resp = minio_client.get_object(bucket, path)
            lines = resp.read().decode("utf-8").splitlines()
            resp.close()

            for line in lines:
                line = line.strip()
                if "\t" not in line:
                    continue
                key, value = line.split("\t", 1)
                reducer_idx = partition_for_key(key, num_reducers)
                parts[reducer_idx].append((key, value))

        except Exception as ex:
            logger.warning(f"[utility.py] merge_and_partition_map: failed to read {path}: {ex}")

    for part in parts:
        part.sort(key=lambda x: x[0])

    base, ext = os.path.splitext(input_object)

    if num_reducers == 1:
        all_pairs = parts[0]
        part_data = ("\n".join(f"{k}\t{v}" for k, v in all_pairs) + "\n").encode("utf-8")
        part_path = f"{job_id}/part/{job_id}_part{ext}"
        minio_client.put_object(
            bucket,
            part_path,
            data=io.BytesIO(part_data),
            length=len(part_data),
            content_type="text/plain"
        )
        logger.debug(f"[utility.py] uploaded part 0: {len(all_pairs)} pairs → {job_id}/part/{job_id}_part{ext}")
        return [part_path]

    part_paths = []

    for idx, part in enumerate(parts):
        part_data = ("\n".join(f"{k}\t{v}" for k, v in part) + "\n").encode("utf-8")
        part_path = f"{job_id}/part/{job_id}_part_{idx}{ext}"
        minio_client.put_object(
            bucket,
            part_path,
            data=io.BytesIO(part_data),
            length=len(part_data),
            content_type="text/plain"
        )
        part_paths.append(part_path)
        logger.debug(f"[utility.py] uploaded part {idx}: {len(part)} pairs → {job_id}/part/{job_id}_part_{idx}{ext}")

    return part_paths

def final_reduce_merge(job_id: str, reducer_outputs: list[str], output_path: str):
    if not reducer_outputs:
        logger.warning(f"[final-merge] no reducer outputs for job={job_id}")
        return

    merged_lines = []

    for path in reducer_outputs:
        try:
            resp = minio_client.get_object(settings.MINIO_BUCKET, path)
            data = resp.read().decode("utf-8")
            resp.close()

            merged_lines.extend(data.splitlines())

        except Exception as ex:
            logger.warning(f"[final-merge] failed reading {path}: {ex}")

    merged_lines.sort()

    final_data = ("\n".join(merged_lines) + "\n").encode("utf-8")

    minio_client.put_object(
        settings.MINIO_BUCKET,
        output_path,
        data=io.BytesIO(final_data),
        length=len(final_data),
        content_type="text/plain"
    )

    logger.info(f"[final-merge] created final output → {output_path}")


def cleanup_job_files(
    job_id: str,
    map_paths: list[str],
    reduce_input_paths: list[str],
    reduce_output_paths: list[str],
) -> None:
    files: list[str] = []

    if map_paths:
        files.extend(map_paths)

    if reduce_input_paths:
        files.extend(reduce_input_paths)

    if reduce_output_paths:
        files.extend(reduce_output_paths)

    if not files:
        logger.info(f"[cleanup] job={job_id} nothing to delete")
        return

    logger.info(f"[cleanup] {files}")

    try:
        delete_files(files)
        logger.info(f"[cleanup] job={job_id} deleted={len(files)} files")

    except Exception as ex:
        logger.warning(f"[cleanup] job={job_id} cleanup failed: {ex}")