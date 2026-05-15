import asyncio
from app.db.database import SessionLocal
from app.core.settings import settings

async def monitor_workers():
    from app.kubernetes_client import _get_batch_client
    while True:
        try:
            batch_v1 = _get_batch_client()
            db = SessionLocal()

            k8s_workers = batch_v1.list_namespaced_job(namespace=settings.MANAGER_NAMESPACE)

            for k8s_worker in k8s_workers.items:
                worker_name = k8s_worker.metadata.name
                status = k8s_worker.status

                if status.succeeded:
                    print(f"[kubernetes_service.py] {worker_name} succeeded")
                elif status.failed:
                    print(f"[kubernetes_service.py] {worker_name} failed")

            db.close()
        except Exception as ex:
            print(f"[kubernetes_service.py] Exception occurred: {ex}")

        await asyncio.sleep(10)