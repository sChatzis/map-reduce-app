from datetime import datetime

from pydantic import BaseModel, model_validator
from enum import Enum

import database as db
import commands as cmd

#    task_id serial primary key,
#    type varchar(10),
#    status varchar(20) default 'idle',
#    input_split varchar(255),
#    data_location varchar(255),
#    job_id integer not null,
#    worker_id integer,
#    foreign key (job_id) references jobs(job_id) on delete cascade,
#    foreign key (worker_id) references workers(worker_id) on delete set null

class TaskType(str, Enum):
    MAP = "map"
    REDUCE = "reduce"

class TaskStatus(str, Enum):
    IDLE = "idle"
    IN_PROGRESS = "in-progress"
    COMPLETED = "completed"

class Task(BaseModel):
    task_id: int
    type: TaskType
    status: TaskStatus
    input_split: str
    data_location: str
    job_id: int
    worker_id: int

def task_add_task(job_id: int, worker_id: int, type: TaskType, input_split: str, data_location: str):
    if not db.dds_db.connected:
        print(f"[task.py] task_add_task: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[task.py] task_add_task: could not get cursor from task database")
        return None

    try:
        cursor.execute(cmd.TASK_ADD_TASK, (job_id, worker_id, type, input_split, data_location))
    except Exception as ex:
        print(f"[task.py] task_add_task: failed to execute query [{ex}]")
        return None

    if not db.dds_db.commit():
        print(f"[task.py] task_add_task: could not add task to the dds database")
        return None

    try:
        task = cursor.fetchone()
        task = Task.model_validate(task)
    except Exception as ex:
        print(f"[task.py] task_add_task: failed to validate task [{ex}]")
        task = None

    db.dds_db.close()

    return task

def task_find_task_by_id(task_id: int):
    if not db.dds_db.connected:
        print(f"[task.py] task_find_task: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[task.py] task_find_task: could not get cursor from task database")
        return None

    task = None

    try:
        cursor.execute(cmd.TASK_FIND_TASK_BY_ID, (task_id,))
        task = cursor.fetchall()

        if len(task) != 1:
            print(f"[task.py] task_find_task: more than one tasks with the same id")
            task = None
    except Exception as ex:
        print(f"[task.py] task_find_task: failed to fetch task [{ex}]")
        task = None

    if task is not None:
        try:
            task = Task.model_validate(task[0])
        except Exception as ex:
            print(f"[task.py] task_find_task: could not validate model [{ex}]")
            task = None

    db.dds_db.close()

    return task

def task_get_tasks():
    if not db.dds_db.connected:
        print(f"[task.py] task_get_tasks: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[task.py] task_get_tasks: could not get cursor from the dds")
        return None

    tasks = None
    _tasks = None

    try:
        cursor.execute(cmd.TASK_GET_TASKS)
        _tasks = cursor.fetchall()
    except Exception as ex:
        print(f"[task.py] task_get_tasks: failed to fetch tasks [{ex}]")
        _tasks = None

    if _tasks is not None:
        print(f"[task.py] task_get_tasks: found {len(_tasks)} tasks")

        try:
            tasks = [Task.model_validate(j) for j in _tasks]
        except Exception as ex:
            print(f"[task.py] task_get_tasks: could not validate model [{ex}]")
            tasks = None

    db.dds_db.close()

    return tasks