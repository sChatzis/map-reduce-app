JOB_ADD_JOB: str = """
            INSERT INTO jobs (
                input_files,
                output_path,
                mapper_code,
                reducer_code,
                user_id
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING *
"""
JOB_FIND_JOB_BY_ID: str = f"select * from jobs where job_id = %s"
JOB_GET_JOBS: str = f"select * from jobs"

WORKER_ADD_WORKER: str = """
            INSERT INTO workers (
                pod_name
            )
            VALUES (%s)
            RETURNING *
"""
WORKER_FIND_WORKER_BY_ID: str = f"select * from workers where worker_id = %s"
WORKER_GET_WORKERS: str = f"select * from workers"