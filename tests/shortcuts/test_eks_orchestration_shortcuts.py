from pathlib import Path
import subprocess
import sys


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
    assert 'arbitrary Stage 3 credential reference was accepted' in text
    assert 'forbidden Git path was accepted' in text
    assert 'can-i create deployments.apps' in text
    assert 'node-role\",\"value\":\"general' in text
    stage4 = text[text.index("[Stage 4]") : text.index("[Stage 5]")]
    assert "start_port_forward stage-04-gitops service/gitea 3000" not in stage4
    assert '"$stage4_gateway"' in stage4
    stage5 = text[text.index("[Stage 5]") : text.index("[Cleanup]")]
    assert "kubectl exec" not in stage5
    assert "-d '{}'" in stage5


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


def test_public_participant_git_gateway_stays_on_the_fixed_proof_path() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")
    stage4 = text[text.index("[Stage 4]") : text.index("[Stage 5]")]

    assert 'not path.startswith("/api/lab/footholds/")' in stage4
    assert 'not path.endswith("/stage-04/git/vuln-mlops-gitops.git")' in stage4
    assert 'parts.scheme not in ("http", "https")' in stage4
    assert 'parts.path not in ("", "/")' in stage4
    assert 'encoded_user = quote(user, safe="")' in stage4
    assert 'encoded_token = quote(token, safe="")' in stage4
    assert '@127.0.0.1:$(forwarded_port)${stage4_gateway}' not in stage4

    snippet_start = stage4.index('git_url="$("$POC_PYTHON" -c \'') + len(
        'git_url="$("$POC_PYTHON" -c \'')
    snippet_end = stage4.index("' \"$modelgate_url\"", snippet_start)
    builder = stage4[snippet_start:snippet_end]
    gateway = "/api/lab/footholds/proof/stage-04/git/vuln-mlops-gitops.git"

    def build(base: str, path: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-c", builder, base, "lab-user", "token:@", path],
            capture_output=True,
            text=True,
            check=False,
        )

    public = build("http://3.35.2.114", gateway)
    assert public.returncode == 0
    assert public.stdout.strip() == (
        "http://lab-user:token%3A%40@3.35.2.114" + gateway
    )
    assert build("http://3.35.2.114/admin", gateway).returncode != 0
    assert build("http://3.35.2.114", "/other.git").returncode != 0
