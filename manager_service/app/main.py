from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import uvicorn

import database as db
import manager

@asynccontextmanager
async def manager_lifespan(app: FastAPI):
    if not db.dds_db.connect():
        print(f"[main.py] manager_lifespan: dds connection failed", flush=True)
    else:
        print(f"[main.py] manager_lifespan: dds connection succeeded", flush=True)

    yield

    if not db.dds_db.disconnect():
        print(f"[main.py] manager_lifespan: dds disconnect failed", flush=True)
    else:
        print(f"[main.py] manager_lifespan: dds disconnect succeeded", flush=True)

app = FastAPI(title="Manager API", lifespan=manager_lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(manager.manager_router)

@app.exception_handler(404)
async def default_error(req: Request, exc: HTTPException):
    print(f"[main.py] default_error: Invalid URI [{req.url.path}]")
    return JSONResponse(
        status_code=404,
        content={"detail": f"[main.py] default_error: Invalid URI [{req.url.path}]"}
    )

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )