JOB_ADD_JOB: str = """
            insert into jobs (
                input_files,
                output_path,
                mapper_code,
                reducer_code,
                user_id
            )
            values (%s, %s, %s, %s, %s)
            returning *
"""
JOB_FIND_JOB_BY_ID: str = f"select * from jobs where job_id = %s"
JOB_GET_JOBS: str = f"select * from jobs"

WORKER_ADD_WORKER: str = """
            insert into workers (
                pod_name
            )
            values (%s)
            returning *
"""
WORKER_FIND_WORKER_BY_ID: str = f"select * from workers where worker_id = %s"
WORKER_GET_WORKERS: str = f"select * from workers"
WORKER_CHANGE_STATUS: str = """
            update workers
            set status = %s, last_sign = now() 
            where worker_id = %s;
"""

TASK_ADD_TASK: str = """
            insert INTO tasks (
                job_id,
                worker_id,
                type,
                input_split,
                data_location
            )
            values (%s, %s, %s, %s, %s)
            returning *
"""
TASK_FIND_TASK_BY_ID: str = f"select * from tasks where task_id = %s"
TASK_GET_TASKS: str = f"select * from tasks"