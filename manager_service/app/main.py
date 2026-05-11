from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine, Base
from app.models import job, task, worker  # ensure all models are registered

# Create all tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Manager Service API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Welcome to the Manager Service API"}


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "manager_service"}
