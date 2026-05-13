from minio import Minio
import os, subprocess

client = Minio(
    os.environ["MINIO_ENDPOINT"],
    access_key=os.environ["MINIO_ACCESS_KEY"],
    secret_key=os.environ["MINIO_SECRET_KEY"],
    secure=False
)

bucket = os.environ["MINIO_BUCKET"]
client.fget_object(bucket, os.environ["SCRIPT_OBJECT"], "/tmp/script.py")

in_obj = os.environ["INPUT_OBJECT"]
out_obj = os.environ["OUTPUT_OBJECT"]

in_type = os.path.splitext(in_obj)[1]
out_type = os.path.splitext(out_obj)[1]

local_in = f"/tmp/input" + in_type
local_out = f"/tmp/output" + out_type

client.fget_object(bucket, in_obj, local_in)

subprocess.run(["python", "/tmp/script.py"], check=True)

client.fput_object(bucket, out_obj, local_out)