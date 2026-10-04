# Stage 5: Runtime Socket -> Escape Worker

Stage 5 moves the Git-controlled `runtime-builder` onto one tainted, labeled escape
worker and gives that existing Deployment access to that node's containerd socket.
The local proof is stored only on the escape kind node and is read through a
container launched by containerd; it is never mounted into the Kubernetes Pod.

## Intended path

1. The Stage 4 Git credential updates `runtime-builder/` on `stage4-lab`.
2. Argo CD reconciles only the pre-created `runtime-builder` in `stage-05-runtime`.
3. The container discovers `/run/stage5/containerd.sock`.
4. `crictl` discovers the running Pod's CRI sandbox, asks the node daemon to pull
   the digest-pinned proof image, then injects a short-lived unmanaged container
   using the existing workload's container identity and a read-only bind of the
   synthetic node proof directory. A second bind targets that Pod's existing
   `tmp` emptyDir so the container can copy only the synthetic proof into the Pod.
5. The proof, containerd CRI operation log, Pod node name, and Kubernetes exec
   audit record demonstrate the boundary crossing.

## Boundaries

- Only the escape worker receives the node proof and escape taint/label.
- The namespace uses the privileged Pod Security level because Kubernetes Pod
  Security forbids hostPath at lower levels. A ValidatingAdmissionPolicy fixes the
  exact Deployment, image digest, node selector, toleration, socket path, and mount.
- The container is UID 0 only for Unix-socket DAC access. It is not privileged,
  drops all capabilities, cannot gain privileges, uses seccomp RuntimeDefault, has
  a read-only root filesystem, and receives no ServiceAccount token or network.
- `images/runtime-client` builds the shared kind/EKS image from the official `crictl`
  v1.36.0 archive with its reviewed SHA-256 and packages an explicit
  `/run/stage5/containerd.sock` configuration. The Deployment pins the published OCI
  index digest; no runtime client binary is mounted from the worker host.
- Argo CD has read-only cache access and may only update/patch the existing
  `runtime-builder`; it cannot create/delete workloads or mutate another name.
- No AWS identity, CSI resource, production data, reverse shell, or arbitrary
  credential proof is introduced in Stage 5.

The broad power of a container runtime socket is intentional but exists only in a
disposable lab escape node. Do not apply this overlay to a shared or production
cluster.
