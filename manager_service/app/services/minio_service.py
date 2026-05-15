import logging

from minio import Minio

from app.core.settings import settings

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