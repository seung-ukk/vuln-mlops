from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "lab" / "stages" / "stage-05-iam-app"


def deployment(name: str) -> dict:
    return yaml.safe_load((DRAFT / name).read_text(encoding="utf-8"))


def test_base_and_git_desired_app_use_the_same_irsa_identity_and_image() -> None:
    base = deployment("runtime-builder-base.yaml.in")
    desired = deployment("runtime-builder-desired.yaml.in")
    for item in (base, desired):
        pod = item["spec"]["template"]["spec"]
        assert item["metadata"]["name"] == "runtime-builder"
        assert item["metadata"]["namespace"] == "stage-05-runtime"
        assert pod["serviceAccountName"] == "runtime-builder-iam"
        assert pod["automountServiceAccountToken"] is False
        assert pod["nodeSelector"] == {
            "lab.vuln-mlops/node-role": "general",
            "kubernetes.io/arch": "amd64",
        }
        assert len(pod["containers"]) == 1
        assert pod["containers"][0]["image"] == "__RUNTIME_BUILDER_IMAGE__"
        assert pod["containers"][0]["command"][1] == "runtime_builder.main:app"
        assert all("hostPath" not in volume for volume in pod["volumes"])


def test_git_change_only_enables_the_reviewed_legacy_mode() -> None:
    base = deployment("runtime-builder-base.yaml.in")
    desired = deployment("runtime-builder-desired.yaml.in")
    base_env = {item["name"]: item.get("value") for item in base["spec"]["template"]["spec"]["containers"][0]["env"]}
    desired_env = {item["name"]: item.get("value") for item in desired["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert base_env["BUILDER_MODE"] == "baseline"
    assert desired_env["BUILDER_MODE"] == "legacy-build"
    assert base_env["STAGE5_MODE"] == "iam-pending"
    assert desired_env["STAGE5_MODE"] == "iam-build"
    assert desired["spec"]["template"]["metadata"]["annotations"] == {
        "lab.vuln-mlops/stage-04-proof": "FLAG{stage_4_gitops_placeholder}"
    }


def test_draft_admission_keeps_argo_on_one_named_deployment() -> None:
    items = list(yaml.safe_load_all((DRAFT / "admission-policy.yaml.in").read_text(encoding="utf-8")))
    policy = items[0]
    validations = "\n".join(item["expression"] for item in policy["spec"]["validations"])
    assert "request.userInfo.username == 'system:serviceaccount:stage-04-gitops:argocd-application-controller'" in policy["spec"]["matchConditions"][0]["expression"]
    assert "object.metadata.name == 'runtime-builder'" in validations
    assert "runtime-builder-iam" in validations
    assert "__RUNTIME_BUILDER_IMAGE__" in validations
    assert "lab.vuln-mlops/stage-04-proof" in validations
    assert "hostPath" not in validations


def test_iam_migration_seeds_participant_readme_and_exact_irsa_inputs() -> None:
    script = (ROOT / "deploy" / "eks-lab" / "orchestrate.sh").read_text(encoding="utf-8")
    assert 'IAM_REPOSITORY_README="${IAM_STAGE5_DIR}/repository/runtime-builder/README.md"' in script
    assert 'git -C "$repository_dir" add runtime-builder/README.md' in script
    assert 'tf output -raw runtime_builder_irsa_role_arn' in script
    assert 'tf output -raw runtime_proof_bucket' in script
    assert 'tf output -raw region' in script
    assert 'preapply_stage5_admission\n      apply_stage_composition' in script
    assert 'kubectl kustomize "$STAGE3_OVERLAY"' in script
    assert 'ghcr\\.io/seung-ukk/vuln-mlops@sha256:[a-f0-9]{64}' in script


def test_iam_migration_overlay_excludes_operator_deployment_update() -> None:
    overlay = (ROOT / "deploy" / "eks-lab" / "stage-05-iam-migrate" / "kustomization.yaml").read_text(encoding="utf-8")
    removal = yaml.safe_load((ROOT / "deploy" / "eks-lab" / "stage-05-iam-migrate" / "delete-runtime-builder.yaml").read_text(encoding="utf-8"))
    assert "../stage-05-iam" in overlay
    assert removal["$patch"] == "delete"
    assert removal["metadata"]["namespace"] == "stage-05-runtime"
    assert removal["metadata"]["name"] == "runtime-builder"


def test_iam_service_account_is_bound_to_rendered_role() -> None:
    sa = deployment("serviceaccount.yaml.in")
    config = deployment("aws-config.yaml.in")
    assert sa["metadata"]["annotations"]["eks.amazonaws.com/role-arn"] == "__RUNTIME_BUILDER_ROLE_ARN__"
    assert config["data"]["proof-bucket"] == "__RUNTIME_PROOF_BUCKET__"


def test_socket_orchestrator_cannot_reset_an_iam_deployment() -> None:
    script = (ROOT / "deploy" / "eks-lab" / "orchestrate.sh").read_text(encoding="utf-8")
    assert 'if [[ "$active_sa" == "runtime-builder-iam" && "$STAGE5_IAM" == false ]]' in script
    assert 'guard_active_stage5_profile\n    if [[ "$STAGE5_IAM" == true ]]' in script
