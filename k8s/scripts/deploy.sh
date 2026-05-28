#!/bin/sh
set -e

NAMESPACE="mapreduce"
ENV_FILE="../../../.env"

IMAGE_NAME="map-reduce-app-manager_service:latest"
WORKER_IMAGE_NAME="map-reduce-app-manager_worker:latest"

POSTGRES_IMAGE="postgres:15"
MINIO_IMAGE="minio/minio:latest"
ADMINER_IMAGE="adminer:latest"

Info() { printf "[INFO] %s\n" "$1"; }
Fail() { printf "[ERROR] %s\n" "$1"; exit 1; }

EnsureImage() {
    img="$1"
    docker images -q "$img" | grep -q . || docker pull "$img"
}

Info "Starting parallel image preparation..."

# Parallel pulls (background jobs)
EnsureImage "$POSTGRES_IMAGE" &
PID1=$!

EnsureImage "$MINIO_IMAGE" &
PID2=$!

EnsureImage "$ADMINER_IMAGE" &
PID3=$!

wait $PID1 $PID2 $PID3 || Fail "Image pulls failed"

Info "Pulls complete."

Info "Building images in parallel..."

docker build -t "$IMAGE_NAME" "../../.." &
B1=$!

docker build -t "$WORKER_IMAGE_NAME" "../../../manager_worker" &
B2=$!

wait $B1 $B2 || Fail "Build failed"

Info "Builds complete."

# Continue deployment normally...
kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f - >/dev/null

Info "Done setup phase."