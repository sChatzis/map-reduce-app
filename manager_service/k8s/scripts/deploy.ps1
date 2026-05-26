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
$AUTH_IMAGE_NAME = "map-reduce-app-auth-service:latest"
$AUTH_DOCKERFILE = Join-Path $PSScriptRoot "..\..\..\authentication_service"
$CLI_IMAGE_NAME = "map-reduce-app-cli:latest"
$CLI_DOCKERFILE = Join-Path $PSScriptRoot "..\..\..\ui_service"

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
# 6. Build auth image
# ==========================================

Info "Building auth image: $AUTH_IMAGE_NAME..."
docker build -t $AUTH_IMAGE_NAME $AUTH_DOCKERFILE
if ($LASTEXITCODE -ne 0) { Fail "Auth image build failed." }
Info "Auth image built."

# ==========================================
# 7. Build CLI (UI) image
# ==========================================

Info "Building CLI image: $CLI_IMAGE_NAME..."
docker build -t $CLI_IMAGE_NAME $CLI_DOCKERFILE
if ($LASTEXITCODE -ne 0) { Fail "CLI image build failed." }
Info "CLI image built."

# ==========================================
# 8. Pull external images if needed
# ==========================================

EnsureImage $POSTGRES_IMAGE
EnsureImage $MINIO_IMAGE
EnsureImage $ADMINER_IMAGE

# ==========================================
# 9. Load images into cluster
# ==========================================

if (Get-Command minikube -ErrorAction SilentlyContinue) {
    Info "Loading images into minikube..."
    minikube image load $IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load manager image into minikube." }
    minikube image load $WORKER_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load worker image into minikube." }
    minikube image load $AUTH_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load auth image into minikube." }
    minikube image load $CLI_IMAGE_NAME
    if ($LASTEXITCODE -ne 0) { Fail "Failed to load CLI image into minikube." }
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
        kind load docker-image $AUTH_IMAGE_NAME --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load auth image into kind." }
        kind load docker-image $CLI_IMAGE_NAME --name $cluster
        if ($LASTEXITCODE -ne 0) { Fail "Failed to load CLI image into kind." }
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
# 10. Apply jobs-db manifests
# ==========================================

Info "Applying jobs-db manifests..."

kubectl apply -f "$K8S_DIR\jobs_db\jobs-postgres-pvc.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply jobs-db PVC." }

kubectl apply -f "$K8S_DIR\jobs_db\jobs-postgres-statefulset.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply jobs-db StatefulSet." }

kubectl apply -f "$K8S_DIR\jobs_db\jobs-postgres-service.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply jobs-db Service." }

Info "Waiting for jobs-db to be ready..."
kubectl rollout status statefulset/jobs-db --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "jobs-db rollout failed or timed out." }
Info "jobs-db ready."

# ==========================================
# 11. Apply user-db manifests
# ==========================================

Info "Applying user-db manifests..."

kubectl apply -f "$K8S_DIR\user_db\user-postgres-pvc.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply user-db PVC." }

kubectl apply -f "$K8S_DIR\user_db\user-postgres-statefulset.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply user-db StatefulSet." }

kubectl apply -f "$K8S_DIR\user_db\user-postgres-service.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply user-db Service." }

Info "Waiting for user-db to be ready..."
kubectl rollout status statefulset/user-db --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "user-db rollout failed or timed out." }
Info "user-db ready."

# ==========================================
# 12. Apply MinIO manifests
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
Info "MinIO ready."

# ==========================================
# 13. Apply Adminer manifests
# ==========================================

Info "Applying Adminer manifests..."

kubectl apply -f "$K8S_DIR\adminer\adminer.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply Adminer." }

Info "Waiting for Adminer to be ready..."
kubectl rollout status deployment/adminer --namespace=$NAMESPACE --timeout=60s
if ($LASTEXITCODE -ne 0) { Fail "Adminer rollout failed or timed out." }
Info "Adminer ready."

# ==========================================
# 14. Apply auth-service manifests
# ==========================================

Info "Applying auth-service manifests..."

kubectl delete -f "$K8S_DIR\..\..\authentication_service\auth-service.yaml" --ignore-not-found
kubectl apply -f "$K8S_DIR\..\..\authentication_service\auth-service.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply auth service." }

kubectl apply -f "$K8S_DIR\..\..\authentication_service\auth-statefulset.yaml"
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply auth statefulset." }

Info "Waiting for auth-service rollout..."
kubectl rollout status statefulset/auth-service --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "Auth-service rollout failed or timed out." }
Info "Auth-service ready."

# ==========================================
# 15. Apply ui-service manifests
# ==========================================

Info "Applying UI-service manifests..."

kubectl apply -f "$K8S_DIR\..\..\ui_service\ui-service.yaml" --namespace=$NAMESPACE
if ($LASTEXITCODE -ne 0) { Fail "Failed to apply UI-service." }

Info "Waiting for UI-service rollout..."
kubectl rollout status deployment/ui-service --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "UI-service rollout failed or timed out." }
Info "UI-service ready."

# ==========================================
# 16. Apply manager manifests
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
# 17. Wait for manager rollout
# ==========================================

Info "Waiting for manager-service rollout..."
kubectl rollout status statefulset/manager-service --namespace=$NAMESPACE --timeout=120s
if ($LASTEXITCODE -ne 0) { Fail "Rollout failed or timed out." }
Info "Rollout complete."

# ==========================================
# 18. Print health checks
# ==========================================

Write-Host ""
Info "Pods:"
kubectl get pods -n $NAMESPACE -o wide

Write-Host ""
Info "=== Access Points ==="
Info "UI:             http://localhost:30000"
Info "Manager API:    http://localhost:30001"
Info "MinIO Console:  http://localhost:30002"
Info "Adminer:        http://localhost:30003"

Write-Host ""
Info "kubectl logs -n mapreduce manager-service-0 -f"
Info "kubectl exec -it -n mapreduce deployment/ui-service -- /bin/bash"