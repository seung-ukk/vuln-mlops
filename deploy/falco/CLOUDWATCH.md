# Falco alert retention in CloudWatch (operator runbook)

This is an optional, manually installed observer for the personal EKS cluster.
Terraform does not own the log group, IAM role, Pod Identity association, or
Fluent Bit release. The existing Pod Identity Agent add-on is Terraform-managed;
do not create, upgrade, or remove it through this procedure. Use the operator AWS profile and kubeconfig; review the
account and cluster shown in preflight before making changes. This ships only the
`Lab container process started` and `Lab escape host maintenance started` Falco
JSON alerts, not all Pod stdout. It does
not block a workload. CloudWatch retains ingested events for **7 days**; in-flight
events can still be lost if the collector/node fails before delivery, and a
collector restart can cause duplicates because the offset DB is an `emptyDir`.

The official `fluent/fluent-bit` Helm chart is pinned to **0.58.2** (Fluent Bit
**5.1.2**). Its Pod reads `/var/log` read-only, has no Kubernetes RBAC, and can
write only log streams starting `falco-` under this one log group. The group is
created separately, so the Pod has no `CreateLogGroup` or retention permission.
There is no new dedicated node: one small collector runs alongside Falco on each
general and escape worker (50m CPU/64Mi request, 200m/256Mi limit).

## 1. Preflight and local render

Run from WSL. The verified account is `707605822656` and the cluster is
`vuln-mlops-personal-lab` in `ap-northeast-2`. Stop if the AWS account, cluster
ARN, or kube context differs. The existing `eks-pod-identity-agent` add-on is
`ACTIVE` at `v1.4.0-eksbuild.3`; its DaemonSet was verified `3/3 Ready`, with
Pods on both general workers and the escape worker. Confirm this remains true
before installation.

```bash
cd /mnt/c/Users/yoseb/Desktop/vuln-mlops
export AWS_REGION=ap-northeast-2
export AWS_DEFAULT_REGION=ap-northeast-2
export CLUSTER=vuln-mlops-personal-lab
export ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text)"
aws sts get-caller-identity
aws eks describe-cluster --name "$CLUSTER" --query 'cluster.arn' --output text
kubectl config current-context
kubectl get nodes -L lab.vuln-mlops/node-role
aws eks describe-addon --cluster-name "$CLUSTER" --addon-name eks-pod-identity-agent
kubectl -n kube-system get daemonset eks-pod-identity-agent -o wide
kubectl -n kube-system get pods -o wide | grep eks-pod-identity-agent
helm template falco-cloudwatch fluent-bit \
  --repo https://fluent.github.io/helm-charts --version 0.58.2 \
  -n falco-observe -f deploy/falco/cloudwatch-values.yaml > /tmp/falco-cloudwatch.yaml
python3 deploy/falco/render_cloudwatch_iam.py "$ACCOUNT_ID" /tmp/falco-cloudwatch-iam
cat /tmp/falco-cloudwatch-iam/trust.json
cat /tmp/falco-cloudwatch-iam/policy.json
```

## 2. Create AWS resources

Run these once after reviewing `/tmp/falco-cloudwatch-iam/*.json`. If the group
or role already exists, inspect it before reusing it rather than overwriting its
policy. The role trust requires this exact cluster, namespace, and ServiceAccount.

```bash
export LOG_GROUP="/vuln-mlops/$CLUSTER/falco"
export ROLE_NAME="$CLUSTER-falco-cloudwatch"
export ROLE_ARN="arn:aws:iam::$ACCOUNT_ID:role/$ROLE_NAME"
aws logs create-log-group --log-group-name "$LOG_GROUP" \
  --tags Project=vuln-mlops,LabId=vuln-mlops,Environment=personal-lab,ManagedBy=manual,Boundary=isolated-security-lab
aws logs put-retention-policy --log-group-name "$LOG_GROUP" --retention-in-days 7
aws logs describe-log-groups --log-group-name-prefix "$LOG_GROUP" \
  --query 'logGroups[*].[logGroupName,retentionInDays]' --output table
aws iam create-role --role-name "$ROLE_NAME" \
  --assume-role-policy-document file:///tmp/falco-cloudwatch-iam/trust.json \
  --tags Key=Project,Value=vuln-mlops Key=LabId,Value=vuln-mlops \
         Key=Environment,Value=personal-lab Key=ManagedBy,Value=manual \
         Key=Boundary,Value=isolated-security-lab
aws iam put-role-policy --role-name "$ROLE_NAME" \
  --policy-name falco-cloudwatch-stream-write \
  --policy-document file:///tmp/falco-cloudwatch-iam/policy.json
aws eks create-pod-identity-association --cluster-name "$CLUSTER" \
  --namespace falco-observe --service-account falco-cloudwatch \
  --role-arn "$ROLE_ARN" \
  --tags Project=vuln-mlops,LabId=vuln-mlops,Environment=personal-lab,ManagedBy=manual,Boundary=isolated-security-lab
aws eks list-pod-identity-associations --cluster-name "$CLUSTER" \
  --namespace falco-observe --service-account falco-cloudwatch
```

## 3. Install collector and verify

Apply the network policy before starting the collector. Falco's existing
namespace policy already permits DNS and HTTPS; the new policy permits only the
collector's TCP 80 request to the link-local Pod Identity Agent. A `kubectl exec`
probe in each Stage 5 container produces a harmless process-start event.

```bash
kubectl apply -f deploy/falco/cloudwatch-network-policy.yaml
helm upgrade --install falco-cloudwatch fluent-bit \
  --repo https://fluent.github.io/helm-charts --version 0.58.2 \
  -n falco-observe --wait --atomic --timeout 10m \
  -f deploy/falco/cloudwatch-values.yaml
kubectl -n falco-observe rollout status daemonset/falco-cloudwatch --timeout=10m
kubectl -n falco-observe get pods -l app.kubernetes.io/instance=falco-cloudwatch -o wide
export PROBE_START_MS="$(date -u +%s%3N)"
kubectl -n stage-05-runtime exec deployment/runtime-builder -c runtime-builder -- python -c pass
kubectl -n stage-05-runtime exec deployment/runtime-maintenance -c runtime-relay -- python -c pass
aws logs filter-log-events --log-group-name "$LOG_GROUP" --start-time "$PROBE_START_MS" \
  --filter-pattern '"Lab container process started"' \
  --query 'events[*].[timestamp,message]' --output text
kubectl -n falco-observe logs daemonset/falco-cloudwatch -c fluent-bit --since=10m
kubectl -n stage-05-runtime get deployments runtime-builder runtime-maintenance
```

Expect one collector Pod on each of the two general nodes and the escape node,
two new CloudWatch alerts after `PROBE_START_MS` with the right Pod names, and both Stage 5
Deployments Ready. If no events arrive, inspect collector output for Pod Identity
or CloudWatch errors and verify the Pod has injected
`AWS_CONTAINER_CREDENTIALS_FULL_URI` and its projected identity token. Do not
print credentials or token content. CloudWatch `filter-log-events` and Logs
Insights are operator-only; do not expose the log group to participants.

## Manual cleanup before destroying the lab

These four collector resources are outside Terraform. Remove only these named
resources when the observation exercise ends. Leave the Terraform-managed Pod
Identity Agent add-on in place.

```bash
helm uninstall falco-cloudwatch -n falco-observe --wait
kubectl delete -f deploy/falco/cloudwatch-network-policy.yaml
export ASSOCIATION_ID="$(aws eks list-pod-identity-associations --cluster-name "$CLUSTER" \
  --namespace falco-observe --service-account falco-cloudwatch \
  --query 'associations[0].associationId' --output text)"
aws eks delete-pod-identity-association --cluster-name "$CLUSTER" \
  --association-id "$ASSOCIATION_ID"
aws iam delete-role-policy --role-name "$ROLE_NAME" \
  --policy-name falco-cloudwatch-stream-write
aws iam delete-role --role-name "$ROLE_NAME"
aws logs delete-log-group --log-group-name "$LOG_GROUP"
```

The final log-group deletion immediately removes retained alerts. Perform it
only when the 7-day observation window is no longer needed.
