# Stage 3: Monitoring Stack Trust Abuse

The intended path uses `monitoring-runner` network access to Grafana's anonymous
Viewer datasource proxy. Prometheus Kubernetes discovery scrapes the internal
credential broker; `gitops_debug_info` reveals only topology and an opaque reference.
The reference can then be exchanged at the broker for a synthetic, lab-only Git
credential scoped by repository, branch, and path. No Kubernetes or Argo CD token is
placed in metrics.

Prometheus 3.14.0 and Grafana 13.2.2 are pinned by multi-architecture digest. All
Services are ClusterIP-only. The placeholder credential must be randomized or
replaced by the Stage 4 repository issuer before a shared exercise.

