from minio import Minio, S3Error
from minio.deleteobjects import DeleteObject

from app.core.settings import settings

import io
import os
import logging

logger = logging.getLogger(__name__)

client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ACCESS_KEY,
    secret_key=settings.MINIO_SECRET_KEY,
    secure=False,
)

def ensure_bucket(name: str) -> None:
    """Idempotently create a MinIO bucket.

    Safe to call on every startup: a no-op if the bucket already exists.
    Propagates errors when MinIO is unreachable so the service fails loudly
    at boot rather than silently breaking the first job submission.
    """
    if client.bucket_exists(name):
        logger.info("bucket already exists: %s", name)
        return
    client.make_bucket(name)
    logger.info("created bucket: %s", name)


def file_exists(fpath: str) -> bool:
    try:
        client.stat_object(settings.MINIO_BUCKET, fpath)
        return True
    except S3Error as ex:
        if ex.code == "NoSuchKey":
            return False
        raise


def upload_local_file(
    local_path: str,
    out_fpath: str,
    content_type: str = "text/plain",
) -> bool:
    if not os.path.exists(local_path):
        logger.warning(f"[upload] local file missing: {local_path}")
        return False

    with open(local_path, "rb") as f:
        data = f.read()

    client.put_object(
        settings.MINIO_BUCKET,
        out_fpath,
        data=io.BytesIO(data),
        length=len(data),
        content_type=content_type,
    )

    logger.info(f"[upload] uploaded {local_path} → {out_fpath}")
    return True


def delete_files(files: list[str]) -> None:
    if not files:
        return

    _files = [DeleteObject(file) for file in files]

    try:
        client.remove_objects(settings.MINIO_BUCKET, _files)
        logger.info(f"[cleanup] deleted {len(_files)} objects")
    except Exception as ex:
        logger.warning(f"[cleanup] failed deleting objects: {ex}")