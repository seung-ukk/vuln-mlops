from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "eks-lab" / "orchestrate.sh"
ACCEPTANCE = ROOT / "deploy" / "eks-lab" / "acceptance.sh"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_orchestrator_requires_explicit_non_root_aws_identity() -> None:
    text = script_text()

    assert '${AWS_PROFILE:-}' in text
    assert "aws sts get-caller-identity" in text
    assert "== *':root'" in text
    assert "AWS_ACCESS_KEY_ID" not in text
    assert "AWS_SECRET_ACCESS_KEY" not in text
    assert "AWS_SESSION_TOKEN" not in text


def test_orchestrator_does_not_bypass_server_side_safety() -> None:
    text = script_text()

    assert "--server-side" in text
    assert "--force-conflicts" not in text
    assert "--validate=false" not in text
    assert "kubectl delete namespace" not in text
    assert "kubectl delete namespaces" not in text
    assert "delete --all" not in text
    assert 'FIELD_MANAGER="vuln-mlops-orchestrator"' not in text


def test_reset_deletes_only_fixed_transient_resources() -> None:
    text = script_text()

    assert "job/stage-02-secret-reader" in text
    assert "pod/stage-03-client" in text
    assert "-n stage-05-runtime delete pod -l app=runtime-builder" in text
    assert "delete deployment" not in text
    assert "delete statefulset" not in text
    assert "delete secret" not in text


def test_orchestrator_preserves_stage_4_and_5_scope() -> None:
    text = script_text()

    assert "stage3-lab-writer" in text
    assert "vuln-mlops-gitops" in text
    assert "stage4-lab" in text
    assert "runtime-builder/deployment.yaml" in text
    assert "stage-06" not in text
    assert "iam:PassRole" not in text
    assert "cluster-admin" not in text
    assert "push --force" not in text


def test_orchestrator_uses_an_ephemeral_kubeconfig_and_workspace() -> None:
    text = script_text()

    assert 'WORK_DIR="$(mktemp -d)"' in text
    assert 'KUBECONFIG_FILE="${WORK_DIR}/kubeconfig"' in text
    assert 'export KUBECONFIG="$KUBECONFIG_FILE"' in text
    assert 'rm -rf -- "$WORK_DIR"' in text
    assert "trap cleanup EXIT" in text


def test_acceptance_checks_representative_shortcut_denials() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")

    assert 'get secret/stage-02-flag' in text
    assert 'direct Prometheus shortcut succeeded' in text
    assert 'forbidden Git path was accepted' in text
    assert 'can-i create deployments.apps' in text
    assert 'node-role\",\"value\":\"general' in text


def test_acceptance_keeps_proof_channels_synthetic_and_scoped() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")

    assert "MODELGATE_INTERNAL_SSRF_PROOF" not in text
    assert "FLAG{stage_2_rbac_chaining_placeholder}" in text
    assert "FLAG{stage_3_monitoring_trust_placeholder}" in text
    assert "FLAG{stage_4_gitops_placeholder}" in text
    assert "FLAG{stage_5_node_placeholder}" in text
    assert "stage-06" not in text
    assert "169.254.169.254" not in text
    assert "cluster-admin" not in text
    assert "push --force" not in text


def test_acceptance_cleanup_is_limited_to_transient_resources() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")

    assert "job/stage-02-secret-reader" in text
    assert "pod/stage-03-client" in text
    assert "delete namespace" not in text
    assert "delete deployment" not in text
    assert "delete secret" not in text


def test_acceptance_cleanup_does_not_reuse_a_stale_forwarded_port() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")
    cleanup = text[text.index("cleanup() {") : text.index("trap cleanup EXIT")]

    assert "start_port_forward stage-04-gitops service/gitea 3000" in cleanup
    assert "point_git_remote_at_current_forward" in cleanup
    assert cleanup.index("point_git_remote_at_current_forward") < cleanup.index(
        'push_git_manifest "$STAGE5_BASE"'
    )
