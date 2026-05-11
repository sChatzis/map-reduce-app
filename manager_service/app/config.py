import os

DDS_DB_USER: str | None = os.getenv("POSTGRES_DDS_USER", None)
DDS_DB_PASSWORD: str | None = os.getenv("POSTGRES_DDS_PASSWORD", None)
DDS_DB_NAME: str | None = os.getenv("POSTGRES_DDS_DB", None)
DDS_DB_SERVER: str | None = os.getenv("POSTGRES_DDS_SERVER", None)
DDS_DB_PORT: int = int(os.getenv("POSTGRES_DDS_PORT", -1))

MINIO_BUCKET = os.getenv("MINIO_BUCKET", None)
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", None)
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", None)
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", None)

MANAGER_NAMESPACE = os.getenv("MANAGER_NAMESPACE", "default")
MANAGER_WORKER_IMAGE_NAME=os.getenv("MANAGER_WORKER_IMAGE_NAME", "manager_worker:latest")

print(f"[constants.py]: DDS_DB_USER {DDS_DB_USER}")
print(f"[constants.py]: DDS_DB_PASSWORD {DDS_DB_PASSWORD}")
print(f"[constants.py]: DDS_DB_NAME {DDS_DB_NAME}")
print(f"[constants.py]: DDS_DB_SERVER {DDS_DB_SERVER}")
print(f"[constants.py]: DDS_DB_PORT {DDS_DB_PORT}")

print(f"[constants.py]: MINIO_BUCKET {MINIO_BUCKET}")
print(f"[constants.py]: MINIO_ENDPOINT {MINIO_ENDPOINT}")
print(f"[constants.py]: MINIO_ACCESS_KEY {MINIO_ACCESS_KEY}")
print(f"[constants.py]: MINIO_SECRET_KEY {MINIO_SECRET_KEY}")