from modelgate.kubernetes import stage2_job_manifest
from tests.stage2_manifest_helpers import document, documents


FORBIDDEN_RBAC_RESOURCES = {
    "secrets",
    "roles",
    "rolebindings",
    "clusterroles",
    "clusterrolebindings",
    "serviceaccounts/token",
    "pods/exec",
    "pods/attach",
    "nodes",
    "nodes/proxy",
}


def validation_expressions() -> str:
    policy = document("admission-policy.yaml", "ValidatingAdmissionPolicy", "stage-02-job-shape")
    return "\n".join(validation["expression"] for validation in policy["spec"]["validations"])


def test_modelgate_role_has_no_privilege_escalation_or_secret_permissions():
    role = document("rbac.yaml", "Role", "stage-02-job-submitter")
    resources = {
        resource for rule in role["rules"] for resource in rule.get("resources", [])
    }
    verbs = {verb for rule in role["rules"] for verb in rule["verbs"]}

    assert resources.isdisjoint(FORBIDDEN_RBAC_RESOURCES)
    assert "*" not in resources
    assert "*" not in verbs
    assert role["metadata"]["name"] == "stage-02-job-submitter"
    assert role["metadata"]["namespace"] == "stage-02-rbac"


def test_admission_denies_identity_image_command_and_host_shortcuts():
    expressions = validation_expressions()

    assert "object.metadata.name == 'stage-02-secret-reader'" in expressions
    assert "serviceAccountName == 'monitoring-runner'" in expressions
    assert "sha256:5ed410ebac5dc976cc717098994dcdb29bbbd38f6bd65f582311f5be4ba719cf" in expressions
    assert "command == ['/bin/kubectl']" in expressions
    assert "stage-02-flag" in expressions
    assert "hostNetwork" in expressions
    assert "hostPID" in expressions
    assert "hostIPC" in expressions
    assert "has(volume.projected)" in expressions
    assert "kube-root-ca.crt" in expressions
    assert "kube-api-access-" in expressions
    assert "!has(object.spec.template.spec.containers[0].env)" in expressions
    assert "privileged == false" in expressions
    assert "allowPrivilegeEscalation == false" in expressions
    assert "capabilities.drop == ['ALL']" in expressions


def test_admission_binding_fails_closed_with_deny():
    policy = document("admission-policy.yaml", "ValidatingAdmissionPolicy", "stage-02-job-shape")
    binding = document(
        "admission-policy.yaml", "ValidatingAdmissionPolicyBinding", "stage-02-job-shape"
    )

    assert policy["spec"]["failurePolicy"] == "Fail"
    assert set(binding["spec"]["validationActions"]) == {"Deny", "Audit"}


def test_stage_namespace_enforces_restricted_pod_security():
    namespace = document("namespace.yaml", "Namespace", "stage-02-rbac")
    labels = namespace["metadata"]["labels"]

    assert labels["pod-security.kubernetes.io/enforce"] == "restricted"
    assert labels["pod-security.kubernetes.io/audit"] == "restricted"
    assert labels["pod-security.kubernetes.io/warn"] == "restricted"


def test_foothold_relay_has_no_caller_controlled_job_fields():
    job = stage2_job_manifest()
    assert job["metadata"]["name"] == "stage-02-secret-reader"
    assert job["metadata"]["namespace"] == "stage-02-rbac"
    pod = job["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == "monitoring-runner"
    assert pod["automountServiceAccountToken"] is True
    assert pod["containers"][0]["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "privileged": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }


def test_network_policy_allows_only_dns_and_fixed_kind_api_endpoint():
    policies = documents("network-policy.yaml")
    stage_policies = [
        policy for policy in policies if policy["metadata"]["namespace"] == "stage-02-rbac"
    ]
    api_policy = next(
        policy
        for policy in stage_policies
        if policy["metadata"]["name"] == "stage-02-api-egress"
    )
    cidrs = {
        destination["ipBlock"]["cidr"]
        for rule in api_policy["spec"]["egress"]
        for destination in rule["to"]
        if "ipBlock" in destination
    }
    ports = {
        port["port"]
        for rule in api_policy["spec"]["egress"]
        for port in rule["ports"]
    }

    assert cidrs == {"10.96.0.1/32", "172.16.0.0/12"}
    assert ports == {53, 443, 6443}
    assert any(
        policy["metadata"]["name"] == "stage-02-default-deny"
        and policy["spec"]["podSelector"] == {}
        and set(policy["spec"]["policyTypes"]) == {"Ingress", "Egress"}
        for policy in stage_policies
    )
