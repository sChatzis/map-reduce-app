# ==========================================
# MapReduce - Deploy Manager Service Only
# ==========================================

$ErrorActionPreference = "Stop"

$NAMESPACE = "mapreduce"
$IMAGE_NAME = "map-reduce-app-manager_service:latest"
$WORKER_IMAGE_NAME = "map-reduce-app-manager_worker:latest"
$WORKER_DOCKERFILE = Join-Path $PSScriptRoot "..\..\..\manager_worker"
$K8S_DIR = Join-Path $PSScriptRoot "..\"

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Green }
function Warning($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ==========================================
# 1. Build images
# ==========================================

Info "Building manager image: $IMAGE_NAME..."
docker build -t $IMAGE_NAME ..\\..\\
if ($LASTEXITCODE -ne 0) { Fail "Manager image build failed." }
Info "Manager image built."

Info "Building worker image: $WORKER_IMAGE_NAME..."
docker build -t $WORKER_IMAGE_NAME $WORKER_DOCKERFILE
if ($LASTEXITCODE -ne 0) { Fail "Worker image build failed." }
Info "Worker image built."

# ==========================================
# 2. Load images into cluster
# ==========================================

if (Get-Command minikube -ErrorAction SilentlyContinue) {
    Info "Loading images into minikube..."
    minikube image load $IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load manager image into minikube." }
    minikube image load $WORKER_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load worker image into minikube." }
} elseif (Get-Command kind -ErrorAction SilentlyContinue) {
    $cluster = kind get clusters 2>$null | Select-Object -First 1
    if ($cluster) {
        Info "Loading images into kind cluster: $cluster..."
        kind load docker-image $IMAGE_NAME --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load manager image into kind." }
        kind load docker-image $WORKER_IMAGE_NAME --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load worker image into kind." }
    }
} else {
    Warning "Neither minikube nor kind detected - skipping image load."
}

# ==========================================
# 3. Apply manager manifests
# ==========================================

Info "Applying manager manifests..."

kubectl apply -f "$K8S_DIR\..\manager-service-account.yaml" --namespace=$NAMESPACE
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply service account." }

kubectl delete -f "$K8S_DIR\..\manager-service.yaml" --namespace=$NAMESPACE --ignore-not-found
kubectl apply -f "$K8S_DIR\..\manager-service.yaml" --namespace=$NAMESPACE
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply service." }

kubectl apply -f "$K8S_DIR\..\manager-statefulset.yaml" --namespace=$NAMESPACE
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply statefulset." }

Info "Manifests applied."

# ==========================================
# 4. Wait for rollout
# ==========================================

Info "Waiting for manager-service rollout..."
kubectl rollout status statefulset/manager-service --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "Rollout failed or timed out." }
Info "Rollout complete."

# ==========================================
# 5. Health checks
# ==========================================

Write-Host ""
Info "=== Health Checks ==="

Write-Host ""
Info "Pods:"
kubectl get pods -n $NAMESPACE -o wide

Write-Host ""
Info "Pod readiness:"
kubectl wait --for=condition=Ready pod -l app=manager-service -n $NAMESPACE --timeout=30s

Write-Host ""
Info "Container logs:"
kubectl logs -n $NAMESPACE -l app=manager-service --tail=100

Write-Host ""
Info "kubectl logs -n mapreduce manager-service-0 -f"