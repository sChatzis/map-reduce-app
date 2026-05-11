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
