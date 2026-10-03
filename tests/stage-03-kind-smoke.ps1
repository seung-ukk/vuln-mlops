param([string]$KindCommand = "kind")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$name = "stage-03-$PID"
$image = "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
$config = Join-Path ([IO.Path]::GetTempPath()) "$name.yaml"
@"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  serviceSubnet: 10.96.0.0/12
nodes:
  - role: control-plane
"@ | Set-Content -LiteralPath $config -Encoding utf8NoBOM
function Run([scriptblock]$command) { & $command; if ($LASTEXITCODE -ne 0) { throw "command failed: $LASTEXITCODE" } }
try {
  Run { & $KindCommand create cluster --name $name --image $image --config $config }
  Run { kubectl apply -k (Join-Path $root "deploy/base") }
  Run { kubectl apply -k (Join-Path $root "lab/stages/stage-02-rbac") }
  Run { kubectl apply -k (Join-Path $root "lab/stages/stage-03-monitoring") }
  foreach ($deployment in @("prometheus", "grafana", "credential-broker")) {
    kubectl rollout status "deployment/$deployment" -n stage-03-monitoring --timeout=300s
    if ($LASTEXITCODE -ne 0) {
      kubectl get pods -n stage-03-monitoring -o wide
      kubectl describe "deployment/$deployment" -n stage-03-monitoring
      kubectl logs -n stage-03-monitoring -l "app=$deployment" --all-containers --tail=100
      throw "$deployment rollout failed"
    }
  }
  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-03-monitoring/attack-client.yaml") }
  Run { kubectl wait --for=condition=Ready pod/stage-03-client -n stage-02-rbac --timeout=180s }
  Start-Sleep -Seconds 12
  $query = kubectl exec -n stage-02-rbac stage-03-client -- curl -fsS "http://grafana.stage-03-monitoring.svc:3000/api/datasources/proxy/uid/stage3-prometheus/api/v1/query?query=gitops_debug_info"
  if ($query -notmatch "stage3-lab-repo-writer" -or $query -notmatch "runtime-builder") { throw "datasource discovery failed" }
  $proof = kubectl exec -n stage-02-rbac stage-03-client -- curl -fsS "http://credential-broker.stage-03-monitoring.svc:8080/exchange/stage3-lab-repo-writer"
  if ($proof -notmatch "FLAG\{stage_3_monitoring_trust_placeholder\}" -or $proof -notmatch "SYNTHETIC_STAGE3_GIT_TOKEN") { throw "credential exchange failed" }
  foreach ($resource in @("secrets", "deployments.apps", "nodes", "nodes/proxy", "pods/exec")) {
    $answer = (kubectl auth can-i create $resource --as=system:serviceaccount:stage-02-rbac:monitoring-runner -n stage-03-monitoring).Trim()
    if ($answer -ne "no") { throw "shortcut allowed: $resource" }
  }
  Write-Output "Stage 3 datasource discovery, credential exchange, and shortcut denials verified."
} finally {
  & $KindCommand delete cluster --name $name 2>$null | Out-Null
  Remove-Item -LiteralPath $config -Force -ErrorAction SilentlyContinue
}
