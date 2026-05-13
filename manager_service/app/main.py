from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db.database import engine, Base
from app.api.v1.endpoints import jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[main.py] lifespan: creating database tables")
    # Import all models so SQLAlchemy knows about them before create_all
    from app.models import job, task, worker  # noqa: F401
    Base.metadata.create_all(bind=engine)
    print("[main.py] lifespan: tables ready")
    yield
    print("[main.py] lifespan: shutdown")


app = FastAPI(title="Manager API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs.router, prefix="/v1")


@app.exception_handler(404)
async def not_found_handler(req: Request, exc: HTTPException):
    return JSONResponse(
        status_code=404,
        content={"detail": f"Invalid URI [{req.url.path}]"}
    )
