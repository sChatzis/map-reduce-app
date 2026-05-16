import os
import io
import re

from app.core.settings import settings
from app.services.minio_service import client as minio_client


_KEY_CHARS = re.compile(r"^[A-Za-z0-9/_\-\.]+$")


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

def generate_map_output_paths(input_path: str, num_chunks: int) -> list[str]:
    base, ext = os.path.splitext(input_path)
    file_name = os.path.basename(base)
    maps_dir = f"{base}_map"

    if num_chunks <= 0:
        return []

    if num_chunks == 1:
        return [input_path]

    return [
        f"{maps_dir}/{file_name}_map_{idx}{ext}"
        for idx in range(num_chunks)
    ]

def generate_reduce_input_paths(orig_path: str, num_reducers: int) -> list[str]:
    if num_reducers <= 0:
        return []

    base, ext = os.path.splitext(orig_path)
    file_name = os.path.basename(base)

    if num_reducers == 1:
        return [f"{base}_reduce/{file_name}_part{ext}"]

    return [
        f"{base}_part/{file_name}_part_{idx}{ext}"
        for idx in range(num_reducers)
    ]

def generate_reduce_output_paths(orig_path: str, num_reducers: int) -> list[str]:
    if num_reducers <= 0:
        return []

    base, ext = os.path.splitext(orig_path)
    file_name = os.path.basename(base)

    if num_reducers == 1:
        return [f"{base}_reduce/{file_name}_reduce{ext}"]

    return [
        f"{base}_reduce/{file_name}_reduce_{idx}{ext}"
        for idx in range(num_reducers)
    ]

def split_input_file_to_chunks(
    input_object: str,
    num_chunks: int,
    bucket: str = settings.MINIO_BUCKET
) -> list[str]:
    if num_chunks <= 0:
        return []

    if num_chunks == 1:
        return [input_object]

    resp = minio_client.get_object(bucket, input_object)
    lines = resp.read().decode("utf-8").splitlines()
    resp.close()

    lines = [line for line in lines if line.strip()]

    if not lines:
        return []

    base, ext = os.path.splitext(input_object)
    file_name = os.path.basename(base)

    chunk_size = max(1, len(lines) // num_chunks)
    chunks = [lines[idx : idx + chunk_size] for idx in range(0, len(lines), chunk_size)]
    chunk_paths = []

    for idx, chunk in enumerate(chunks):
        chunk_data = ("\n".join(chunk) + "\n").encode("utf-8")
        chunk_path = f"{base}_chunks/{file_name}_chunk_{idx}{ext}"

        minio_client.put_object(
            bucket,
            chunk_path,
            data=io.BytesIO(chunk_data),
            length=len(chunk_data),
            content_type="text/plain"
        )
        chunk_paths.append(chunk_path)
        print(f"[utility.py] uploaded chunk {idx} of {len(chunk_data)} bytes, {len(chunk)} lines → {chunk_path}")

    return chunk_paths

def merge_and_partition_map(
    input_object: str,
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
                reducer_idx = hash(key) % num_reducers
                parts[reducer_idx].append((key, value))

        except Exception as ex:
            print(f"[utility.py] reduce_merge_and_partition_map: failed to read {path}: {ex}")

    for part in parts:
        part.sort(key=lambda x: x[0])

    base, ext = os.path.splitext(input_object)
    file_name = os.path.basename(base)
    part_dir = f"{base}_part"

    if num_reducers == 1:
        all_pairs = parts[0]
        part_data = ("\n".join(f"{k}\t{v}" for k, v in all_pairs) + "\n").encode("utf-8")
        part_path = f"{part_dir}/{file_name}_part{ext}"
        minio_client.put_object(
            bucket,
            part_path,
            data=io.BytesIO(part_data),
            length=len(part_data),
            content_type="text/plain"
        )
        print(f"[utility.py] uploaded part 0: {len(all_pairs)} pairs → {part_path}")
        return [part_path]

    part_paths = []

    for idx, part in enumerate(parts):
        part_data = ("\n".join(f"{k}\t{v}" for k, v in part) + "\n").encode("utf-8")
        part_path = f"{part_dir}/{file_name}_part_{idx}{ext}"
        minio_client.put_object(
            bucket,
            part_path,
            data=io.BytesIO(part_data),
            length=len(part_data),
            content_type="text/plain"
        )
        part_paths.append(part_path)
        print(f"[utility.py] uploaded partition {idx}: {len(part)} pairs → {part_path}")

    return part_paths