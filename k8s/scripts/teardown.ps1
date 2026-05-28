# ==========================================
# MapReduce Kubernetes Teardown Script
# ==========================================

$NAMESPACE = "mapreduce"
$SECRET_NAME = "manager-env"
$WORKER_IMAGE_NAME = "map-reduce-app-manager_worker:latest"
$AUTH_IMAGE_NAME = "map-reduce-app-auth-service:latest"
$CLI_IMAGE_NAME = "map-reduce-app-cli:latest"

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Green }
function Warning($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ==========================================
# 1. Delete worker jobs
# ==========================================

Write-Host ""
Info "Deleting worker jobs..."
kubectl delete jobs --all --namespace=$NAMESPACE --ignore-not-found --grace-period=0 --force > $null
Info "Worker jobs deleted."

# ==========================================
# 2. Delete manager
# ==========================================

Info "Deleting manager statefulset..."
kubectl delete statefulset manager-service --namespace=$NAMESPACE --ignore-not-found
Info "Deleting manager service..."
kubectl delete service manager-service --namespace=$NAMESPACE --ignore-not-found
Info "Deleting manager RBAC..."
kubectl delete rolebinding manager-rolebinding --namespace=$NAMESPACE --ignore-not-found
kubectl delete role manager-role --namespace=$NAMESPACE --ignore-not-found
kubectl delete serviceaccount manager-sa --namespace=$NAMESPACE --ignore-not-found
Info "Manager deleted."

# ==========================================
# 3. Delete ui-service
# ==========================================

Info "Deleting ui-service deployment..."
kubectl delete deployment ui-service --namespace=$NAMESPACE --ignore-not-found
Info "Deleting ui-service service..."
kubectl delete service ui-service-lb --namespace=$NAMESPACE --ignore-not-found
Info "UI-service deleted."

# ==========================================
# 4. Delete auth-service
# ==========================================

Info "Deleting auth-service statefulset..."
kubectl delete statefulset auth-service --namespace=$NAMESPACE --ignore-not-found
Info "Deleting auth-service service..."
kubectl delete service auth-service --namespace=$NAMESPACE --ignore-not-found
Info "Auth-service deleted."

# ==========================================
# 5. Delete worker image
# ==========================================

Info "Cleaning images from local environment..."

docker rmi $WORKER_IMAGE_NAME -f 2>$null
docker rmi $AUTH_IMAGE_NAME -f 2>$null
docker rmi $CLI_IMAGE_NAME -f 2>$null

if (Get-Command minikube -ErrorAction SilentlyContinue) {
    minikube image rm $WORKER_IMAGE_NAME 2>$null
    minikube image rm $AUTH_IMAGE_NAME 2>$null
    minikube image rm $CLI_IMAGE_NAME 2>$null
}

Info "Image cleanup completed."

# ==========================================
# 6. Delete Adminer
# ==========================================

Info "Deleting Adminer deployment..."
kubectl delete deployment adminer --namespace=$NAMESPACE --ignore-not-found
Info "Deleting Adminer service..."
kubectl delete service adminer --namespace=$NAMESPACE --ignore-not-found
Info "Adminer deleted."

# ==========================================
# 7. Delete MinIO
# ==========================================

Info "Deleting MinIO statefulset..."
kubectl delete statefulset minio --namespace=$NAMESPACE --ignore-not-found
Info "Deleting MinIO service..."
kubectl delete service minio --namespace=$NAMESPACE --ignore-not-found
Info "MinIO deleted."
Info "Deleting MinIO PVC..."
kubectl delete pvc minio-pvc --namespace=$NAMESPACE --ignore-not-found
Info "MinIO PVC deleted."

# ==========================================
# 8. Delete jobs-db
# ==========================================

Info "Deleting jobs-db statefulset..."
kubectl delete statefulset jobs-db --namespace=$NAMESPACE --ignore-not-found
Info "Deleting jobs-db service..."
kubectl delete service jobs-db --namespace=$NAMESPACE --ignore-not-found
Info "jobs-db deleted."
Info "Deleting jobs-db PVC..."
kubectl delete pvc jobs-postgres-pvc --namespace=$NAMESPACE --ignore-not-found
Info "jobs-db PVC deleted."

# ==========================================
# 9. Delete user-db
# ==========================================

Info "Deleting user-db statefulset..."
kubectl delete statefulset user-db --namespace=$NAMESPACE --ignore-not-found
Info "Deleting user-db service..."
kubectl delete service user-db --namespace=$NAMESPACE --ignore-not-found
Info "user-db deleted."
Info "Deleting user-db PVC..."
kubectl delete pvc user-postgres-pvc --namespace=$NAMESPACE --ignore-not-found
Info "user-db PVC deleted."

# ==========================================
# 10. Delete secret
# ==========================================

Info "Deleting secret..."
kubectl delete secret $SECRET_NAME --namespace=$NAMESPACE --ignore-not-found
Info "Secret deleted."

# ==========================================
# 11. Delete namespace
# ==========================================

Info "Deleting namespace: $NAMESPACE..."
kubectl delete namespace $NAMESPACE --ignore-not-found
Info "Namespace deleted."

# ==========================================
# 12. Print status
# ==========================================

Write-Host ""
Info "=== Remaining Resources ==="
kubectl get all -n $NAMESPACE 2>$null
kubectl get pvc -n $NAMESPACE 2>$null