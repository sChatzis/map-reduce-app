# ==========================================
# MapReduce - Delete Manager Service Only
# ==========================================

$ErrorActionPreference = "Stop"

$NAMESPACE = "mapreduce"
$K8S_DIR = Join-Path $PSScriptRoot "..\"

function Info($msg) { Write-Host "[INFO]  $msg" -ForegroundColor Green }
function Warning($msg) { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Fail($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

# ==========================================
# 1. Delete manager manifests
# ==========================================

Info "Deleting manager manifests..."

kubectl delete -f "$K8S_DIR\..\manager-statefulset.yaml" --ignore-not-found
if ($LASTEXITCODE -ne 0) { Fail "Failed to delete statefulset." }

Info "Waiting for manager pod to terminate..."
kubectl wait --for=delete pod/manager-service-0 --namespace=$NAMESPACE --timeout=60s 2>$null

kubectl delete -f "$K8S_DIR\..\manager-service.yaml" --ignore-not-found
if ($LASTEXITCODE -ne 0) { Fail "Failed to delete service." }

kubectl delete -f "$K8S_DIR\..\manager-service-account.yaml" --ignore-not-found
if ($LASTEXITCODE -ne 0) { Fail "Failed to delete service account." }

Info "Manager manifests deleted."

# ==========================================
# 2. Delete all worker jobs
# ==========================================

Info "Deleting all worker jobs in namespace $NAMESPACE..."
kubectl delete jobs -n $NAMESPACE --all --ignore-not-found --grace-period=0 --force > $null
if ($LASTEXITCODE -ne 0) { Fail "Failed to delete worker jobs." }
Info "Worker jobs deleted."

# ==========================================
# 3. Confirm deletion
# ==========================================

Write-Host ""
Info "=== Remaining Pods ==="
kubectl get pods -n $NAMESPACE -o wide

Write-Host ""
Info "=== Remaining Services ==="
kubectl get svc -n $NAMESPACE

Write-Host ""
Info "=== Remaining StatefulSets ==="
kubectl get statefulset -n $NAMESPACE