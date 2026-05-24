# ==========================================
# MapReduce Kubernetes Deploy Script
# ==========================================

$ErrorActionPreference = "Stop"

$NAMESPACE = "mapreduce"
$ENV_FILE = "..\..\..\.env"
$SECRET_NAME = "manager-env"
$IMAGE_NAME = "map-reduce-app-manager_service:latest"
$WORKER_IMAGE_NAME = "map-reduce-app-manager_worker:latest"
$WORKER_DOCKERFILE = Join-Path $PSScriptRoot "..\..\..\manager_worker"
$K8S_DIR = Join-Path $PSScriptRoot "..\"
$POSTGRES_IMAGE = "postgres:15"
$MINIO_IMAGE = "minio/minio:latest"
$ADMINER_IMAGE = "adminer:latest"

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Green }
function Warning($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

function EnsureImage($image) {
    $existing = docker images -q $image
    if ($existing) {
        Info "Image '$image' already exists, skipping pull."
    } else {
        Info "Pulling image: $image..."
        docker pull $image
        if ($LASTEXITCODE -ne 0) {
            Fail "Failed to pull image: $image"
        }
        Info "Image '$image' pulled."
    }
}

# ==========================================
# 1. Preflight checks
# ==========================================

Info "Running preflight checks..."

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Fail "kubectl not found"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "docker not found"
}

if (-not (Test-Path $ENV_FILE)) {
    Fail ".env file not found. Copy .env.example to .env and fill in the secrets."
}

$envContent = Get-Content $ENV_FILE

$sensitiveKeys = "USER_DB_PASSWORD", "JWT_SECRET_KEY", "JOBS_DB_PASSWORD", "MINIO_SECRET_KEY"

foreach ($key in $sensitiveKeys) {
    $found = $false
    foreach ($line in $envContent) {
        if ($line -match "^${key}=(.+)$") {
            $found = $true
            break
        }
    }
    if (-not $found) {
        Fail "$key is empty in $ENV_FILE - fill in all secrets before deploying."
    }
}

Info "Preflight checks passed."

# ==========================================
# 2. Create namespace
# ==========================================

Info "Creating namespace: $NAMESPACE..."
$nsExists = kubectl get namespace $NAMESPACE --ignore-not-found

if ($nsExists) {
    Warning "Namespace $NAMESPACE already exists, skipping."
} else {
    kubectl create namespace $NAMESPACE
    if ($LASTEXITCODE -ne 0) {
        Fail "Failed to create namespace."
    }
}

# ==========================================
# 3. Create / update secret from .env
# ==========================================

Info "Applying secret: $SECRET_NAME..."
$secretYaml = kubectl create secret generic $SECRET_NAME --from-env-file=$ENV_FILE --namespace=$NAMESPACE --dry-run=client -o yaml
$secretYaml | kubectl apply -f -
if ($LASTEXITCODE -ne 0) {
    Fail "Failed to apply secret."
}
Info "Secret applied."

# ==========================================
# 4. Build manager image
# ==========================================

Info "Building manager image: $IMAGE_NAME..."
docker build -t $IMAGE_NAME ..\\..\\
if ($LASTEXITCODE -ne 0) {
    Fail "Manager image build failed."
}
Info "Manager image built."

# ==========================================
# 5. Build worker image
# ==========================================

Info "Building worker image: $WORKER_IMAGE_NAME..."
docker build -t $WORKER_IMAGE_NAME $WORKER_DOCKERFILE
if ($LASTEXITCODE -ne 0) {
    Fail "Worker image build failed."
}
Info "Worker image built."

# ==========================================
# 6. Pull external images if needed
# ==========================================

EnsureImage $POSTGRES_IMAGE
EnsureImage $MINIO_IMAGE
EnsureImage $ADMINER_IMAGE

# ==========================================
# 7. Load images into cluster
# ==========================================

if (Get-Command minikube -ErrorAction SilentlyContinue) {
    Info "Loading images into minikube..."
    minikube image load $IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load manager image into minikube." }
    minikube image load $WORKER_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load worker image into minikube." }
    minikube image load $POSTGRES_IMAGE
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load postgres image into minikube." }
    minikube image load $MINIO_IMAGE
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load minio image into minikube." }
    minikube image load $ADMINER_IMAGE
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load adminer image into minikube." }
} elseif (Get-Command kind -ErrorAction SilentlyContinue) {
    $cluster = kind get clusters 2>$null | Select-Object -First 1
    if ($cluster) {
        Info "Loading images into kind cluster: $cluster..."
        kind load docker-image $IMAGE_NAME --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load manager image into kind." }
        kind load docker-image $WORKER_IMAGE_NAME --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load worker image into kind." }
        kind load docker-image $POSTGRES_IMAGE --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load postgres image into kind." }
        kind load docker-image $MINIO_IMAGE --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load minio image into kind." }
        kind load docker-image $ADMINER_IMAGE --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load adminer image into kind." }
    }
} else {
    Warning "Neither minikube nor kind detected - skipping image load."
}

# ==========================================
# 8. Apply Postgres manifests
# ==========================================

Info "Applying Postgres manifests..."

kubectl apply -f "$K8S_DIR\jobs_db\jobs-postgres-pvc.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply Postgres PVC." }

kubectl apply -f "$K8S_DIR\jobs_db\jobs-postgres-statefulset.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply Postgres StatefulSet." }

kubectl apply -f "$K8S_DIR\jobs_db\jobs-postgres-service.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply Postgres Service." }

Info "Waiting for Postgres to be ready..."
kubectl rollout status statefulset/jobs-db --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "Postgres rollout failed or timed out." }
Info "Postgres ready."

# ==========================================
# 9. Apply MinIO manifests
# ==========================================

Info "Applying MinIO manifests..."

kubectl apply -f "$K8S_DIR\minio\minio-pvc.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply MinIO PVC." }

kubectl apply -f "$K8S_DIR\minio\minio-statefulset.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply MinIO StatefulSet." }

kubectl delete -f "$K8S_DIR\minio\minio-service.yaml" --ignore-not-found
kubectl apply -f "$K8S_DIR\minio\minio-service.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply MinIO Service." }

Info "Waiting for MinIO to be ready..."
kubectl rollout status statefulset/minio --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "MinIO rollout failed or timed out." }
Info "MinIO ready. Access console at http://localhost:30001"

# ==========================================
# 10. Apply Adminer manifests
# ==========================================

Info "Applying Adminer manifests..."

kubectl apply -f "$K8S_DIR\adminer\adminer.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply Adminer." }

Info "Waiting for Adminer to be ready..."
kubectl rollout status deployment/adminer --namespace=$NAMESPACE --timeout=60s
if ($LASTEXITCODE -ne 0) { Fail "Adminer rollout failed or timed out." }
Info "Adminer ready. Access at http://localhost:30002"

# ==========================================
# 11. Apply manager manifests
# ==========================================

Info "Applying manager manifests..."

kubectl apply -f "$K8S_DIR\..\manager-service-account.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply service account." }

kubectl delete -f "$K8S_DIR\..\manager-service.yaml" --ignore-not-found
kubectl apply -f "$K8S_DIR\..\manager-service.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply service." }

kubectl apply -f "$K8S_DIR\..\manager-statefulset.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply statefulset." }

Info "Manifests applied."

# ==========================================
# 12. Wait for manager rollout
# ==========================================

Info "Waiting for manager-service rollout..."
kubectl rollout status statefulset/manager-service --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "Rollout failed or timed out." }
Info "Rollout complete."

# ==========================================
# 13. Print health checks
# ==========================================

Write-Host ""
Info "=== Health Checks ==="

Write-Host ""
Info "Pods:"
kubectl get pods -n $NAMESPACE -o wide

Write-Host ""
Info "Services:"
kubectl get svc -n $NAMESPACE

Write-Host ""
Info "StatefulSets:"
kubectl get statefulset -n $NAMESPACE

Write-Host ""
Info "Pod readiness:"
kubectl wait --for=condition=Ready pod -l app=manager-service -n $NAMESPACE --timeout=30s

Write-Host ""
Info "Recent events:"
kubectl get events -n $NAMESPACE --sort-by=.metadata.creationTimestamp

Write-Host ""
Info "Container logs:"
kubectl logs -n $NAMESPACE -l app=manager-service --tail=100

Write-Host ""
Info "=== Access Points ==="
Info "Manager API:    http://localhost:30000"
Info "MinIO Console:  http://localhost:30001"
Info "Adminer:        http://localhost:30002"

Write-Host ""
Info "kubectl logs -n mapreduce manager-service-0 -f"