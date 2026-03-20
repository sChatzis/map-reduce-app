from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.database import engine
from app.models.user import Base
from app.api.v1.endpoints import users

# Create the database tables automatically on startup
Base.metadata.create_all(bind=engine)

# Initialize application, includes the routers and handles the initial database set up
app = FastAPI(
    title="User Service API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Allow the React App
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

# --- REGISTER ROUTER ---
app.include_router(users.router, prefix="/v1/users", tags=["Users"])


@app.get("/")
def read_root():
    return {"message": "Welcome to the User Service API"}


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "user_service"}


