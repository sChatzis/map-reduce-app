import os
from urllib.parse import quote_plus


class Settings:
    POSTGRES_USER: str = os.getenv("POSTGRES_DDS_USER", "dds_user")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_DDS_PASSWORD", "pass")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_DDS_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_DDS_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DDS_DB", "dds")

    DATABASE_URL: str = (
        f"postgresql+psycopg2://{POSTGRES_USER}:{quote_plus(POSTGRES_PASSWORD)}"
        f"@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "your-insecure-default-secret-key")
    ALGORITHM: str = "HS256"

    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
    MINIO_BUCKET: str = os.getenv("MINIO_BUCKET", "jobs")
    MINIO_ACCESS_KEY: str = os.getenv("MINIO_ACCESS_KEY", "minio")
    MINIO_SECRET_KEY: str = os.getenv("MINIO_SECRET_KEY", "pass")

    MANAGER_NAMESPACE: str = os.getenv("MANAGER_NAMESPACE", "default")
    MANAGER_WORKER_IMAGE_NAME: str = os.getenv("MANAGER_WORKER_IMAGE_NAME", "manager_worker:latest")


settings = Settings()
