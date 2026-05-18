from kubernetes import client as k8s_client
from kubernetes import config as kubernetes_config

from app.core.settings import settings
from app.models.enums import TaskType

import asyncio
import logging

logger = logging.getLogger(__name__)

_batch_v1 = None
_core_v1 = None

def _get_batch_client():
    global _batch_v1
    if _batch_v1 is None:
        try:
            kubernetes_config.load_incluster_config()
        except kubernetes_config.ConfigException:
            kubernetes_config.load_kube_config()
        _batch_v1 = k8s_client.BatchV1Api()
    return _batch_v1


def _get_core_client():
    global _core_v1
    if _core_v1 is None:
        _core_v1 = k8s_client.CoreV1Api()
    return _core_v1


def get_batch_client() -> k8s_client.BatchV1Api:
    """Return the (lazily initialized) BatchV1Api singleton.

    Designed for use as a FastAPI dependency so tests can override it with a
    fake client via ``app.dependency_overrides[get_batch_client] = lambda: fake``
    without touching a real Kubernetes cluster.
    """
    return _get_batch_client()


def get_core_client() -> k8s_client.CoreV1Api:
    return _get_core_client()


async def create_worker_job(
    worker_id: str,
    pod_name: str,
    script_fpath: str,
    in_fpath: str,
    out_fpath: str,
    task_type: TaskType,
    retries: int = 3
):
    batch_v1 = _get_batch_client()

    minio_env = [
        k8s_client.V1EnvVar(name="MINIO_BUCKET", value=settings.MINIO_BUCKET),
        k8s_client.V1EnvVar(name="MINIO_ENDPOINT", value=settings.MINIO_ENDPOINT),
        k8s_client.V1EnvVar(name="MINIO_ACCESS_KEY", value=settings.MINIO_ACCESS_KEY),
        k8s_client.V1EnvVar(name="MINIO_SECRET_KEY", value=settings.MINIO_SECRET_KEY),
    ]

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(
            name=f"worker-{worker_id}",
            labels={
                "worker_id": worker_id,
                "app": pod_name,
            }
        ),
        spec=k8s_client.V1JobSpec(
            backoff_limit=retries,
            ttl_seconds_after_finished=300,
            active_deadline_seconds=600,
            parallelism=1,
            completions=1,
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels={"app": pod_name}),
                spec=k8s_client.V1PodSpec(
                    restart_policy="OnFailure",
                    security_context=k8s_client.V1PodSecurityContext(
                        run_as_non_root=True,
                        run_as_user=1000
                    ),
                    containers=[
                        k8s_client.V1Container(
                            name=f"worker-{worker_id}-{task_type.value.lower()}",
                            image=settings.MANAGER_WORKER_IMAGE_NAME,
                            image_pull_policy="IfNotPresent",
                            env=minio_env + [
                                k8s_client.V1EnvVar(name="SCRIPT_OBJECT", value=script_fpath),
                                k8s_client.V1EnvVar(name="INPUT_OBJECT", value=in_fpath),
                                k8s_client.V1EnvVar(name="OUTPUT_OBJECT", value=out_fpath),
                            ],
                            resources=k8s_client.V1ResourceRequirements(
                                requests={"cpu": "100m", "memory": "128Mi"},
                                limits={"cpu": "500m", "memory": "512Mi"},
                            ),
                        )
                    ]
                )
            )
        )
    )

    return await asyncio.to_thread(
        batch_v1.create_namespaced_job,
        namespace=settings.MANAGER_NAMESPACE,
        body=job
    )
