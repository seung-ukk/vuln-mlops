# Architecture and trust boundaries

## Runtime components

The Kubernetes Deployment creates one Pod with three non-root containers:

1. `api` exposes the ModelGate workflow on port 8080.
2. `mlflow-registry` listens only on Pod loopback port 5000 and provides the real
   MLflow Model Registry and webhook implementation.
3. `validator` claims jobs from a shared SQLite queue and loads registered model
   versions to perform a compatibility check.

The design deliberately keeps the original MLflow behavior. ModelGate does not
reimplement redirect handling or pickle loading. It adds the normal business event
that makes those product paths reachable: webhook connectivity testing and automatic
model compatibility validation.

## Trust boundaries

- Only the ModelGate API is exposed by the Kubernetes Service.
- The MLflow server is reachable from containers in the same Pod over loopback.
- The API and worker share a job database using an `emptyDir` volume.
- Model artifacts use a shared local volume in the base deployment. An approved lab
  can replace this with a dedicated S3 prefix.
- The Pod uses one ServiceAccount so the application identity is consistent across
  the workflow. No host namespace, host mount, privileged mode, or Linux capability
  is required.

## Vulnerable and patched controls

The vulnerable image pins `mlflow==3.13.0`. For a negative control, build a second
image after changing the MLflow requirement to a reviewed patched release (3.16.0 or
later) and run the same functional tests. Do not silently upgrade the vulnerable
profile because exact versioning is part of the exercise evidence.

## EKS lab profile

The base NetworkPolicy denies RFC1918 and link-local egress. The `eks-lab` Kustomize
overlay enables HTTPS egress, VPC HTTP/HTTPS, and the IPv4 IMDS endpoint. Before use:

- narrow `10.0.0.0/8` to the actual disposable VPC CIDR;
- attach an IRSA role or create a Pod Identity association out of band;
- restrict any target role to tagged canary resources and an approved launch template;
- configure automatic cleanup and a budget alarm;
- verify how the installed CNI implements `ipBlock` for node and link-local traffic.
