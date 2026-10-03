# Stage 2: RBAC Chaining

This stage starts with `system:serviceaccount:modelgate-lab:modelgate`. That identity
can create only the fixed `stage-02-secret-reader` Job in `stage-02-rbac`. Admission
pins the Job's name, `monitoring-runner` identity, image digest, command, arguments,
and restricted security context. The runner can `get` only `stage-02-flag`; it cannot
list Secrets.

`attack-job.yaml` is deliberately excluded from `kustomization.yaml`: creating it is
the boundary-crossing action. Its stdout is the base64-encoded synthetic flag, which
the caller decodes locally. The committed flag is a development placeholder and must
be replaced with a random value during lab provisioning.

Run the repeatable kind acceptance test from the repository root:

```bash
bash tests/stage-02-kind-smoke.sh
```

On PowerShell:

```powershell
.\tests\stage-02-kind-smoke.ps1
```

The test uses Kubernetes 1.37.0 via an immutable kind node digest and deletes its
temporary cluster on exit. `ValidatingAdmissionPolicy` requires Kubernetes 1.30 or
newer. The NetworkPolicy fixes the kind Kubernetes Service IP at `10.96.0.1` and
allows only port `6443` on kind's private Docker-network range for kube-proxy's
post-DNAT control-plane endpoint. Patch those API destinations for another disposable
cluster; do not widen application ports or add Stage 3 endpoints.
