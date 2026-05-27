#!/bin/sh

# ==========================================
# MapReduce Kubernetes Teardown Script
# POSIX-compliant version
# ==========================================

set -e

NAMESPACE="mapreduce"
SECRET_NAME="manager-env"

Info() { printf "\033[0;32m[INFO]\033[0m  %s\n" "$1"; }
Warning() { printf "\033[1;33m[WARN]\033[0m  %s\n" "$1"; }
Fail() { printf "\033[0;31m[ERROR]\033[0m %s\n" "$1"; exit 1; }

# ==========================================
# 1. Delete worker jobs
# ==========================================

echo ""
Info "Deleting worker jobs..."
kubectl delete jobs --all --namespace="$NAMESPACE" --ignore-not-found
Info "Worker jobs deleted."

# ==========================================
# 2. Delete manager
# ==========================================

Info "Deleting manager statefulset..."
kubectl delete statefulset manager-service --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting manager service..."
kubectl delete service manager-service --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting manager RBAC..."
kubectl delete rolebinding manager-rolebinding --namespace="$NAMESPACE" --ignore-not-found
kubectl delete role manager-role --namespace="$NAMESPACE" --ignore-not-found
kubectl delete serviceaccount manager-sa --namespace="$NAMESPACE" --ignore-not-found

Info "Manager deleted."

# ==========================================
# 3. Delete worker image
# ==========================================

Info "Cleaning worker image from local environment..."

if [ -n "$WORKER_IMAGE_NAME" ]; then
    docker rmi "$WORKER_IMAGE_NAME" -f 2>/dev/null || true
fi

if command -v minikube >/dev/null 2>&1; then
    minikube image rm "$WORKER_IMAGE_NAME" 2>/dev/null || true
fi

Info "Image cleanup completed."

# ==========================================
# 4. Delete Adminer
# ==========================================

Info "Deleting Adminer deployment..."
kubectl delete deployment adminer --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting Adminer service..."
kubectl delete service adminer --namespace="$NAMESPACE" --ignore-not-found

Info "Adminer deleted."

# ==========================================
# 5. Delete MinIO
# ==========================================

Info "Deleting MinIO statefulset..."
kubectl delete statefulset minio --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting MinIO service..."
kubectl delete service minio --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting MinIO PVC..."
kubectl delete pvc minio-pvc --namespace="$NAMESPACE" --ignore-not-found

Info "MinIO deleted."

# ==========================================
# 6. Delete Postgres
# ==========================================

Info "Deleting Postgres statefulset..."
kubectl delete statefulset jobs-db --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting Postgres service..."
kubectl delete service jobs-db --namespace="$NAMESPACE" --ignore-not-found

Info "Deleting Postgres PVC..."
kubectl delete pvc jobs-postgres-pvc --namespace="$NAMESPACE" --ignore-not-found

Info "Postgres deleted."

# ==========================================
# 7. Delete secret
# ==========================================

Info "Deleting secret..."
kubectl delete secret "$SECRET_NAME" --namespace="$NAMESPACE" --ignore-not-found

Info "Secret deleted."

# ==========================================
# 8. Delete namespace
# ==========================================

Info "Deleting namespace: $NAMESPACE..."
kubectl delete namespace "$NAMESPACE" --ignore-not-found

Info "Namespace deleted."

# ==========================================
# 9. Print status
# ==========================================

echo ""
Info "=== Remaining Resources ==="

kubectl get all -n "$NAMESPACE" 2>/dev/null || true
kubectl get pvc -n "$NAMESPACE" 2>/dev/null || true