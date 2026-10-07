# Stage 4/5 hostPath capstone: operator migration draft

Status: local implementation only. **Do not run the cutover commands yet.** The
new ModelGate/runtime-builder image must be published at a reviewed OCI index
digest, the candidate Deployments must be tested against the installed new
admission policy, and the current
GitOps branch must be backed up first. No live EKS resources have been changed
by this draft.

The Terraform plan generated before the separate `node-evidence` directory
was added is stale. The reviewed replacement is
`/tmp/vuln-hostpath-node-review-v2.tfplan`; do not apply the earlier
`/tmp/vuln-hostpath-node-review.tfplan` file. The revised admission policy
passed an EKS server-side dry run on 2026-10-07, without persisting it.

## Target topology

`Stage 3 Git credential → runtime-builder/deployment.yaml → Argo CD →
stage-05-runtime/runtime-builder on the escape worker → fixed hostPath
maintenance directory → systemd host service → escape node IAM role → exact
synthetic S3 object`.

The host writes the bounded result under `/var/lib/vuln-mlops/node-evidence`,
outside the writable maintenance directory. The Pod mounts that second path
read-only. A Git command that merely writes a fake JSON file in the maintenance
directory cannot satisfy the participant result endpoint.

The baseline Pod uses UID/GID 10001 and a read-only hostPath mount. Git can
change its command, UID/GID, and the mount's read-only flag. It cannot change
the image, ServiceAccount, node selector, hostPath source, namespace, or
container count. The host's `vuln-mlops-maintenance.path` unit watches only
`/var/lib/vuln-mlops/maintenance/task.sh`; its service executes that script as
host root. This is real host execution on a disposable node. The node must be
replaced after a solve.

## Before cutover

1. Build and publish the changed app image after explicit authorization to
   commit/push. Record its complete OCI index digest. The current deployed
   digest lacks `/stage-05/node-result` and `/node/result`.
2. Verify the private S3 object's body is the synthetic Flag, and no real
   secrets are in the lab bucket. Confirm the account, region, cluster, EIP,
   node labels, current Argo revision, Falco DaemonSets, and Gitea branch.
3. Back up the current `stage4-lab` branch and live manifests outside the
   existing `checkpoints/` directory. Record the escape node instance ID.
4. Render `deploy/eks-lab/stage-05-hostpath` with the new digest and review
   every resource and deletion. Server-side dry-run the new admission policy.
   Decide whether to enable [S3 object-level CloudTrail data events](https://docs.aws.amazon.com/awscloudtrail/latest/userguide/logging-data-events-with-cloudtrail.html)
   for the exact proof object during the acceptance window. They are not
   enabled by default and can incur charges; without them, the result JSON
   and host journal are supporting evidence but not an independent AWS event
   record.
5. Create a Terraform plan with
   `-var='enable_hostpath_node_capstone=true'`. It should remove the old
   runtime-builder S3 policy, attach one-object `s3:GetObject` to the escape
   node role, and update only the escape node's launch template/user data.
   Review the exact plan before applying it. [AWS documents that changing a
   managed node group's launch-template version recycles its nodes](https://docs.aws.amazon.com/eks/latest/userguide/launch-templates.html).

## Cutover order

1. Suspend automated sync of the `runtime-builder` Argo Application. Scale
   the old builder to zero and delete `runtime-maintenance`. Confirm no old
   builder or maintenance Pod remains. This prevents the old socket and Pod
   IRSA paths from inheriting the new node IAM permission.
2. Apply the reviewed Terraform plan. Wait for the replacement escape worker
   to be Ready and verify its maintenance path unit is active. Confirm the
   runtime-builder Pod S3 policy was removed.
3. Remove the old runtime relay Service, ServiceAccount, ConfigMap, and
   NetworkPolicies, especially `runtime-builder-iam-egress` and
   `runtime-builder-maintenance-egress`; Kubernetes NetworkPolicies are
   additive, so leaving either can re-open egress.
4. Put the new baseline Deployment and participant README in the Gitea
   `stage4-lab` branch. Keep the existing branch/path scope hook. Replace the
   old Deployment template rather than merging it, so the socket/IRSA fields
   cannot survive server-side apply.
5. Apply the new admission policy and hostPath overlay, then update Stage 1~3
   workloads to the same reviewed app image. Re-enable Argo automated sync.
   Confirm `Synced/Healthy`, exact commit SHA, new Pod UID, escape node name,
   baseline UID/GID, and read-only mount.
6. Upgrade only `falco-escape` with its existing common/escape values plus
   `deploy/eks-lab/stage-05-hostpath/falco-values.yaml`. The current common
   rule excludes `container.id = host`; this additional observe-only rule
   records the host maintenance script start without logging arguments or
   paths. Confirm Fluent Bit sends the event to the existing seven-day
   CloudWatch group. No response or blocking action is configured.

   ```bash
   helm upgrade --install falco-escape falco \
     --repo https://falcosecurity.github.io/charts --version 9.2.0 \
     -n falco-observe --wait --atomic --timeout 10m \
     -f deploy/falco/values-common.yaml \
     -f deploy/falco/values-escape.yaml \
     -f deploy/eks-lab/stage-05-hostpath/falco-values.yaml
   ```

## Acceptance and reset

- Before the Git change, writing `task.sh` from the baseline Pod must fail.
  Confirm separately that a non-root process cannot write with a writable
  mount and a root process cannot write with a read-only mount. Direct Pod
  IMDS/IRSA S3 access, a different bucket/key, general-worker placement, and
  extra ServiceAccounts/resources must fail.
- Generate the mentor-only desired Deployment with
  `deploy/hostpath_capstone.py`. Push it to the scoped Gitea branch through the
  participant path. Confirm Argo revision equals that commit and the new Pod
  has run on the escape worker. Observe host `systemd` execution and the
  node-role S3 `GetObject` separately, using an S3 data event if enabled.
  The participant result endpoint is a bounded display channel; its JSON
  alone is not independent host evidence.
- Restore the baseline Git revision. Terminate the compromised escape EC2
  instance through its managed node group and wait for a new instance. Verify
  the new node has no `result.json`, the builder is baseline again, and Falco
  plus CloudWatch collection are healthy on the replacement node.

The cutover is intentionally not encoded as one blind command: it requires a
new image digest, a reviewed Terraform plan, a server-side admission dry run,
and live evidence from the user's personal account. The operator should stop
if any prerequisite or expected deletion differs from this list.
