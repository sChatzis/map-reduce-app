import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

class Settings:
    POSTGRES_USER: str = os.getenv("JOBS_DB_USER", "manager_user")
    POSTGRES_PASSWORD: str = os.getenv("JOBS_DB_PASSWORD", "secret")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("JOBS_DB_NAME", "jobs_db")
    DATABASE_URL: str = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{quote_plus(POSTGRES_PASSWORD)}"
        f"@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    JWT_SECRET_KEY: str = os.environ["JWT_SECRET_KEY"]
    ALGORITHM: str = "HS256"

    MANAGER_NAMESPACE: str = os.environ["MANAGER_NAMESPACE"]
    MANAGER_WORKER_IMAGE_NAME: str = os.environ["MANAGER_WORKER_IMAGE_NAME"]
    MANAGER_REFRESH_PERIOD: int = int(os.environ["MANAGER_REFRESH_PERIOD"])

    MINIO_ENDPOINT: str =  os.environ["MINIO_ENDPOINT"]
    MINIO_BUCKET: str =  os.environ["MINIO_BUCKET"]
    MINIO_ACCESS_KEY: str =  os.environ["MINIO_ACCESS_KEY"]
    MINIO_SECRET_KEY: str =  os.environ["MINIO_SECRET_KEY"]

settings = Settings()
