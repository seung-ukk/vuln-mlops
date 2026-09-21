# 팀 실행 가이드와 안전한 PoC

이 문서는 팀원이 저장소를 clone하여 ModelGate를 실행하고, 격리된 로컬
Docker 환경에서 SSRF와 RCE 취약 경로를 검증하는 절차를 설명한다.

PoC는 다음 두 가지 합성 증거만 사용한다.

- SSRF: Docker 내부에서만 접근 가능한 `lab-canary`의 고정 문자열 읽기
- RCE: validator 컨테이너의 `/tmp/modelgate-rce-proof` 파일 생성

AWS IMDS, 실제 자격증명, 실제 내부 서비스, reverse shell 및 외부 시스템은
대상으로 사용하지 않는다.

## 1. 사전 준비

- Git
- Docker Desktop 또는 Docker Engine
- Docker Compose v2 (`docker compose version`으로 확인)
- 포트 `8080`, `5000`이 로컬에서 사용 가능할 것

Windows에서는 Docker Desktop의 Linux container engine이 실행 중이어야 한다.

## 2. Clone 및 실행

```bash
git clone https://github.com/seung-ukk/vuln-mlops.git
cd vuln-mlops
docker compose up -d --build
docker compose ps
```

정상 상태에서는 다음 네 서비스가 표시된다.

| 서비스 | 역할 | 호스트 노출 |
| --- | --- | --- |
| `api` | ModelGate UI/API | `127.0.0.1:8080` |
| `mlflow` | 실제 MLflow 3.13.0 backend | `127.0.0.1:5000` |
| `validator` | 모델 자동 호환성 검증 | 없음 |
| `lab-canary` | SSRF용 합성 내부 서비스 | 없음 |

확인 주소:

- ModelGate: <http://127.0.0.1:8080>
- MLflow: <http://127.0.0.1:5000>

헬스 체크:

```bash
curl -fsS http://127.0.0.1:8080/readyz
```

PowerShell에서는 다음 명령을 사용할 수 있다.

```powershell
Invoke-RestMethod http://127.0.0.1:8080/readyz
```

## 3. 정상 기능 검증

먼저 무해한 statsmodels 모델을 MLflow에 기록한다.

```bash
docker compose exec -T validator python -m modelgate.seed_benign
```

출력의 `artifact_uri` 값을 ModelGate UI에 입력한다. 예시는
`models:/m-0123456789abcdef` 형식이다. 등록 후 validation job이
`succeeded`가 되면 정상적인 모델 등록·자동 검증 흐름이 동작한 것이다.

## 4. SSRF PoC

### 실행

```bash
docker compose exec -T api python poc/ssrf_canary.py
```

스크립트는 다음 순서로 동작한다.

1. 공개 HTTPS redirect endpoint를 MLflow webhook URL로 등록한다.
2. 첫 URL은 MLflow의 공개 IP 검사를 통과한다.
3. HTTP 302 목적지는 Docker 내부의
   `http://lab-canary:9000/canary`이다.
4. MLflow 3.13.0이 redirect 목적지를 다시 검사하지 않고 요청한다.
5. Webhook test 응답을 통해 내부 canary 문자열을 읽는다.

성공 출력에는 다음 필드가 포함된다.

```json
{
  "proof": "ssrf",
  "success": true,
  "internal_target": "http://lab-canary:9000/canary",
  "canary": "MODELGATE_INTERNAL_SSRF_PROOF"
}
```

`lab-canary`에는 호스트 포트가 없으므로 팀원의 브라우저나 호스트에서
`127.0.0.1:9000`으로 직접 접근할 수 없다. 이 상태에서 해당 응답이 MLflow
Webhook 결과에 포함되는 것이 SSRF 증거다.

기본 redirect service는 `https://httpbin.org/redirect-to`다. 네트워크 정책으로
접근할 수 없는 환경에서는 팀이 소유한 공개 HTTPS redirect endpoint를 다음처럼
지정할 수 있다.

```bash
docker compose exec -e POC_REDIRECTOR_URL=https://redirect.lab.example/redirect-to \
  -T api python poc/ssrf_canary.py
```

redirect service는 `url`과 `status_code=302` query parameter를 지원해야 한다.

## 5. RCE PoC

### 실행

```bash
docker compose exec -T validator python poc/rce_marker.py
```

스크립트는 다음 순서로 동작한다.

1. 정상 statsmodels MLflow 모델 디렉터리를 만든다.
2. 모델 pickle을 `/tmp` marker만 생성하는 합성 payload로 교체한다.
3. MLflow run artifact로 업로드하고 ModelGate에 모델 버전을 등록한다.
4. validator가 `mlflow.pyfunc.load_model()`로 모델을 자동 로드한다.
5. `MLFLOW_ALLOW_PICKLE_DESERIALIZATION=false` 상태에서도 statsmodels loader가
   역직렬화를 수행하여 marker 파일이 생성된다.

성공 출력 예시:

```json
{
  "proof": "rce",
  "success": true,
  "validation_status": "succeeded",
  "marker_path": "/tmp/modelgate-rce-proof",
  "marker": "MODELGATE_RCE_PROOF uid=10001",
  "pickle_safety_setting": "false"
}
```

별도로 marker를 확인하려면 다음 명령을 사용한다.

```bash
docker compose exec -T validator python -c "from pathlib import Path; print(Path('/tmp/modelgate-rce-proof').read_text())"
```

이 PoC는 파일 한 개를 validator의 임시 디렉터리에 기록할 뿐이며 셸 연결,
네트워크 callback, credential 접근 또는 호스트 파일 접근을 수행하지 않는다.

## 6. 로그와 증거 수집

```bash
docker compose logs --no-color api mlflow validator > modelgate-lab.log
docker compose ps > modelgate-containers.txt
```

보고서에는 다음을 함께 기록한다.

- 이미지의 MLflow 버전: `3.13.0`
- `MLFLOW_ALLOW_PICKLE_DESERIALIZATION=false`
- SSRF canary 문자열 및 webhook ID
- RCE validation job ID와 marker 내용
- 테스트 시각과 Git commit SHA

## 7. 종료 및 초기화

컨테이너만 종료하고 기록을 보존하려면:

```bash
docker compose down
```

ModelGate의 로컬 SQLite 및 artifact volume까지 삭제하여 완전히 초기화하려면:

```bash
docker compose down --volumes
```

두 번째 명령은 이 Compose 프로젝트가 만든 `modelgate-lab_state`와
`modelgate-lab_artifacts` volume을 삭제한다.

## 8. 문제 해결

- `Invalid Host header`: 최신 저장소인지 확인하고 MLflow command에
  `--allowed-hosts mlflow:5000,localhost,127.0.0.1`이 있는지 확인한다.
- SSRF PoC timeout: Docker 컨테이너에서 `https://httpbin.org`로 나가는 HTTPS가
  허용되는지 확인한다.
- 포트 충돌: `docker compose ps`와 `docker ps`로 기존 실행을 확인한다.
- 모델 검증 실패: `docker compose logs validator`에서 해당 job ID를 검색한다.
- 완전한 재시작: `docker compose down --volumes` 후 다시 `up -d --build`한다.
