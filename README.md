# vuln-mlops / ModelGate

ModelGate is an intentionally vulnerable, MLflow-backed model onboarding service for
an authorized Kubernetes red-team lab. It models a real MLOps workflow: register a
model artifact, create a model version, run an automatic compatibility validation,
approve the version, and notify downstream systems through webhooks.

> **Warning**
>
> This project pins a known-vulnerable MLflow release. Never deploy it to the public
> Internet, a production cluster, or an account containing real data or credentials.

## Why this design

The application uses the affected product instead of recreating similar bugs:

- MLflow `3.13.0` Webhook redirect SSRF:
  [GHSA-7gwp-5pfp-969j](https://github.com/mlflow/mlflow/security/advisories/GHSA-7gwp-5pfp-969j)
- MLflow statsmodels deserialization guard bypass:
  [GHSA-gqvg-gmmx-x4hm](https://github.com/mlflow/mlflow/security/advisories/GHSA-gqvg-gmmx-x4hm)

ModelGate adds only the realistic business workflow. The validator calls
`mlflow.pyfunc.load_model()` when a model version is registered, while the webhook
routes delegate delivery to the MLflow server.

```text
user -> ModelGate API/UI -> MLflow Tracking + Model Registry
                             |-> webhook delivery
                             |-> model artifacts
                    validation worker -> compatibility load
```

## Local start

Requirements: Docker with Compose v2.

```bash
docker compose up --build
```

Open `http://127.0.0.1:8080`. The MLflow UI is available for local inspection at
`http://127.0.0.1:5000`; both listeners are bound to loopback only.

Create a harmless statsmodels sample in MLflow first:

```bash
docker compose exec -T validator python -m modelgate.seed_benign
```

The command prints JSON containing an `artifact_uri` such as
`models:/m-0123456789abcdef`. Paste that URI into the UI or the registration
request. This follows the MLflow 3 model workflow: log an artifact first, then use
the logged-model URI as the source of a registered model version.

Useful API endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/artifacts` | Upload a zipped MLflow model bundle and receive its artifact URI |
| `GET` | `/api/proofs/rce/{proof_id}` | Verify a fixed marker without returning file content |
| `GET` | `/api/lab/footholds/{proof_id}/self-rules` | Review the RCE foothold's bounded Stage 2 permissions |
| `POST` | `/api/lab/footholds/{proof_id}/stage-02/job` | Submit the fixed Stage 2 reader Job |
| `GET` | `/api/lab/footholds/{proof_id}/stage-02/job` | Poll the fixed Stage 2 reader Job |
| `GET` | `/api/lab/footholds/{proof_id}/stage-02/log` | Read only the fixed synthetic Stage 2 proof log |
| `GET` | `/api/lab/footholds/{proof_id}/stage-03/datasources` | Discover the bounded Grafana datasource after Stage 2 completion |
| `GET` | `/api/lab/footholds/{proof_id}/stage-03/query` | Query only the fixed topology metric through Grafana |
| `GET` | `/api/lab/footholds/{proof_id}/stage-03/exchange/{credential_ref}` | Exchange only the discovered synthetic credential reference |
| `GET/POST` | `/api/lab/footholds/{proof_id}/stage-04/git/vuln-mlops-gitops.git/...` | Fixed Git smart-HTTP gateway for the single lab repository |
| `GET` | `/api/lab/footholds/{proof_id}/stage-04/application` | Read normalized `runtime-builder` Argo reconciliation status |
| `POST` | `/api/lab/footholds/{proof_id}/stage-05/runtime/proof` | Run the fixed synthetic runtime proof after Stage 4 reconciliation |
| `POST` | `/api/models` | Register a model version and queue validation |
| `GET` | `/api/models/{name}` | Read registry metadata |
| `POST` | `/api/models/{name}/versions/{version}/validate` | Queue validation |
| `POST` | `/api/models/{name}/versions/{version}/approve` | Set `champion` alias |
| `GET` | `/api/system/info` | Read bounded synthetic lab discovery hints |
| `POST` | `/api/webhooks` | Create a registry webhook |
| `POST` | `/api/webhooks/{id}/test` | Test webhook delivery through MLflow |
| `GET` | `/api/jobs/{id}` | Read validation result |

Example registration using a benign lab artifact:

```bash
curl -sS http://127.0.0.1:8080/api/models \
  -H 'content-type: application/json' \
  -d '{"name":"fraud-detection","artifact_uri":"models:/m-REPLACE_WITH_LOGGED_MODEL_ID","description":"lab compatibility check"}'
```

An external client can upload a model directory without direct access to the
MLflow container. The ZIP must contain exactly one `MLmodel` manifest. Archive
size, extracted size, file count, paths, duplicate entries, encryption, and
symbolic links are validated before the bundle is stored:

```bash
curl -sS http://127.0.0.1:8080/api/artifacts \
  -H 'content-type: application/zip' \
  --data-binary @model-bundle.zip
```

The API validates and stores the bundle, publishes it as an MLflow logged model,
and returns a `models:/m-...` `artifact_uri`. Use that URI in `POST /api/models`.
This makes the complete upload, registration, and automatic validation workflow
reachable through the public ModelGate API; direct access to MLflow is not required.

## Container image publishing

Pull requests build the image without publishing it. Pushes to `main` publish
`ghcr.io/seung-ukk/vuln-mlops:main`, `:latest`, and an immutable `:sha-...` tag.
Tags beginning with `v` publish the corresponding release tag. Kubernetes
deployments should use an immutable digest for shared lab releases.

The only deserialization payload included creates a fixed synthetic marker for the
authorized PoC. No reverse shell, credential collection code, arbitrary proof-file
read API, redirector, or AWS mutation script is included in this repository.

## Kubernetes deployment

Build and push the image to an approved registry, then update the three image fields
in `deploy/base/deployment.yaml`.

Safe baseline:

```bash
kubectl apply -k deploy/base
```

The base NetworkPolicy blocks private and link-local egress, so it is appropriate for
functional verification but not the complete EKS chain. The explicit lab overlay
opens the documented VPC and metadata paths:

```bash
kubectl apply -k deploy/eks-lab
```

Before applying that overlay, narrow its VPC CIDR and configure a disposable IRSA or
Pod Identity role with canary-only permissions. See [SECURITY.md](SECURITY.md) and
[docs/architecture.md](docs/architecture.md).

## Development

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements/dev.txt
pytest
```

On PowerShell, activate the environment with `.venv\\Scripts\\Activate.ps1`.

## Team setup and safe PoC

Clone/run instructions and marker-only SSRF/RCE verification are documented in
[docs/TEAM_GUIDE_AND_POC.md](docs/TEAM_GUIDE_AND_POC.md).
