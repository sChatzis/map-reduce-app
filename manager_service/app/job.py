from datetime import datetime

from pydantic import BaseModel, model_validator
from enum import Enum

import utility as util
import database as db
import commands as cmd

# job_id int auto increment,
# status varchar(20),
# input_files varchar(255),
# output_path varchar(255),
# mapper_code varchar(255),
# reducer_code varchar(255),
# created_at timestamptz,
# updated_at timestamptz,
# user_id int not null

class JobStatus(str, Enum):
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class JobRequest(BaseModel):
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    user_id: int

class Job(BaseModel):
    job_id: int
    status: JobStatus
    input_files: str
    output_path: str
    mapper_code: str
    reducer_code: str
    created_at: datetime
    updated_at: datetime
    user_id: int

def job_add_job(req: JobRequest):
    if not db.dds_db.connected:
        print(f"[job.py] job_add_job: no connection to dds")
        return None

    if req.user_id <= 0:
        print(f"[job.py] job_add_job: user id is not valid [{req.user_id}]")
        return None

    if not util.is_valid_path(req.input_files):
        print(f"[job.py] job_add_job: given input files path is not valid [{req.input_files}]")
        return None

    if not util.is_valid_path(req.output_path):
        print(f"[job.py] job_add_job: given output path is not valid [{req.output_path}]")
        return None

    if not util.is_valid_path(req.mapper_code):
        print(f"[job.py] job_add_job: given mapper code path is not valid [{req.mapper_code}]")
        return None

    if not util.is_valid_path(req.reducer_code):
        print(f"[job.py] job_add_job: given reducer code path is not valid [{req.reducer_code}]")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[job.py] job_add_job: could not get cursor from job database")
        return None

    try:
        cursor.execute(
                        cmd.JOB_ADD_JOB,
                        (
                            req.input_files,
                            req.output_path,
                            req.mapper_code,
                            req.reducer_code,
                            req.user_id
                        )
        )

    except Exception as ex:
        print(f"[job.py] job_add_job: failed to execute query [{ex}]")
        return None

    if not db.dds_db.commit():
        print(f"[job.py] job_add_job: could not add job to the dds database")
        return None

    try:
        job = cursor.fetchone()
        job = Job.model_validate(job)
    except Exception as ex:
        print(f"[job.py] job_add_job: failed to validate job [{ex}]")
        job = None

    db.dds_db.close()

    return job

def job_find_job(id: int):
    if not db.dds_db.connected:
        print(f"[job.py] job_find_job: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[job.py] job_find_job: could not get cursor from job database")
        return None

    job = None

    try:
        cursor.execute(cmd.JOB_FIND_JOB_BY_ID, (id,))
        job = cursor.fetchall()

        if len(job) != 1:
            print(f"[job.py] job_find_job: more than one jobs with the same id")
            job = None
    except Exception as ex:
        print(f"[job.py] job_find_job: failed to fetch job [{ex}]")
        job = None

    if job is not None:
        try:
            job = Job.model_validate(job[0])
        except Exception as ex:
            print(f"[job.py] job_find_job: could not validate model [{ex}]")
            job = None

    db.dds_db.close()

    return job

def job_get_jobs():
    if not db.dds_db.connected:
        print(f"[job.py] job_get_jobs: no connection to dds")
        return None

    cursor = db.dds_db.cursor()

    if cursor is None:
        print(f"[job.py] job_get_jobs: could not get cursor from the dds")
        return None

    jobs = None
    _jobs = None

    try:
        cursor.execute(cmd.JOB_GET_JOBS)
        _jobs = cursor.fetchall()
    except Exception as ex:
        print(f"[job.py] job_get_jobs: failed to fetch jobs [{ex}]")
        _jobs = None

    if _jobs is not None:
        print(f"[job.py] job_get_jobs: found {len(_jobs)} jobs")

        try:
            jobs = [Job.model_validate(j) for j in _jobs]
        except Exception as ex:
            print(f"[job.py] job_get_jobs: could not validate model [{ex}]")
            jobs = None

    db.dds_db.close()

    return jobs