from tests.stage2_manifest_helpers import STAGE, document, documents, rule_for


MODELGATE = ("ServiceAccount", "modelgate", "modelgate-lab")
RUNNER_IMAGE = (
    "registry.k8s.io/kubectl:v1.37.0@"
    "sha256:5ed410ebac5dc976cc717098994dcdb29bbbd38f6bd65f582311f5be4ba719cf"
)


def subjects(binding: dict) -> set[tuple[str, str, str]]:
    return {
        (subject["kind"], subject["name"], subject.get("namespace", ""))
        for subject in binding["subjects"]
    }


def test_stage_kustomization_installs_controls_but_not_attack_job():
    kustomization = document("kustomization.yaml", "Kustomization", "")
    resources = set(kustomization["resources"])

    assert "attack-job.yaml" not in resources
    assert resources == {
        "namespace.yaml",
        "service-account.yaml",
        "flag-secret.yaml",
        "rbac.yaml",
        "admission-policy.yaml",
        "network-policy.yaml",
    }


def test_modelgate_can_self_review_and_submit_only_stage_job_resources():
    review_binding = document(
        "rbac.yaml", "ClusterRoleBinding", "stage-02-modelgate-self-review"
    )
    submitter = document("rbac.yaml", "Role", "stage-02-job-submitter")
    submit_binding = document(
        "rbac.yaml", "RoleBinding", "stage-02-modelgate-job-submitter"
    )

    assert MODELGATE in subjects(review_binding)
    assert MODELGATE in subjects(submit_binding)
    assert submitter["metadata"]["namespace"] == "stage-02-rbac"
    assert set(rule_for(submitter, "jobs")["verbs"]) == {"create", "get", "watch"}
    assert set(rule_for(submitter, "pods")["verbs"]) == {"get", "list"}
    assert rule_for(submitter, "pods/log")["verbs"] == ["get"]


def test_monitoring_runner_can_get_only_the_fixed_flag_secret():
    role = document("rbac.yaml", "Role", "stage-02-flag-reader")
    binding = document(
        "rbac.yaml", "RoleBinding", "stage-02-monitoring-runner-flag-reader"
    )
    rule = rule_for(role, "secrets")

    assert rule["verbs"] == ["get"]
    assert rule["resourceNames"] == ["stage-02-flag"]
    assert (
        "ServiceAccount",
        "monitoring-runner",
        "stage-02-rbac",
    ) in subjects(binding)


def test_attack_job_uses_pinned_runner_and_fixed_identity():
    job = document("attack-job.yaml", "Job", "stage-02-secret-reader")
    pod = job["spec"]["template"]["spec"]
    container = pod["containers"][0]

    assert pod["serviceAccountName"] == "monitoring-runner"
    assert pod["automountServiceAccountToken"] is True
    assert container["image"] == RUNNER_IMAGE
    assert container["command"] == ["/bin/kubectl"]
    assert container["args"] == [
        "get",
        "secret",
        "stage-02-flag",
        "--namespace=stage-02-rbac",
        "--output=jsonpath={.data.flag}",
    ]


def test_audit_policy_records_all_stage_namespace_metadata():
    policy = document("audit-policy.yaml", "Policy", "")

    assert policy["rules"][0] == {
        "level": "Metadata",
        "namespaces": ["stage-02-rbac"],
    }
    assert policy["rules"][1] == {"level": "None"}
