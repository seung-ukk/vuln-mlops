# Runtime Builder: host maintenance profile

The `stage4-lab` branch controls only `runtime-builder/deployment.yaml`. Argo CD
reconciles that file into the existing `stage-05-runtime/runtime-builder`
Deployment. The Stage 3 Git credential cannot create another Kubernetes
resource or change another repository path.

The Deployment is scheduled on the dedicated escape worker. It mounts that
worker's lab maintenance directory at `/host-maintenance`. The initial mount
is read-only and the container runs as UID/GID 10001. The image root also
remains read-only. Check each setting independently when reasoning about which
filesystem can be written.

The host uses a maintenance task in that directory. The builder Pod has no
Kubernetes token or AWS workload role. The application status endpoint reports
the reconciled revision and, after a host result exists, a bounded result URL.
The result exposes only the synthetic lab account, assumed node-role ARN, and
the synthetic S3 flag. It does not expose command output or credentials.
