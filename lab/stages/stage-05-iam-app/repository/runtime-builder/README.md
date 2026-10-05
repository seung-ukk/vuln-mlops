# Runtime Builder

This repository controls the `runtime-builder` application deployed by the
`runtime-builder` Argo CD Application. The `stage4-lab` branch contains its
Deployment at `runtime-builder/deployment.yaml`.

The baseline build profile is disabled. The legacy profile enables the build
API after Argo CD reconciles the Deployment. Use the ModelGate application
status response to discover the proof-bound build info endpoint; the builder
Service itself is internal to the cluster.

The build API accepts a `source_ref`. An older source resolver checks a path
under `/workspace` using a shell command assembled from that reference.
The HTTP response reports only whether the command completed; it does not
return command output. The build info endpoint reports the active profile and
input field. These details are enough to assess whether the resolver treats
the reference as data or shell syntax.

The application runs under the `runtime-builder-iam` ServiceAccount. Its AWS
role can read one synthetic proof object from the lab S3 bucket. The proof
endpoint reports only a validated account, assumed-role ARN, and synthetic
flag after the application has observed that proof. No AWS keys are stored in
this repository.

A separate `runtime-maintenance` agent runs on the dedicated escape worker.
It has no IRSA role or Kubernetes token, but its fixed maintenance task uses
the worker's containerd socket. Only the builder Pod can call the agent.
The baseline builder profile disables that maintenance bridge; the legacy
profile enables it after Argo CD reconciles this Git revision. The ModelGate
application status response then shows a proof-bound runtime path. This is
an independent exercise from the command injection / IAM proof: compare a
normal Pod's access with the runtime operation's synthetic node proof. The
public request accepts no command, image, path, target Pod, or request body.
