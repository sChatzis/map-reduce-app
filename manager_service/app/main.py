import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import engine, Base
from app.models.job import Job
from app.models.task import Task
from app.models.worker import Worker
from app.api.v1.endpoints import jobs
from app.services.kubernetes_service import monitor_workers

# Create all tables on startup
Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    monitor_task = asyncio.create_task(monitor_workers())
    yield
    monitor_task.cancel()
    try:
        await monitor_task
    except asyncio.CancelledError:
        print("[main.py] monitor stopped")


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
