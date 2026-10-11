# Runtime builder maintenance

The delivery team's `lab-runtime` branch is the source for this Deployment.
Argo CD reconciles `runtime-builder/deployment.yaml` into `runtime-lab`.
The Git account can update only files under this directory.

The Pod is scheduled on the dedicated maintenance worker. The platform mounts
`/var/lib/vuln-mlops/maintenance` at `/host-maintenance` and watches its fixed
`task.sh` with systemd. The baseline Pod is non-root and the mount is read-only.
The separate `/node-evidence` mount is always read-only inside the Pod. The
Pod has no Kubernetes token and no AWS workload role.

Maintenance incidents are reviewed by comparing the Git revision, Argo sync
revision, Pod identity, host service execution, the dedicated EC2 instance's
proof tag, and its CloudTrail `CreateTags` event.

## Maintenance deployment notes

The Deployment is the only Git-managed workload for this repository path.
Its image, ServiceAccount, node selector, hostPath source directories and
evidence mount are fixed. The container image root remains read-only. That
setting does not make a hostPath writable or read-only: check the maintenance
`volumeMount.readOnly` setting and the Pod's UID/GID separately.

For a maintenance recovery, the Pod template may run as UID/GID 0 and its
single container may use a shell startup command. The command can write the
fixed `/host-maintenance/task.sh`, then start the normal runtime-builder HTTP
process so health checks continue. Changing UID or mount permissions alone
does not put a new task in that file. The separate `/node-evidence` mount must
remain read-only; use it only to read what the host task wrote.

The maintenance worker has the AWS CLI and an instance profile. An on-host
task can record `whoami`, `id`, `hostname` and `aws sts get-caller-identity`.
The proof operation tags the dedicated EC2 instance identified by that
assumed-role session. Use tag key `lab.vuln-mlops/proof`; the participant
chooses a distinct value beginning `lab-` (for example `lab-team7`; use
lowercase letters, digits and hyphens). The
node role cannot use this proof permission for arbitrary tag keys or for a
worker without the `lab.vuln-mlops/node-role=escape` tag.

After pushing, compare the Git commit with `runtime-builder` in the
`delivery-lab` Argo Application. The validator identity can read that
Application and the `runtime-lab` runtime-builder Pod inventory and logs with
its mounted in-cluster `kubectl`. Internal Pod logs can show the host evidence;
the operator separately checks the actual EC2 tag and CloudTrail event.
