# Stage 4: Argo CD / GitOps

이 디렉터리는 Stage 3에서 발급한 synthetic Git credential을 제한된 Gitea
repository에 연결하고, Argo CD가 기존 `runtime-builder` Deployment만 reconcile하는
로컬 실습 경계를 구현한다.

## Intended path

1. `stage3-lab-writer`가 `stage4-lab` branch의 `runtime-builder/` 경로를 변경한다.
2. Gitea pre-receive hook이 branch와 path 범위를 검사한다.
3. Argo CD `runtime-builder` Application이 auto-sync한다.
4. 기존 Deployment의 `STAGE4_MODE`와 synthetic proof annotation이 변경된다.
5. commit SHA, Argo revision, Kubernetes audit event를 성공 증거로 확인한다.

Stage 4는 runtime socket이나 hostPath를 추가하지 않는다. 해당 경계는 Stage 5에서
별도로 설계하고 검증한다.

## Boundary controls

- AppProject는 한 repository, `stage4-lab`, `runtime-builder/`, 현재 cluster의
  `stage-04-gitops` namespace, `apps/Deployment`만 허용한다.
- controller Role은 `runtime-builder`의 `get/update/patch`만 변경 권한으로 갖는다.
- Argo CD의 dynamic cluster cache가 namespaced API resource를 탐색하고 desired/live
  diff를 계산하므로 `get/list/watch` read-only wildcard는 필요하다. cluster Secret의
  destination namespace가 `stage-04-gitops`로 제한되고, wildcard에는 mutation verb가
  없다.
- ValidatingAdmissionPolicy는 controller가 다른 Deployment, host namespace,
  hostPath, privileged container를 적용하지 못하게 한다.
- Gitea hook은 다른 branch와 repository path를 거부한다.
- credentials와 proof는 모두 synthetic placeholder이며 실제 credential을 포함하지 않는다.

## Pinned components

- Argo CD `v3.5.3`:
  `quay.io/argoproj/argocd@sha256:dd3f47d5a5e4da563a7a398506e892481b358a7cec50abdf320c71aa55904bfa`
- Gitea `1.27.3-rootless`:
  `gitea/gitea@sha256:1c17ecaead42eb3b5391553d8708103a4beb0e86edf5b9ebc1eb269c318845f2`
- Argo CD install/CRD 원본은 `vendor/`에 고정하며 SHA-256을 정적 테스트로 검증한다.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  tests\attack-path\test_stage04_gitops_path.py `
  tests\shortcuts\test_stage04_shortcuts.py

.\tests\stage-04-kind-smoke.ps1 -KindCommand .\.tmp-kind.exe
```

kind smoke는 intended commit reconciliation과 proof/audit evidence를 확인하고, 다른
branch/path push, Deployment/Secret/Role 생성, 다른 Deployment 변경을 함께 거부한다.
