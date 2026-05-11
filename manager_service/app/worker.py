from datetime import datetime

from pydantic import BaseModel, model_validator
from enum import Enum

import database as db
import commands as cmd

# worker_id serial primary key,
# pod_name varchar(20),
# status varchar(20) default 'idle',
# last_sign timestamptz default now()

class WorkerStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    FAILED = "failed"

class Worker(BaseModel):
    worker_id: int
    status: WorkerStatus
    pod_name: str
    last_sign: datetime

def worker_add_worker(name: str):
    if not db.dds_db.connected:
        print(f"[worker.py] worker_add_worker: no connection to dds")
        return None

    if name is None:
        print(f"[worker.py] worker_add_worker: worker name is None [{name}]")
        return None

    if name == "":
        print(f"[worker.py] worker_add_worker: worker name is empty [{name}]")

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[worker.py] worker_add_worker: could not get cursor from worker database")
        return None

    try:
        cursor.execute(cmd.WORKER_ADD_WORKER, (name,))
    except Exception as ex:
        print(f"[worker.py] worker_add_worker: failed to execute query [{ex}]")
        return None

    if not db.dds_db.commit():
        print(f"[worker.py] worker_add_worker: could not add worker to the dds database")
        return None

    try:
        worker = cursor.fetchone()
        worker = Worker.model_validate(worker)
    except Exception as ex:
        print(f"[worker.py] worker_add_worker: failed to validate worker [{ex}]")
        worker = None

    db.dds_db.close()

    return worker

def worker_find_worker_by_id(worker_id: int):
    if not db.dds_db.connected:
        print(f"[worker.py] worker_find_worker: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[worker.py] worker_find_worker: could not get cursor from worker database")
        return None

    worker = None

    try:
        cursor.execute(cmd.WORKER_FIND_WORKER_BY_ID, (id,))
        worker = cursor.fetchall()

        if len(worker) != 1:
            print(f"[worker.py] worker_find_worker: more than one workers with the same id")
            worker = None
    except Exception as ex:
        print(f"[worker.py] worker_find_worker: failed to fetch worker [{ex}]")
        worker = None

    if worker is not None:
        try:
            worker = Worker.model_validate(worker[0])
        except Exception as ex:
            print(f"[worker.py] worker_find_worker: could not validate model [{ex}]")
            worker = None

    db.dds_db.close()

    return worker

def worker_update_status():
    if not db.dds_db.connected:
        print(f"[worker.py] worker_find_worker: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[worker.py] worker_find_worker: could not get cursor from worker database")
        return None

    worker = None

    try:
        cursor.execute(cmd.WORKER_FIND_WORKER_BY_ID, (id,))
        worker = cursor.fetchall()

        if len(worker) != 1:
            print(f"[worker.py] worker_find_worker: more than one workers with the same id")
            worker = None
    except Exception as ex:
        print(f"[worker.py] worker_find_worker: failed to fetch worker [{ex}]")
        worker = None

    if worker is not None:
        try:
            worker = Worker.model_validate(worker[0])
        except Exception as ex:
            print(f"[worker.py] worker_find_worker: could not validate model [{ex}]")
            worker = None

    db.dds_db.close()

    return worker

def worker_get_workers():
    if not db.dds_db.connected:
        print(f"[worker.py] worker_get_workers: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[worker.py] worker_get_workers: could not get cursor from the dds")
        return None

    workers = None
    _workers = None

    try:
        cursor.execute(cmd.WORKER_GET_WORKERS)
        _workers = cursor.fetchall()
    except Exception as ex:
        print(f"[worker.py] worker_get_workers: failed to fetch workers [{ex}]")
        _workers = None

    if _workers is not None:
        print(f"[worker.py] worker_get_workers: found {len(_workers)} workers")

        try:
            workers = [Worker.model_validate(j) for j in _workers]
        except Exception as ex:
            print(f"[worker.py] worker_get_workers: could not validate model [{ex}]")
            workers = None

    db.dds_db.close()

    return workers