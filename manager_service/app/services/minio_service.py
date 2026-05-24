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
        logger.info("\n[ensure_bucket] bucket already exists %s\n", name)
        return

    client.make_bucket(name)

    logger.info("\n[ensure_bucket] created bucket %s\n", name)


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
        logger.warning(f"\n[upload_local_file] local file missing {local_path}\n")
        return False

    file_size = os.path.getsize(local_path)

    with open(local_path, "rb") as f:
        client.put_object(
            settings.MINIO_BUCKET,
            out_fpath,
            data=f,
            length=file_size,
            content_type=content_type,
        )

    logger.info(f"\n[upload_local_file] uploaded {local_path} {out_fpath}\n")
    return True


def delete_files(files: list[str]) -> None:
    if not files:
        return

    _files = [DeleteObject(file) for file in files]

    try:
        errors = list(client.remove_objects(settings.MINIO_BUCKET, _files))

        if errors:
            for error in errors:
                logger.warning(f"\n[delete_files] failed deleting object {error}\n")
        else:
            logger.info(f"\n[delete_files] deleted {len(_files)} objects\n")
    except Exception as ex:
        logger.warning(f"\n[delete_files] failed deleting objects {ex}\n")


def write_text_to_file(path: str, data: bytes, content_type: str = "text/plain"):
        client.put_object(
            settings.MINIO_BUCKET,
            path,
            data=io.BytesIO(data),
            length=len(data),
            content_type=content_type,
        )


def read_file_as_text(input_path: str) -> str:
    resp = client.get_object(settings.MINIO_BUCKET, input_path)

    try:
        return resp.read().decode("utf-8")

    finally:
        resp.close()
        resp.release_conn()

