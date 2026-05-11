from fastapi import APIRouter, HTTPException

import job
import kubernetes_client

manager_router = APIRouter()

@manager_router.post("/jobs", status_code=201)
def manager_add_job(req: job.JobRequest):
    print("[manager_service.py] manager_add_job")

    _job = job.job_add_job(req)

    if _job is None:
        raise HTTPException(
            status_code=500,
            detail="Job insert failed"
        )

    return _job


@manager_router.get("/jobs/{id}")
def manager_get_job_by_id(id: int):
    print(f"[manager_service.py] manager_get_job_by_id: id [{id}]")

    _job = job.job_find_job(id)

    if _job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found with id = {id}"
        )

    return _job


@manager_router.get("/jobs")
def manager_get_jobs():
    print("[manager_service.py] manager_get_jobs")

    _jobs = job.job_get_jobs()

    if _jobs is None:
        raise HTTPException(
            status_code=500,
            detail="Failed to get jobs"
        )

    return _jobs


@manager_router.get("/jobs/{id}/result")
def manager_find_result_of_job(id: int):
    print(f"[manager_service.py] manager_find_result_of_job: id [{id}]")

    _job = job.job_find_job(id)

    if _job is None:
        raise HTTPException(
            status_code=404,
            detail=f"Job not found with id = {id}"
        )

    if _job.status != job.JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job with id = {id} not completed"
        )

    return {"output_path": _job.output_path}


@manager_router.post("/jobs/{id}/recover")
def manager_recover_job(id: int):
    print(f"[manager_service.py] manager_recover_job: id [{id}]")

    return {"message": f"Recovered job {id}"}