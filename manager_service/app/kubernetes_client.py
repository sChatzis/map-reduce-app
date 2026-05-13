from kubernetes import client as k8s_client
from kubernetes import config as kubernetes_config

from app.core.config import settings

_batch_v1 = None


def _get_batch_client():
    global _batch_v1
    if _batch_v1 is None:
        try:
            kubernetes_config.load_incluster_config()
        except kubernetes_config.ConfigException:
            kubernetes_config.load_kube_config()
        _batch_v1 = k8s_client.BatchV1Api()
    return _batch_v1


def create_worker_job(worker_id: int, pod_name: str, script_fpath: str, in_fpath: str, out_fpath: str, retries: int = 3):
    batch_v1 = _get_batch_client()

    minio_env = [
        k8s_client.V1EnvVar(name="MINIO_BUCKET", value=settings.MINIO_BUCKET),
        k8s_client.V1EnvVar(name="MINIO_ENDPOINT", value=settings.MINIO_ENDPOINT),
        k8s_client.V1EnvVar(name="MINIO_ACCESS_KEY", value=settings.MINIO_ACCESS_KEY),
        k8s_client.V1EnvVar(name="MINIO_SECRET_KEY", value=settings.MINIO_SECRET_KEY),
    ]

    script_var = k8s_client.V1EnvVar(name="SCRIPT_OBJECT", value=script_fpath)
    in_var = k8s_client.V1EnvVar(name="INPUT_OBJECT", value=in_fpath)
    out_var = k8s_client.V1EnvVar(name="OUTPUT_OBJECT", value=out_fpath)

    job = k8s_client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=k8s_client.V1ObjectMeta(name=f"worker-{worker_id}"),
        spec=k8s_client.V1JobSpec(
            backoff_limit=retries,
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(labels={"app": pod_name}),
                spec=k8s_client.V1PodSpec(
                    restart_policy="OnFailure",
                    containers=[
                        k8s_client.V1Container(
                            name=f"worker-{worker_id}-runner",
                            image=settings.MANAGER_WORKER_IMAGE_NAME,
                            env=minio_env + [script_var, in_var, out_var]
                        )
                    ]
                )
            )
        )
    )

    return batch_v1.create_namespaced_job(namespace=settings.MANAGER_NAMESPACE, body=job)
