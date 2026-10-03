param([string]$KindCommand = "kind")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$name = "stage-04-$PID"
$tmp = Join-Path ([IO.Path]::GetTempPath()) "vuln-mlops-$name"
$audit = Join-Path $tmp "audit"
$config = Join-Path $tmp "kind.yaml"
$portLog = Join-Path $tmp "port-forward.log"
$portErrorLog = Join-Path $tmp "port-forward-error.log"
New-Item -ItemType Directory -Force $audit | Out-Null
$auditPolicy = (Resolve-Path (Join-Path $root "lab/stages/stage-04-gitops/audit-policy.yaml")).Path
@"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking: {serviceSubnet: 10.96.0.0/12}
nodes:
  - role: control-plane
    extraMounts:
      - {hostPath: '$auditPolicy', containerPath: /etc/kubernetes/stage-04-audit.yaml, readOnly: true}
      - {hostPath: '$audit', containerPath: /var/log/kubernetes}
    kubeadmConfigPatches:
      - |
        kind: ClusterConfiguration
        apiServer:
          extraArgs:
            audit-policy-file: /etc/kubernetes/stage-04-audit.yaml
            audit-log-path: /var/log/kubernetes/audit.log
          extraVolumes:
            - {name: audit-policy, hostPath: /etc/kubernetes/stage-04-audit.yaml, mountPath: /etc/kubernetes/stage-04-audit.yaml, readOnly: true, pathType: File}
            - {name: audit-log, hostPath: /var/log/kubernetes, mountPath: /var/log/kubernetes, pathType: DirectoryOrCreate}
"@ | Set-Content $config -Encoding utf8NoBOM
function Run([scriptblock]$c) { & $c; if ($LASTEXITCODE -ne 0) { throw "command failed: $LASTEXITCODE" } }
$pf = $null
try {
  Run { & $KindCommand create cluster --name $name --image "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5" --config $config }
  Run { kubectl create namespace stage-02-rbac }
  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-04-gitops/vendor/application-crd-v3.5.3.yaml") --server-side }
  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-04-gitops/vendor/appproject-crd-v3.5.3.yaml") --server-side }
  Run { kubectl apply -f (Join-Path $root "lab/stages/stage-04-gitops/vendor/applicationset-crd-v3.5.3.yaml") --server-side }
  Run { kubectl wait --for=condition=Established crd/applications.argoproj.io crd/appprojects.argoproj.io --timeout=120s }
  Run { kubectl apply -k (Join-Path $root "lab/stages/stage-04-gitops") --server-side }
  foreach($workload in @("deployment/gitea", "deployment/argocd-repo-server", "deployment/argocd-redis", "statefulset/argocd-application-controller")) {
    kubectl rollout status $workload -n stage-04-gitops --timeout=600s
    if($LASTEXITCODE -ne 0) {
      kubectl get pods -n stage-04-gitops -o wide
      kubectl describe $workload -n stage-04-gitops
      kubectl logs -n stage-04-gitops --all-containers --prefix --tail=100 -l app=gitea
      throw "$workload rollout failed"
    }
  }
  $controller = "system:serviceaccount:stage-04-gitops:argocd-application-controller"
  foreach($check in @(
    @("create", "deployments.apps"),
    @("create", "secrets"),
    @("create", "roles.rbac.authorization.k8s.io")
  )) {
    $answer = (kubectl auth can-i @check -n stage-04-gitops "--as=$controller").Trim()
    if($answer -ne "no") { throw "Argo shortcut allowed: $($check -join ' ')" }
  }
  Run { kubectl create deployment other-workload -n stage-04-gitops --image=nginxinc/nginx-unprivileged:1.29.1-alpine }
  $nameEscape = (kubectl patch deployment other-workload -n stage-04-gitops --type=merge --patch '{"metadata":{"annotations":{"stage4":"denied"}}}' "--as=$controller" 2>&1 | Out-String)
  if($LASTEXITCODE -eq 0 -or $nameEscape -notmatch "Forbidden") {
    throw "Argo resource-name shortcut was not rejected as Forbidden: $nameEscape"
  }
  Run { kubectl exec -n stage-04-gitops deploy/gitea -- gitea admin user create --config /etc/gitea/app.ini --username stage3-lab-writer --password SYNTHETIC_STAGE3_GIT_TOKEN --email lab@example.invalid --must-change-password=false }
  $pf = Start-Process kubectl -ArgumentList @("port-forward", "-n", "stage-04-gitops", "svc/gitea", "33000:3000") -RedirectStandardOutput $portLog -RedirectStandardError $portErrorLog -WindowStyle Hidden -PassThru
  foreach($i in 1..30) { try { Invoke-RestMethod http://127.0.0.1:33000/api/healthz | Out-Null; break } catch { Start-Sleep 1 } }
  $auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("stage3-lab-writer:SYNTHETIC_STAGE3_GIT_TOKEN"))
  Invoke-RestMethod http://127.0.0.1:33000/api/v1/user/repos -Method Post -Headers @{Authorization="Basic $auth"} -ContentType application/json -Body '{"name":"vuln-mlops-gitops","private":true}' | Out-Null
  $pod = (kubectl get pod -n stage-04-gitops -l app=gitea -o jsonpath='{.items[0].metadata.name}').Trim()
  $hook = [Convert]::ToBase64String([IO.File]::ReadAllBytes((Join-Path $root "lab/stages/stage-04-gitops/scope-hook.sh")))
  Run { kubectl exec -n stage-04-gitops $pod -- sh -c "mkdir -p /var/lib/gitea/git/repositories/stage3-lab-writer/vuln-mlops-gitops.git/hooks/pre-receive.d; echo $hook | base64 -d > /var/lib/gitea/git/repositories/stage3-lab-writer/vuln-mlops-gitops.git/hooks/pre-receive.d/scope; chmod 755 /var/lib/gitea/git/repositories/stage3-lab-writer/vuln-mlops-gitops.git/hooks/pre-receive.d/scope" }
  $repo = Join-Path $tmp "repo"; New-Item -ItemType Directory -Force (Join-Path $repo "runtime-builder") | Out-Null
  Copy-Item (Join-Path $root "lab/stages/stage-04-gitops/runtime-builder-base.yaml") (Join-Path $repo "runtime-builder/deployment.yaml")
  Push-Location $repo
  Run { git init -b stage4-lab }; Run { git config user.email lab@example.invalid }; Run { git config user.name stage3-lab-writer }
  Run { git add . }; Run { git commit -m baseline }; Run { git remote add origin "http://stage3-lab-writer:SYNTHETIC_STAGE3_GIT_TOKEN@127.0.0.1:33000/stage3-lab-writer/vuln-mlops-gitops.git" }; Run { git push -u origin stage4-lab }
  Set-Content forbidden.txt "denied"
  Run { git add forbidden.txt }; Run { git commit -m 'attempt forbidden path' }
  git push origin stage4-lab 2>$null
  if($LASTEXITCODE -eq 0) { throw "Git path shortcut was accepted" }
  Run { git reset --hard HEAD~1 }
  Run { git switch -c main }
  git push origin main 2>$null
  if($LASTEXITCODE -eq 0) { throw "Git branch shortcut was accepted" }
  Run { git switch stage4-lab }; Run { git branch -D main }
  Copy-Item (Join-Path $root "lab/stages/stage-04-gitops/repository/runtime-builder/deployment.yaml") (Join-Path $repo "runtime-builder/deployment.yaml") -Force
  Run { git add . }; Run { git commit -m 'control runtime-builder' }; $sha=(git rev-parse HEAD).Trim(); Run { git push origin stage4-lab }
  Pop-Location
  $ok=$false; foreach($i in 1..60) { $mode=kubectl get deploy runtime-builder -n stage-04-gitops -o jsonpath='{.spec.template.spec.containers[0].env[0].value}'; if($mode -eq "git-controlled"){$ok=$true;break}; Start-Sleep 3 }
  if(-not $ok){ kubectl get application runtime-builder -n stage-04-gitops -o yaml; throw "Argo reconciliation failed" }
  $proof=kubectl get deploy runtime-builder -n stage-04-gitops -o jsonpath='{.spec.template.metadata.annotations.lab\.vuln-mlops/stage-04-proof}'
  if($proof -ne 'FLAG{stage_4_gitops_placeholder}') { throw "Stage 4 proof missing" }
  $auditText=(docker exec "$name-control-plane" sh -c "cat /var/log/kubernetes/audit.log") -join "`n"
  if($auditText -notmatch "argocd-application-controller" -or $auditText -notmatch "runtime-builder") { throw "audit evidence missing" }
  Write-Output "Stage 4 Git commit $sha reconciled with proof and audit evidence."
} finally {
  if($pf){Stop-Process -Id $pf.Id -Force -ErrorAction SilentlyContinue}
  if((Get-Location).Path -like "$tmp*"){Pop-Location}
  & $KindCommand delete cluster --name $name 2>$null | Out-Null
  Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
