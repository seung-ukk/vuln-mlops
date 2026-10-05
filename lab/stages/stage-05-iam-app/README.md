# IAM app deployment draft (not active)

These manifests are intentionally **not** included in the current socket
Kustomize overlay. The separate `deploy/eks-lab/stage-05-iam` overlay can be
rendered after CI publishes the reviewed OCI index digest containing
`runtime_builder/`. The orchestrator substitutes the image, Terraform role
ARN, proof bucket, and AWS region; it never writes the Flag to a manifest.

The base Deployment keeps `BUILDER_MODE=baseline` and `STAGE5_MODE=iam-pending`.
The Git desired Deployment sets `legacy-build` and `iam-build` along with the
Stage 4 proof annotation. Argo CD continues to reconcile only the existing
`runtime-builder` Deployment in `stage-05-runtime`; it does not create the IAM
role or ServiceAccount. The pre-created `runtime-builder-iam` ServiceAccount is
trusted by the Terraform-managed IRSA role, and the ConfigMap holds only the
bucket name, never the Flag or credentials.

The app is on a general worker, with no containerd socket, hostPath, privileged
container, node selector for the escape group, or Kubernetes API token mount.
This path demonstrates Pod application execution and IAM access, not node
compromise. The existing socket path remains active until the app image and
participant flow are verified.

With `--stage5-iam`, the orchestrator seeds
`repository/runtime-builder/README.md` alongside the base Deployment in the
restricted Gitea `stage4-lab` branch. The migration overlay excludes the
Deployment from the operator apply; the new Git revision lets Argo reconcile
the existing workload under the reviewed admission policy. The current EKS
cluster still uses the socket profile until that migration is run.
