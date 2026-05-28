# ==========================================
# MapReduce - Deploy Manager Service Only
# ==========================================

$ErrorActionPreference = "Stop"

$NAMESPACE = "mapreduce"
$MANAGER_IMAGE_NAME = "map-reduce-app-manager-service:latest"
$MANAGER_DOCKERFILE = Join-Path $PSScriptRoot "..\..\manager_service"
$WORKER_IMAGE_NAME = "map-reduce-app-manager-worker:latest"
$WORKER_DOCKERFILE = Join-Path $PSScriptRoot "..\..\manager_worker"
$K8S_DIR = Join-Path $PSScriptRoot "..\"

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Green }
function Warning($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ==========================================
# 1. Build images
# ==========================================

Info "Building manager image: $MANAGER_IMAGE_NAME..."
docker build -t $MANAGER_IMAGE_NAME $MANAGER_DOCKERFILE
if ($LASTEXITCODE -ne 0) { Fail "Manager image build failed." }
Info "Manager image built."

$workerExists = docker images -q $WORKER_IMAGE_NAME
if ($workerExists) {
    Info "Worker image '$WORKER_IMAGE_NAME' already exists, skipping build."
} else {
    Info "Building worker image: $WORKER_IMAGE_NAME..."
    docker build -t $WORKER_IMAGE_NAME $WORKER_DOCKERFILE
    if ($LASTEXITCODE -ne 0) {
        Fail "Worker image build failed."
    }
    Info "Worker image built."
}

# ==========================================
# 2. Load images into cluster
# ==========================================

if (Get-Command minikube -ErrorAction SilentlyContinue) {
    Info "Loading images into minikube..."
    minikube image load $MANAGER_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load manager image into minikube." }
    minikube image load $WORKER_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load worker image into minikube." }
} elseif (Get-Command kind -ErrorAction SilentlyContinue) {
    $cluster = kind get clusters 2>$null | Select-Object -First 1
    if ($cluster) {
        Info "Loading images into kind cluster: $cluster..."
        kind load docker-image $MANAGER_IMAGE_NAME --name $cluster
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

kubectl apply -f "$K8S_DIR..\manager_service\manager-service-account.yaml" --namespace=$NAMESPACE
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply service account." }

kubectl delete -f "$K8S_DIR..\manager_service\manager-service.yaml" --namespace=$NAMESPACE --ignore-not-found
kubectl apply -f "$K8S_DIR..\manager_service\manager-service.yaml" --namespace=$NAMESPACE
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply service." }

kubectl apply -f "$K8S_DIR..\manager_service\manager-statefulset.yaml" --namespace=$NAMESPACE
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
Info "Pods:"
kubectl get pods -n $NAMESPACE -o wide

Write-Host ""
Info "kubectl logs -n mapreduce manager-service-0 -f"