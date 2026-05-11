from kubernetes import client
from kubernetes import config as kubernetes_config

import config

def kubernetes_client_create_job(worker_id: int, pod_name: str, script_fpath: str, in_fpath: str, out_fpath: str, retries: int = 3):
    script_var = client.V1EnvVar(name="SCRIPT_PATH", value=script_fpath)
    in_var = client.V1EnvVar(name="INPUT_OBJECT", value=in_fpath)
    out_var = client.V1EnvVar(name="OUTPUT_OBJECT", value=out_fpath)

    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=f"worker_{worker_id}"),
        spec=client.V1JobSpec(
            backoff_limit=retries,
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": pod_name}),
                spec=client.V1PodSpec(
                    restart_policy="OnFailure",
                    containers=[
                        client.V1Container(
                            name=f"worker_{worker_id}_runner",
                            image=config.MANAGER_WORKER_IMAGE_NAME,
                            env=MINIO_ENV + [script_var, in_var, out_var]
                        )
                    ]
                )
            )
        )
    )

    return batch_v1.create_namespaced_job(namespace=config.MANAGER_NAMESPACE, body=job)

MINIO_ENV = [
    client.V1EnvVar(
        name="MINIO_BUCKET",
        value= config.MINIO_BUCKET
    ),
    client.V1EnvVar(
        name="MINIO_ENDPOINT",
        value=config.MINIO_ENDPOINT
    ),
    client.V1EnvVar(
        name="MINIO_ACCESS_KEY",
        value=config.MINIO_ACCESS_KEY
    ),
    client.V1EnvVar(
        name="MINIO_SECRET_KEY",
        value=config.MINIO_SECRET_KEY
    )
]

kubernetes_config.load_incluster_config()
batch_v1 = client.BatchV1Api()