param(
    [string]$KindCommand = "kind"
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$clusterName = "stage-02-$PID"
$kindNodeImage = "kindest/node:v1.37.0@sha256:a1ed56cfb0e7b93589bdf97c8cd566405a265939e3620fc4f5de89adff580ae5"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) "vuln-mlops-$clusterName"
$auditDirectory = Join-Path $tempRoot "audit"
$kindConfig = Join-Path $tempRoot "kind-config.yaml"
$modelgateUser = "system:serviceaccount:modelgate-lab:modelgate"

function Invoke-Native {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "native command failed with exit code $LASTEXITCODE"
    }
}

function Assert-CanI-No {
    param([string]$Description, [string[]]$Arguments)
    $answer = (& kubectl auth can-i @Arguments).Trim()
    if ($answer -ne "no") {
        throw "shortcut unexpectedly allowed: $Description ($answer)"
    }
}

function Assert-ApplyDenied {
    param([string]$Description, [string]$JsonPatch)
    $jobPath = Join-Path $repoRoot "lab/stages/stage-02-rbac/attack-job.yaml"
    $rendered = & kubectl patch --local -f $jobPath --type=json "-p=$JsonPatch" -o yaml
    if ($LASTEXITCODE -ne 0) {
        throw "failed to render negative fixture: $Description"
    }
    $rendered | & kubectl apply "--as=$modelgateUser" -f - 2>$null
    if ($LASTEXITCODE -eq 0) {
        throw "admission shortcut unexpectedly allowed: $Description"
    }
}

New-Item -ItemType Directory -Force $auditDirectory | Out-Null
$auditPolicy = (Resolve-Path (Join-Path $repoRoot "lab/stages/stage-02-rbac/audit-policy.yaml")).Path

@"
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
networking:
  serviceSubnet: 10.96.0.0/12
nodes:
  - role: control-plane
    extraMounts:
      - hostPath: '$auditPolicy'
        containerPath: /etc/kubernetes/stage-02-audit-policy.yaml
        readOnly: true
      - hostPath: '$auditDirectory'
        containerPath: /var/log/kubernetes
    kubeadmConfigPatches:
      - |
        kind: ClusterConfiguration
        apiServer:
          extraArgs:
            audit-policy-file: /etc/kubernetes/stage-02-audit-policy.yaml
            audit-log-path: /var/log/kubernetes/audit.log
            audit-log-maxage: "1"
            audit-log-maxbackup: "1"
            audit-log-maxsize: "20"
          extraVolumes:
            - name: audit-policy
              hostPath: /etc/kubernetes/stage-02-audit-policy.yaml
              mountPath: /etc/kubernetes/stage-02-audit-policy.yaml
              readOnly: true
              pathType: File
            - name: audit-log
              hostPath: /var/log/kubernetes
              mountPath: /var/log/kubernetes
              pathType: DirectoryOrCreate
"@ | Set-Content -LiteralPath $kindConfig -Encoding utf8NoBOM

try {
    Invoke-Native { & $KindCommand create cluster --name $clusterName --image $kindNodeImage --config $kindConfig }
    Invoke-Native { kubectl apply -k (Join-Path $repoRoot "deploy/base") }
    Invoke-Native { kubectl apply -k (Join-Path $repoRoot "lab/stages/stage-02-rbac") }

    $review = (& kubectl auth can-i create selfsubjectrulesreviews.authorization.k8s.io "--as=$modelgateUser").Trim()
    if ($review -ne "yes") { throw "SelfSubjectRulesReview is not allowed" }
    $createJob = (& kubectl auth can-i create jobs.batch -n stage-02-rbac "--as=$modelgateUser").Trim()
    if ($createJob -ne "yes") { throw "Stage 2 Job creation is not allowed" }

    & kubectl get secret stage-02-flag -n stage-02-rbac "--as=$modelgateUser" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) { throw "modelgate read the Stage 2 Secret directly" }

    Assert-CanI-No "RoleBinding creation" @("create", "rolebindings.rbac.authorization.k8s.io", "-n", "stage-02-rbac", "--as=$modelgateUser")
    Assert-CanI-No "ServiceAccount token minting" @("create", "serviceaccounts/token", "-n", "stage-02-rbac", "--as=$modelgateUser")
    Assert-CanI-No "Pod exec" @("create", "pods/exec", "-n", "stage-02-rbac", "--as=$modelgateUser")
    Assert-CanI-No "node read" @("get", "nodes", "--as=$modelgateUser")
    foreach ($namespace in @("default", "kube-system", "argocd")) {
        Assert-CanI-No "$namespace Job creation" @("create", "jobs.batch", "-n", $namespace, "--as=$modelgateUser")
    }

    Assert-ApplyDenied "wrong ServiceAccount" '[{"op":"replace","path":"/spec/template/spec/serviceAccountName","value":"default"}]'
    Assert-ApplyDenied "unapproved image" '[{"op":"replace","path":"/spec/template/spec/containers/0/image","value":"registry.k8s.io/kubectl:latest"}]'
    Assert-ApplyDenied "privileged container" '[{"op":"replace","path":"/spec/template/spec/containers/0/securityContext/privileged","value":true}]'
    Assert-ApplyDenied "hostPath mount" '[{"op":"add","path":"/spec/template/spec/volumes","value":[{"name":"host","hostPath":{"path":"/"}}]}]'
    Assert-ApplyDenied "Secret volume shortcut" '[{"op":"add","path":"/spec/template/spec/volumes","value":[{"name":"other-secret","secret":{"secretName":"stage-02-flag"}}]}]'
    Assert-ApplyDenied "environment override" '[{"op":"add","path":"/spec/template/spec/containers/0/env","value":[{"name":"KUBERNETES_SERVICE_HOST","value":"attacker.invalid"}]}]'

    Invoke-Native { kubectl apply "--as=$modelgateUser" -f (Join-Path $repoRoot "lab/stages/stage-02-rbac/attack-job.yaml") }
    & kubectl wait --for=condition=complete job/stage-02-secret-reader -n stage-02-rbac --timeout=240s
    if ($LASTEXITCODE -ne 0) {
        kubectl get pods -n stage-02-rbac -o wide
        kubectl describe job stage-02-secret-reader -n stage-02-rbac
        kubectl describe pods -n stage-02-rbac -l job-name=stage-02-secret-reader
        kubectl logs -n stage-02-rbac -l job-name=stage-02-secret-reader --all-containers --prefix
        throw "Stage 2 reader Job did not complete"
    }
    $podName = (& kubectl get pods -n stage-02-rbac "--as=$modelgateUser" -l job-name=stage-02-secret-reader -o "jsonpath={.items[0].metadata.name}").Trim()
    $encodedFlag = (& kubectl logs -n stage-02-rbac "--as=$modelgateUser" $podName).Trim()
    $decodedFlag = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($encodedFlag))
    if ($decodedFlag -ne "FLAG{stage_2_rbac_chaining_placeholder}") {
        throw "unexpected Stage 2 proof: $decodedFlag"
    }

    $observed = $false
    foreach ($attempt in 1..20) {
        $auditText = (& docker exec "$clusterName-control-plane" sh -c "cat /var/log/kubernetes/audit.log" 2>$null) -join "`n"
        if ($auditText.Contains("system:serviceaccount:modelgate-lab:modelgate") -and
            $auditText.Contains("stage-02-secret-reader")) {
            $observed = $true
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $observed) {
        docker exec "$clusterName-control-plane" sh -c "ls -la /var/log/kubernetes; ps aux | grep '[k]ube-apiserver'"
        docker exec "$clusterName-control-plane" sh -c "tail -n 5 /var/log/kubernetes/audit.log 2>/dev/null || true"
        throw "Stage 2 audit evidence was not observed"
    }

    Write-Output "Stage 2 intended path, shortcut denials, and audit evidence verified."
}
finally {
    & $KindCommand delete cluster --name $clusterName 2>$null | Out-Null
    Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
}
