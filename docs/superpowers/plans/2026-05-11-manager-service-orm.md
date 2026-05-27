# Manager Service ORM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the colleague's flat psycopg2 manager service with a structured SQLAlchemy ORM approach, fix all auth service issues on this branch, resolve UI service merge conflicts, and ensure the full stack runs cleanly via Docker Compose.

**Architecture:** The manager service uses a layered structure (`models/`, `db/`, `core/`, `schemas/`, `api/`, `services/`, `utils/`) mirroring the auth service layout. Business logic from colleague's `job.py`, `task.py`, `worker.py` is adapted to use SQLAlchemy sessions. The colleague's flat files (`database.py`, `commands.py`, etc.) are deleted.

**Tech Stack:** FastAPI, SQLAlchemy 2.x (ORM), PostgreSQL via psycopg2-binary, Pydantic v2, Python-JOSE (JWT), passlib (bcrypt), kubernetes Python SDK, MinIO Python SDK, Docker Compose.

---

## File Map

### manager_service/app/ — files to CREATE
```
app/
├── models/
│   ├── __init__.py
│   ├── enums.py          # JobStatus, TaskType, TaskStatus, WorkerStatus
│   ├── job.py            # SQLAlchemy Job ORM model
│   ├── task.py           # SQLAlchemy Task ORM model
│   └── worker.py         # SQLAlchemy Worker ORM model
├── db/
│   ├── __init__.py
│   └── database.py       # engine, SessionLocal, Base, get_db
├── core/
│   ├── __init__.py
│   └── config.py         # Settings reading env vars
├── schemas/
│   ├── __init__.py
│   ├── job.py            # Pydantic JobCreate, JobOut
│   ├── task.py           # Pydantic TaskOut
│   └── worker.py         # Pydantic WorkerOut
├── api/
│   ├── __init__.py
│   └── v1/
│       ├── __init__.py
│       └── endpoints/
│           ├── __init__.py
│           └── jobs.py   # Router: POST /jobs, GET /jobs, GET /jobs/{id}, GET /jobs/{id}/result
├── services/
│   ├── __init__.py
│   ├── job_service.py    # job_add, job_get, job_get_all (SQLAlchemy session)
│   ├── task_service.py   # task_add, task_get, task_get_all
│   └── worker_service.py # worker_add, worker_get, worker_get_all, worker_update_status
└── utils/
    ├── __init__.py
    └── utility.py        # is_valid_path (moved from app/utility.py)
```

### manager_service/app/ — files to REWRITE
- `app/main.py` — FastAPI app with SQLAlchemy lifespan (`create_all` on startup)
- `app/kubernetes_client.py` — Fix: lazy K8s init (not at module level), fix `SCRIPT_PATH` → `SCRIPT_OBJECT`

### manager_service/app/ — files to DELETE
- `app/database.py` (psycopg2 Database class)
- `app/config.py` (flat env var module)
- `app/commands.py` (raw SQL strings)
- `app/job.py` (psycopg2 job functions)
- `app/task.py` (psycopg2 task functions)
- `app/worker.py` (psycopg2 worker functions)
- `app/manager.py` (old router)
- `app/utility.py` (moved to `app/utils/utility.py`)

### Other files to fix
- `authentication_service/app/models/enums.py` — Fix enum values to uppercase (ADMIN="ADMIN" etc.)
- `authentication_service/app/core/security.py` — Fix `role != "admin"` → `role != UserRole.ADMIN`
- `authentication_service/app/api/v1/endpoints/users.py` — Move `GET /me` before `GET /{user_id}`, fix `GET /` to admin-only
- `ui_service/cli.py` — Resolve merge conflicts
- `ui_service/Dockerfile` — Resolve merge conflicts
- `ui_service/requirements.txt` — Resolve merge conflicts
- `ui_service/ui-service.yaml` — Resolve merge conflicts
- `docker-compose.yml` — Fix dds volume mount path typo, add `JWT_SECRET_KEY` to manager_service, add healthchecks
- `manager_worker/worker.py` — Fix `SCRIPT_OBJECT` env var (already correct, no change needed)

---

## Task 1: Fix Auth Service — Enums, Security, Routing

**Files:**
- Modify: `authentication_service/app/models/enums.py`
- Modify: `authentication_service/app/core/security.py`
- Modify: `authentication_service/app/api/v1/endpoints/users.py`

### Context
The auth service currently has lowercase enum values (`ADMIN = "admin"`, `USER = "plain_user"`). These need to match the PostgreSQL ENUM type values exactly. The fix is uppercase values so the enum name and value align. The `GET /me` route must be declared before `GET /{user_id}` — FastAPI matches routes in order, so `/me` would otherwise be matched as `/{user_id}` with `user_id = "me"`.

- [ ] **Step 1: Fix enums.py — use uppercase values**

Replace the entire file `authentication_service/app/models/enums.py`:

```python
from enum import Enum


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    USER = "USER"


class UserStatus(str, Enum):
    PENDING_APPROVAL = "PENDING_APPROVAL"
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
```

- [ ] **Step 2: Fix security.py — remove hardcoded "admin" string**

In `authentication_service/app/core/security.py`, change the admin check in `get_admin_user_payload` from:
```python
if role != "admin":
```
to:
```python
if role != UserRole.ADMIN:
```

Also remove the dead `decode_access_token` function (lines 61–75) — it is never called and duplicates `get_current_user`.

The final `get_admin_user_payload` function should be:
```python
def get_admin_user_payload(payload: dict = Depends(get_current_user)) -> dict:
    role = payload.get("role")
    if role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operation requires administrator privileges."
        )
    return payload
```

- [ ] **Step 3: Fix users.py — move GET /me before GET /{user_id}, fix GET / to admin-only**

Replace the entire `authentication_service/app/api/v1/endpoints/users.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import DBUser
from app.schemas.user import UserCreate, TokenRequest, Token, UserOut, UserUpdate
from app.core.security import get_password_hash, verify_password, create_access_token, get_active_user, get_admin_user_payload, get_current_user
from app.models.enums import UserStatus, UserRole

router = APIRouter()


# --- Sign Up ---
@router.post("/signup", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register_user(user_in: UserCreate, db: Session = Depends(get_db)):
    """Registers a new user. Account status is PENDING_APPROVAL until admin activates it."""
    if db.query(DBUser).filter(DBUser.username == user_in.username).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )

    hashed_password = get_password_hash(user_in.password)
    new_user = DBUser(
        username=user_in.username,
        password=hashed_password,
        role=UserRole.USER,
        status=UserStatus.PENDING_APPROVAL
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


# --- Get current user (MUST be before /{user_id}) ---
@router.get("/me", response_model=UserOut, status_code=status.HTTP_200_OK)
def get_me(current_user: DBUser = Depends(get_active_user)):
    """Retrieve the current user's information. Requires a valid, active JWT token."""
    return current_user


# --- Log In ---
@router.post("/login", response_model=Token)
def login(form_data: TokenRequest, db: Session = Depends(get_db)):
    """Authenticates the user and returns a JWT access token."""
    user = db.query(DBUser).filter_by(username=form_data.username).first()

    if not user or not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status.value}. Access denied. Requires admin approval."
        )

    access_token = create_access_token(
        data={
            "sub": user.username,
            "user_id": user.id,
            "role": user.role.value,
            "status": user.status.value
        }
    )
    return {"access_token": access_token, "token_type": "bearer"}


# --- Get all users (Admin only) ---
@router.get("/", response_model=list[UserOut], dependencies=[Depends(get_admin_user_payload)])
def read_all_users(db: Session = Depends(get_db)):
    return db.query(DBUser).all()


# --- Get specific user by ID (Admin only) ---
@router.get("/{user_id}", response_model=UserOut, dependencies=[Depends(get_admin_user_payload)])
def read_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# --- Update User Status (Admin only) ---
@router.patch("/{user_id}", response_model=UserOut, dependencies=[Depends(get_admin_user_payload)])
def update_user_status(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(user, key, value)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --- Delete User (Admin only) ---
@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(get_admin_user_payload)])
def delete_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(DBUser).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db.delete(user)
    db.commit()
```

- [ ] **Step 4: Commit**

```bash
git add auth_service/app/models/enums.py \
        auth_service/app/core/security.py \
        auth_service/app/api/v1/endpoints/users.py
git commit -m "fix: align auth service enums to uppercase, fix admin check, fix route ordering"
```

---

## Task 2: Resolve UI Service Merge Conflicts

**Files:**
- Modify: `ui_service/cli.py`
- Modify: `ui_service/Dockerfile`
- Modify: `ui_service/requirements.txt`
- Modify: `ui_service/ui-service.yaml`

All four files have git merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`). The content on both sides of each conflict is identical — the only real difference is that `requirements.txt` was missing `requests` on one side, and `ui-service.yaml` was missing `targetPort: 8000` on one side.

- [ ] **Step 1: Rewrite cli.py — remove conflict markers**

Replace `ui_service/cli.py` with the clean version (identical code on both sides):

```python
import requests
import typer
from typing_extensions import Annotated
import os
from pathlib import Path

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000/v1/users")
TOKEN_FILE = Path.home() / ".mapreduce_token"

app = typer.Typer(help="MapReduce Authentication CLI")
admin_app = typer.Typer(help="System administration commands")
app.add_typer(admin_app, name="admin")


def get_headers():
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text().strip()
        return {"Authorization": f"Bearer {token}"}
    return {}


# ==========================================
# Authentication
# ==========================================
@app.command()
def signup(
        username: Annotated[str, typer.Option(prompt=True, help="Choose a username")],
        password: Annotated[str, typer.Option(prompt=True, hide_input=True, help="Choose a password")]
):
    """Create a new user account."""
    try:
        response = requests.post(f"{BASE_URL}/signup", json={"username": username, "password": password})
        if response.status_code == 201:
            typer.echo("User created successfully. Status: PENDING_APPROVAL. Wait for admin.")
        else:
            typer.echo(f"Error: {response.json().get('detail', response.text)}")
    except Exception as e:
        typer.echo(f"Connection Error: {e}")


@app.command()
def login(
        username: Annotated[str, typer.Option(prompt=True, help="Your username")],
        password: Annotated[str, typer.Option(prompt=True, hide_input=True, help="Your password")]
):
    """Authenticate to receive a user token."""
    try:
        response = requests.post(f"{BASE_URL}/login", json={"username": username, "password": password})
        if response.status_code == 200:
            token = response.json().get("access_token")
            TOKEN_FILE.write_text(token)
            typer.echo("Login successful. Token saved locally.")
        else:
            typer.echo(f"Login failed: {response.json().get('detail', 'Unknown error')}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@app.command()
def whoami():
    """Check current logged-in user info."""
    try:
        response = requests.get(f"{BASE_URL}/me", headers=get_headers())
        if response.status_code == 200:
            user = response.json()
            typer.echo(f"Logged in as: {user.get('username')} | Role: {user.get('role')}")
        else:
            typer.echo("Not logged in or token expired.")
    except Exception as e:
        typer.echo(f"Error: {e}")


# ==========================================
# Admin Commands (Requires Admin JWT)
# ==========================================
@admin_app.command("list-users")
def admin_list_users():
    """List all registered users (Admin only)."""
    try:
        response = requests.get(f"{BASE_URL}/", headers=get_headers())
        response.raise_for_status()

        users = response.json()
        if not users:
            typer.echo("No users found.")
            return

        typer.echo(f"{'ID':<5} | {'Username':<15} | {'Role':<10} | {'Status'}")
        typer.echo("-" * 50)
        for u in users:
            typer.echo(f"{u['id']:<5} | {u['username']:<15} | {u['role']:<10} | {u['status']}")

    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@admin_app.command("verify-user")
def admin_verify_user(
        user_id: Annotated[int, typer.Argument(help="ID of the user to verify")]
):
    """Verify or approve a user account."""
    try:
        payload = {"status": "ACTIVE"}
        response = requests.patch(f"{BASE_URL}/{user_id}", json=payload, headers=get_headers())
        response.raise_for_status()
        typer.echo(f"User ID {user_id} is now ACTIVE.")
    except requests.exceptions.HTTPError as e:
        typer.echo(f"API Error: {e.response.json().get('detail', e)}")
    except Exception as e:
        typer.echo(f"Error: {e}")


@admin_app.command("delete-user")
def admin_delete_user(
        user_id: Annotated[int, typer.Argument(help="ID of the user to delete")]
):
    """Delete a user from the system."""
    if typer.confirm(f"Are you sure you want to delete User ID {user_id}?"):
        try:
            response = requests.delete(f"{BASE_URL}/{user_id}", headers=get_headers())
            response.raise_for_status()
            typer.echo(f"User ID {user_id} deleted successfully.")
        except requests.exceptions.HTTPError as e:
            typer.echo(f"API Error: {e.response.json().get('detail', e)}")
        except Exception as e:
            typer.echo(f"Error: {e}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 2: Rewrite Dockerfile — remove conflict markers**

Replace `ui_service/Dockerfile`:

```dockerfile
FROM python:3.11-slim as builder

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY ./requirements.txt /app/
RUN pip install --no-cache-dir -r /app/requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages

# Copy the CLI script
COPY ./cli.py /app/cli.py

# Keep the container running in the background so we can exec into it
CMD ["tail", "-f", "/dev/null"]
```

- [ ] **Step 3: Rewrite requirements.txt — remove conflict markers, include requests**

Replace `ui_service/requirements.txt`:

```
typer[all]
typing_extensions
requests
```

- [ ] **Step 4: Rewrite ui-service.yaml — remove conflict markers, include targetPort**

Replace `ui_service/ui-service.yaml`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ui-service
  labels:
    app: ui-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: ui-service
  template:
    metadata:
      labels:
        app: ui-service
    spec:
      containers:
      - name: python-ui
        image: mapreduce-cli:latest
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 8000
        env:
        - name: BASE_URL
          value: "http://manager-service:8000/v1/users"
---
apiVersion: v1
kind: Service
metadata:
  name: ui-service-lb
spec:
  type: LoadBalancer
  selector:
    app: ui-service
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8000
```

- [ ] **Step 5: Commit**

```bash
git add ui_service/cli.py ui_service/Dockerfile ui_service/requirements.txt ui_service/ui-service.yaml
git commit -m "fix: resolve ui_service merge conflicts"
```

---

## Task 3: Create Manager Service — Models, DB, Core, Schemas, Utils

**Files:**
- Create: `manager_service/app/models/__init__.py`
- Create: `manager_service/app/models/enums.py`
- Create: `manager_service/app/models/job.py`
- Create: `manager_service/app/models/task.py`
- Create: `manager_service/app/models/worker.py`
- Create: `manager_service/app/db/__init__.py`
- Create: `manager_service/app/db/database.py`
- Create: `manager_service/app/core/__init__.py`
- Create: `manager_service/app/core/config.py`
- Create: `manager_service/app/schemas/__init__.py`
- Create: `manager_service/app/schemas/job.py`
- Create: `manager_service/app/schemas/task.py`
- Create: `manager_service/app/schemas/worker.py`
- Create: `manager_service/app/utils/__init__.py`
- Create: `manager_service/app/utils/utility.py`

- [ ] **Step 1: Create all __init__.py files (empty)**

Create these files with empty content:
- `manager_service/app/models/__init__.py`
- `manager_service/app/db/__init__.py`
- `manager_service/app/core/__init__.py`
- `manager_service/app/schemas/__init__.py`
- `manager_service/app/utils/__init__.py`
- `manager_service/app/api/__init__.py`
- `manager_service/app/api/v1/__init__.py`
- `manager_service/app/api/v1/endpoints/__init__.py`
- `manager_service/app/services/__init__.py`

- [ ] **Step 2: Create manager_service/app/models/enums.py**

```python
from enum import Enum


class JobStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class TaskType(str, Enum):
    MAP = "MAP"
    REDUCE = "REDUCE"


class TaskStatus(str, Enum):
    IDLE = "IDLE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkerStatus(str, Enum):
    ACTIVE = "ACTIVE"
    IDLE = "IDLE"
    FAILED = "FAILED"
```

- [ ] **Step 3: Create manager_service/app/core/config.py**

```python
import os
from dotenv import load_dotenv
from urllib.parse import quote_plus

load_dotenv()


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
```

- [ ] **Step 4: Create manager_service/app/db/database.py**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 5: Create manager_service/app/models/job.py**

```python
from datetime import datetime

from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.orm import relationship

from app.db.database import Base


class Job(Base):
    __tablename__ = "jobs"

    job_id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(String(20), default="SUBMITTED", nullable=False)
    input_files = Column(String(255), nullable=False)
    output_path = Column(String(255), nullable=False)
    mapper_code = Column(String(255), nullable=False)
    reducer_code = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user_id = Column(Integer, nullable=False)

    tasks = relationship("Task", back_populates="job", cascade="all, delete-orphan")
```

- [ ] **Step 6: Create manager_service/app/models/worker.py**

```python
from sqlalchemy import Column, Integer, String, DateTime, func

from app.db.database import Base


class Worker(Base):
    __tablename__ = "workers"

    worker_id = Column(Integer, primary_key=True, autoincrement=True)
    pod_name = Column(String(255), nullable=False)
    status = Column(String(20), default="IDLE", nullable=False)
    last_heartbeat = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship("Task", back_populates="worker")
```

- [ ] **Step 7: Create manager_service/app/models/task.py**

```python
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from app.db.database import Base


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(Integer, primary_key=True, autoincrement=True)
    type = Column(String(10), nullable=False)
    status = Column(String(20), default="IDLE", nullable=False)
    input_split = Column(String(255))
    data_location = Column(String(255))
    job_id = Column(Integer, ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False)
    worker_id = Column(Integer, ForeignKey("workers.worker_id", ondelete="SET NULL"), nullable=True)

    job = relationship("Job", back_populates="tasks")
    worker = relationship("Worker", back_populates="tasks")
```

- [ ] **Step 8: Create manager_service/app/schemas/job.py**

```python
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import JobStatus


class JobCreate(BaseModel):
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    user_id: int


class JobOut(BaseModel):
    job_id: int
    status: JobStatus
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    created_at: datetime
    updated_at: datetime
    user_id: int

    model_config = {"from_attributes": True}
```

- [ ] **Step 9: Create manager_service/app/schemas/task.py**

```python
from typing import Optional
from pydantic import BaseModel
from app.models.enums import TaskType, TaskStatus


class TaskOut(BaseModel):
    task_id: int
    type: TaskType
    status: TaskStatus
    input_split: Optional[str]
    data_location: Optional[str]
    job_id: int
    worker_id: Optional[int]

    model_config = {"from_attributes": True}
```

- [ ] **Step 10: Create manager_service/app/schemas/worker.py**

```python
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import WorkerStatus


class WorkerOut(BaseModel):
    worker_id: int
    pod_name: str
    status: WorkerStatus
    last_heartbeat: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 11: Create manager_service/app/utils/utility.py**

```python
from pathlib import PurePosixPath
import re


def is_valid_path(path: str) -> bool:
    if (not PurePosixPath(path).is_absolute()) or ("\0" in path):
        return False
    return bool(re.match(r'^[a-zA-Z0-9/_\-\.]+$', path))
```

- [ ] **Step 12: Commit**

```bash
git add manager_service/app/models/ \
        manager_service/app/db/ \
        manager_service/app/core/ \
        manager_service/app/schemas/ \
        manager_service/app/utils/ \
        manager_service/app/api/ \
        manager_service/app/services/
git commit -m "feat: add manager service ORM structure (models, db, core, schemas, utils)"
```

---

## Task 4: Create Manager Service — Services (Business Logic)

**Files:**
- Create: `manager_service/app/services/job_service.py`
- Create: `manager_service/app/services/task_service.py`
- Create: `manager_service/app/services/worker_service.py`

These adapt the colleague's logic from `job.py`, `task.py`, `worker.py` to use SQLAlchemy sessions instead of psycopg2.

- [ ] **Step 1: Create manager_service/app/services/job_service.py**

```python
from typing import Optional

from sqlalchemy.orm import Session

from app.models.job import Job
from app.models.enums import JobStatus
from app.schemas.job import JobCreate
from app.utils.utility import is_valid_path


def job_add(req: JobCreate, db: Session) -> Optional[Job]:
    if req.user_id <= 0:
        print(f"[job_service] job_add: user_id not valid [{req.user_id}]")
        return None

    for field_name, value in [
        ("input_files", req.input_files),
        ("output_path", req.output_path),
        ("mapper_code", req.mapper_code),
        ("reducer_code", req.reducer_code),
    ]:
        if not is_valid_path(value):
            print(f"[job_service] job_add: invalid path for {field_name} [{value}]")
            return None

    job = Job(
        status=JobStatus.SUBMITTED,
        input_files=req.input_files,
        output_path=req.output_path,
        mapper_code=req.mapper_code,
        reducer_code=req.reducer_code,
        user_id=req.user_id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def job_get(job_id: int, db: Session) -> Optional[Job]:
    return db.query(Job).filter(Job.job_id == job_id).first()


def job_get_all(db: Session) -> list[Job]:
    return db.query(Job).all()


def job_update_status(job_id: int, new_status: JobStatus, db: Session) -> Optional[Job]:
    job = db.query(Job).filter(Job.job_id == job_id).first()
    if job is None:
        return None
    job.status = new_status
    db.commit()
    db.refresh(job)
    return job
```

- [ ] **Step 2: Create manager_service/app/services/task_service.py**

```python
from typing import Optional

from sqlalchemy.orm import Session

from app.models.task import Task
from app.models.enums import TaskType, TaskStatus


def task_add(job_id: int, task_type: TaskType, input_split: str, data_location: str, db: Session) -> Optional[Task]:
    task = Task(
        job_id=job_id,
        type=task_type,
        status=TaskStatus.IDLE,
        input_split=input_split,
        data_location=data_location,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def task_get(task_id: int, db: Session) -> Optional[Task]:
    return db.query(Task).filter(Task.task_id == task_id).first()


def task_get_all(db: Session) -> list[Task]:
    return db.query(Task).all()


def task_get_by_job(job_id: int, db: Session) -> list[Task]:
    return db.query(Task).filter(Task.job_id == job_id).all()


def task_update_status(task_id: int, new_status: TaskStatus, db: Session) -> Optional[Task]:
    task = db.query(Task).filter(Task.task_id == task_id).first()
    if task is None:
        return None
    task.status = new_status
    db.commit()
    db.refresh(task)
    return task
```

- [ ] **Step 3: Create manager_service/app/services/worker_service.py**

```python
from typing import Optional
from datetime import datetime, UTC

from sqlalchemy.orm import Session

from app.models.worker import Worker
from app.models.enums import WorkerStatus


def worker_add(pod_name: str, db: Session) -> Optional[Worker]:
    if not pod_name:
        print(f"[worker_service] worker_add: pod_name is empty")
        return None

    worker = Worker(
        pod_name=pod_name,
        status=WorkerStatus.IDLE,
    )
    db.add(worker)
    db.commit()
    db.refresh(worker)
    return worker


def worker_get(worker_id: int, db: Session) -> Optional[Worker]:
    return db.query(Worker).filter(Worker.worker_id == worker_id).first()


def worker_get_all(db: Session) -> list[Worker]:
    return db.query(Worker).all()


def worker_update_status(worker_id: int, new_status: WorkerStatus, db: Session) -> Optional[Worker]:
    worker = db.query(Worker).filter(Worker.worker_id == worker_id).first()
    if worker is None:
        print(f"[worker_service] worker_update_status: worker {worker_id} not found")
        return None

    worker.status = new_status
    worker.last_heartbeat = datetime.now(UTC)
    db.commit()
    db.refresh(worker)
    return worker
```

- [ ] **Step 4: Commit**

```bash
git add manager_service/app/services/
git commit -m "feat: add manager service business logic (job, task, worker services)"
```

---

## Task 5: Create Manager Service — Jobs API Endpoints + Rewrite main.py

**Files:**
- Create: `manager_service/app/api/v1/endpoints/jobs.py`
- Modify: `manager_service/app/main.py`

- [ ] **Step 1: Create manager_service/app/api/v1/endpoints/jobs.py**

This adapts `manager.py` routes to use the new services and SQLAlchemy sessions:

```python
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.job import JobCreate, JobOut
from app.models.enums import JobStatus
from app.services import job_service

router = APIRouter()


@router.post("/jobs", response_model=JobOut, status_code=201)
def add_job(req: JobCreate, db: Session = Depends(get_db)):
    print("[jobs.py] add_job")
    job = job_service.job_add(req, db)
    if job is None:
        raise HTTPException(status_code=500, detail="Job insert failed")
    return job


@router.get("/jobs", response_model=list[JobOut])
def get_jobs(db: Session = Depends(get_db)):
    print("[jobs.py] get_jobs")
    return job_service.job_get_all(db)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    print(f"[jobs.py] get_job: job_id [{job_id}]")
    job = job_service.job_get(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")
    return job


@router.get("/jobs/{job_id}/result")
def get_job_result(job_id: int, db: Session = Depends(get_db)):
    print(f"[jobs.py] get_job_result: job_id [{job_id}]")
    job = job_service.job_get(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Job {job_id} is not completed yet (status: {job.status})")
    return {"output_path": job.output_path}


@router.post("/jobs/{job_id}/recover")
def recover_job(job_id: int, db: Session = Depends(get_db)):
    print(f"[jobs.py] recover_job: job_id [{job_id}]")
    job = job_service.job_get(job_id, db)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found with id = {job_id}")
    return {"message": f"Recovered job {job_id}"}
```

- [ ] **Step 2: Rewrite manager_service/app/main.py**

```python
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.db.database import engine, Base
from app.api.v1.endpoints import jobs


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[main.py] lifespan: creating database tables")
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
```

- [ ] **Step 3: Commit**

```bash
git add manager_service/app/api/ manager_service/app/main.py
git commit -m "feat: add manager service jobs API router and rewrite main.py with SQLAlchemy lifespan"
```

---

## Task 6: Fix kubernetes_client.py + Delete Old Flat Files

**Files:**
- Modify: `manager_service/app/kubernetes_client.py`
- Delete: `manager_service/app/database.py`, `manager_service/app/config.py`, `manager_service/app/commands.py`, `manager_service/app/job.py`, `manager_service/app/task.py`, `manager_service/app/worker.py`, `manager_service/app/manager.py`, `manager_service/app/utility.py`

### Bugs in the original kubernetes_client.py:
1. `kubernetes_config.load_incluster_config()` at module level — crashes outside K8s cluster
2. `batch_v1 = client.BatchV1Api()` at module level — depends on config being loaded
3. `SCRIPT_PATH` env var name doesn't match what `worker.py` reads (`SCRIPT_OBJECT`)

- [ ] **Step 1: Rewrite manager_service/app/kubernetes_client.py**

```python
from kubernetes import client as k8s_client
from kubernetes import config as kubernetes_config

from app.core.config import settings

_batch_v1 = None


def _get_batch_client():
    global _batch_v1
    if _batch_v1 is None:
        try:
            kubernetes_config.load_incluster_config()
        except kubernetes_config.ConfigException:
            kubernetes_config.load_kube_config()
        _batch_v1 = k8s_client.BatchV1Api()
    return _batch_v1


def create_worker_job(worker_id: int, pod_name: str, script_fpath: str, in_fpath: str, out_fpath: str, retries: int = 3):
    batch_v1 = _get_batch_client()

    minio_env = [
        k8s_client.V1EnvVar(name="MINIO_BUCKET", value=settings.MINIO_BUCKET),
        k8s_client.V1EnvVar(name="MINIO_ENDPOINT", value=settings.MINIO_ENDPOINT),
        k8s_client.V1EnvVar(name="MINIO_ACCESS_KEY", value=settings.MINIO_ACCESS_KEY),
        k8s_client.V1EnvVar(name="MINIO_SECRET_KEY", value=settings.MINIO_SECRET_KEY),
    ]

    script_var = k8s_client.V1EnvVar(name="SCRIPT_OBJECT", value=script_fpath)
    in_var = k8s_client.V1EnvVar(name="INPUT_OBJECT", value=in_fpath)
    out_var = k8s_client.V1EnvVar(name="OUTPUT_OBJECT", value=out_fpath)

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(name=f"worker-{worker_id}"),
        spec=k8s_client.V1JobSpec(
            backoff_limit=retries,
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels={"app": pod_name}),
                spec=k8s_client.V1PodSpec(
                    restart_policy="OnFailure",
                    containers=[
                        k8s_client.V1Container(
                            name=f"worker-{worker_id}-runner",
                            image=settings.MANAGER_WORKER_IMAGE_NAME,
                            env=minio_env + [script_var, in_var, out_var]
                        )
                    ]
                )
            )
        )
    )

    return batch_v1.create_namespaced_job(namespace=settings.MANAGER_NAMESPACE, body=job)
```

- [ ] **Step 2: Delete old flat files**

```bash
cd "/Users/stefanoschatzis/Desktop/Αρχεία Πανεπιστημίου/10ο Εξάμηνο/Principles of Distrubuted Systems/distributed-project"
git rm manager_service/app/database.py \
       manager_service/app/config.py \
       manager_service/app/commands.py \
       manager_service/app/job.py \
       manager_service/app/task.py \
       manager_service/app/worker.py \
       manager_service/app/manager.py \
       manager_service/app/utility.py
```

- [ ] **Step 3: Commit**

```bash
git add manager_service/app/kubernetes_client.py
git commit -m "refactor: replace psycopg2 flat files with SQLAlchemy ORM structure, fix kubernetes_client"
```

---

## Task 7: Fix docker-compose.yml + Update manager_service/requirements.txt

**Files:**
- Modify: `docker-compose.yml`
- Modify: `manager_service/requirements.txt`

### Issues in docker-compose.yml:
1. `dds` service: volume mount path typo `./manager_service_service/dds_init.sql` → not needed anymore (SQLAlchemy creates tables)
2. `auth_service`: missing healthcheck dependency (DB not ready on startup)
3. `manager_service`: missing `JWT_SECRET_KEY` env var
4. `manager_service`: has `volumes: - ./manager_service:/app` which overrides the Docker image content at runtime — remove for clean builds

### Issues in requirements.txt:
- `psycopg2-binary` still needed (SQLAlchemy uses it as driver)
- `passlib` and `python-jose` not needed in manager service (no auth logic there)
- `typer` not needed in manager service

- [ ] **Step 1: Rewrite docker-compose.yml**

```yaml
services:
  user_db:
    image: postgres:15
    container_name: user_db
    ports:
      - "5432:5432"
    environment:
      POSTGRES_USER: ${USER_DB_USER}
      POSTGRES_PASSWORD: ${USER_DB_PASSWORD}
      POSTGRES_DB: ${USER_DB_NAME}
    volumes:
      - user_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${USER_DB_USER} -d ${USER_DB_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 10

  dds:
    image: postgres:15
    container_name: dds
    ports:
      - "5433:5432"
    environment:
      POSTGRES_USER: ${DDS_USER}
      POSTGRES_PASSWORD: ${DDS_PASSWORD}
      POSTGRES_DB: ${DDS_NAME}
    volumes:
      - dds_postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DDS_USER} -d ${DDS_NAME}"]
      interval: 5s
      timeout: 5s
      retries: 10

  auth_service:
    build: ./auth_service
    container_name: auth_service
    ports:
      - "8000:8000"
    depends_on:
      user_db:
        condition: service_healthy
    environment:
      POSTGRES_USER: ${USER_DB_USER}
      POSTGRES_PASSWORD: ${USER_DB_PASSWORD}
      POSTGRES_DB: ${USER_DB_NAME}
      POSTGRES_SERVER: user_db
      POSTGRES_PORT: 5432
      JWT_SECRET_KEY: ${JWT_SECRET_KEY}

  ui_service:
    build: ./ui_service
    container_name: ui_service
    depends_on:
      - auth_service
    environment:
      BASE_URL: http://auth_service:8000/v1/users

  adminer:
    image: adminer
    restart: always
    ports:
      - "8081:8080"

  manager_service:
    build: ./manager_service
    container_name: manager_service
    ports:
      - "8001:8000"
    depends_on:
      dds:
        condition: service_healthy
    environment:
      POSTGRES_DDS_USER: ${DDS_USER}
      POSTGRES_DDS_PASSWORD: ${DDS_PASSWORD}
      POSTGRES_DDS_DB: ${DDS_NAME}
      POSTGRES_DDS_SERVER: dds
      POSTGRES_DDS_PORT: 5432

      JWT_SECRET_KEY: ${JWT_SECRET_KEY}

      MINIO_ENDPOINT: ${MINIO_ENDPOINT}
      MINIO_BUCKET: ${MINIO_BUCKET}
      MINIO_ACCESS_KEY: ${MINIO_ACCESS_KEY}
      MINIO_SECRET_KEY: ${MINIO_SECRET_KEY}

      MANAGER_NAMESPACE: default
      MANAGER_WORKER_IMAGE_NAME: manager_worker:latest

volumes:
  user_postgres_data:
  dds_postgres_data:
```

Note: `manager_worker` service is removed from docker-compose — it is a K8s Job, not a long-running service. It will be launched by the manager service via the Kubernetes API when a job is submitted.

- [ ] **Step 2: Update manager_service/requirements.txt**

```
fastapi
uvicorn
SQLAlchemy
psycopg2-binary
pydantic
python-dotenv
minio
kubernetes
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml manager_service/requirements.txt
git commit -m "fix: update docker-compose (healthchecks, remove volume override, fix JWT env var) and trim manager requirements"
```

---

## Task 8: Verify the Stack Builds and Auth + Manager Services Start

- [ ] **Step 1: Clear old DB volumes and rebuild**

```bash
docker compose down -v
docker compose build --no-cache auth_service manager_service ui_service
```

Expected: all three images build without errors.

- [ ] **Step 2: Start the stack**

```bash
docker compose up user_db dds auth_service manager_service
```

Watch logs. Expected:
- `user_db` and `dds` reach healthy state
- `auth_service` logs: `Application startup complete`
- `manager_service` logs: `[main.py] lifespan: tables ready` then `Application startup complete`

- [ ] **Step 3: Smoke-test auth service**

```bash
# Sign up
curl -s -X POST http://localhost:8000/v1/users/signup \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | python3 -m json.tool

# Login as admin (will fail — PENDING_APPROVAL, need to promote via DB first)
# Promote user to ADMIN + ACTIVE directly in DB:
docker exec -it user_db psql -U fastapi_user -d user_db \
  -c "UPDATE users SET role='ADMIN', status='ACTIVE' WHERE username='admin';"

# Login
TOKEN=$(curl -s -X POST http://localhost:8000/v1/users/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo $TOKEN

# Whoami
curl -s http://localhost:8000/v1/users/me \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Expected: `/me` returns `{"id": 1, "username": "admin", "role": "ADMIN", "status": "ACTIVE"}`.

- [ ] **Step 4: Smoke-test manager service**

```bash
# Submit a job (input_files, output_path, mapper_code, reducer_code must be valid absolute paths)
curl -s -X POST http://localhost:8001/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{"input_files": "/jobs/input/data.txt", "output_path": "/jobs/output/", "mapper_code": "/jobs/scripts/mapper.py", "reducer_code": "/jobs/scripts/reduce.py", "user_id": 1}' | python3 -m json.tool

# List jobs
curl -s http://localhost:8001/v1/jobs | python3 -m json.tool
```

Expected: job created with `status: "SUBMITTED"`, retrieved in list.

- [ ] **Step 5: Commit any fixes found during smoke test**

```bash
git add -p   # stage only the relevant fixes
git commit -m "fix: <describe what was wrong>"
```

---

## Notes

- The `dds_init.sql` file is no longer used. SQLAlchemy's `Base.metadata.create_all()` creates the tables on startup. You can delete `manager_service/dds_init.sql` or keep it as documentation.
- The `manager_worker` Dockerfile/worker.py are not touched in this plan. The K8s integration (actually launching workers) requires a running K8s cluster — it is tested separately.
- After all tasks are done: push `manager_branch` to remote and open a PR to `main`.
