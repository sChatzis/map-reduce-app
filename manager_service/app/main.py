from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.settings import settings
from app.db.database import engine, Base
from app.models.job import Job
from app.models.task import Task
from app.models.worker import Worker
from app.api.v1.endpoints import jobs
from app.services.kubernetes_service import safe_monitor
from app.services.minio_service import ensure_bucket, upload_local_file

import asyncio
import logging

# Uvicorn's default LOGGING_CONFIG only attaches handlers to the ``uvicorn.*``
# loggers, leaving the root at WARNING; this makes ``app.*`` INFO logs visible.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    ensure_bucket(settings.MINIO_BUCKET)

    upload_local_file(f"app/utils/map.py", "map.py")
    upload_local_file(f"app/utils/reduce.py", "reduce.py")
    upload_local_file(f"test_input.txt", "test_input.txt")

    monitor_task = asyncio.create_task(safe_monitor())

    def handle_task_exception(t: asyncio.Task):
        try:
            t.result()
        except Exception as ex:
            logger.exception(f"[main.py] monitor_task crashed {ex}")

    monitor_task.add_done_callback(handle_task_exception)

    try:
        yield
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            logger.info("[main.py] monitor stopped")
        await engine.dispose()


app = FastAPI(title="Manager Service API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to the Manager Service API"}


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "manager_service"}
