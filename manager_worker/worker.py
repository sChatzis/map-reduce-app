from minio import Minio

import os
import subprocess
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing env var: {name}")
    return value


client = Minio(
    require_env("MINIO_ENDPOINT"),
    access_key=require_env("MINIO_ACCESS_KEY"),
    secret_key=require_env("MINIO_SECRET_KEY"),
    secure=False
)

bucket = require_env("MINIO_BUCKET")
script_obj = require_env("SCRIPT_OBJECT")
in_obj = require_env("INPUT_OBJECT")
out_obj = require_env("OUTPUT_OBJECT")

logger.info("Downloading script...")
client.fget_object(bucket, script_obj, "/tmp/script.py")

in_ext = os.path.splitext(in_obj)[1]
out_ext = os.path.splitext(out_obj)[1]

local_in = f"/tmp/input{in_ext}"
local_out = f"/tmp/output{out_ext}"

logger.info("Downloading input...")
client.fget_object(bucket, in_obj, local_in)

logger.info("Executing script...")

try:
    result = subprocess.run(
        ["python", "/tmp/script.py", local_in, local_out],
        capture_output=True,
        text=True
    )


except subprocess.CalledProcessError as e:
    logger.error(f"Script failed: {e.stderr}")
    raise
except subprocess.TimeoutExpired:
    logger.error("Script timed out")
    raise

if result.stdout:
    logger.info(result.stdout)

if result.stderr:
    logger.warning(result.stderr)

logger.info("Uploading output...")

if not os.path.exists(local_out):
    raise RuntimeError(f"Output file not created: {local_out}")

client.fput_object(bucket, out_obj, local_out)

logger.info("Job completed successfully")
