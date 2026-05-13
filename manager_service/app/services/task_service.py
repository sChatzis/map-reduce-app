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
