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

def task_add_batch(
        job_id: int,
        task_type: TaskType,
        input_splits: list[str],
        data_locations: list[str],
        db: Session
) -> list[Task]:
    if not input_splits or not data_locations:
        return []

    if len(input_splits) != len(data_locations):
        return []

    tasks = []

    for input_split, data_location in zip(input_splits, data_locations):
        task = Task(
            job_id=job_id,
            type=task_type,
            status=TaskStatus.IDLE,
            input_split=input_split,
            data_location=data_location,
        )
        db.add(task)
        tasks.append(task)

    db.commit()

    for task in tasks:
        db.refresh(task)

    return tasks


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
