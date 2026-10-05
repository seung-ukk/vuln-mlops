from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "eks-lab" / "orchestrate.sh"
ACCEPTANCE = ROOT / "deploy" / "eks-lab" / "acceptance.sh"


def script_text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def test_orchestrator_connects_foundation_to_stage_1_through_5() -> None:
    text = script_text()

    assert 'FOUNDATION_BOOTSTRAP="${TF_DIR}/bootstrap.sh"' in text
    assert '"$FOUNDATION_BOOTSTRAP" "${bootstrap_args[@]}"' in text
    assert 'aws eks update-kubeconfig' in text
    assert 'cluster_operator_role_arn' in text
    assert "kubectl apply" in text
    assert "--server-side" in text
    assert '-k "$STAGE3_OVERLAY"' in text
    assert '-k "$STAGE5_OVERLAY"' in text


def test_orchestrator_applies_argocd_crds_before_the_composition() -> None:
    text = script_text()

    crd_position = text.index("application-crd-v3.5.3.yaml")
    composition_position = text.index('-k "$STAGE5_OVERLAY"')
    assert crd_position < composition_position
    assert "applicationset-crd-v3.5.3.yaml" in text
    assert "appproject-crd-v3.5.3.yaml" in text
    assert '--field-manager="$FIELD_MANAGER"' in text


def test_orchestrator_preserves_existing_apply_ownership_boundaries() -> None:
    text = script_text()

    assert 'FIELD_MANAGER="vuln-mlops-stage4"' in text
    assert 'kubectl apply -k "$STAGE3_OVERLAY"' in text
    assert 'restore_existing_git_baseline' in text
    assert text.index("restore_existing_git_baseline") < text.rindex(
        "apply_stage_composition"
    )

    stage3_overlay = (SCRIPT.parent / "stage-03" / "kustomization.yaml").read_text(
        encoding="utf-8"
    )
    assert "../../../lab/stages/stage-03-monitoring" in stage3_overlay
    assert "stage-04" not in stage3_overlay
    assert "stage-05" not in stage3_overlay


def test_orchestrator_waits_for_every_stage_workload() -> None:
    text = script_text()

    expected = [
        "modelgate-lab|deployment/modelgate",
        "stage-01-canary|deployment/lab-canary",
        "stage-03-monitoring|deployment/prometheus",
        "stage-03-monitoring|deployment/grafana",
        "stage-03-monitoring|deployment/credential-broker",
        "stage-04-gitops|deployment/argocd-redis",
        "stage-04-gitops|deployment/argocd-repo-server",
        "stage-04-gitops|statefulset/argocd-application-controller",
        "stage-04-gitops|deployment/gitea",
        "stage-05-runtime|deployment/runtime-builder",
    ]
    for workload in expected:
        assert workload in text


def test_orchestrator_bootstraps_the_fixed_git_boundary() -> None:
    text = script_text()

    assert 'GITEA_USER="stage3-lab-writer"' in text
    assert 'GITEA_REPOSITORY="vuln-mlops-gitops"' in text
    assert 'GIT_BRANCH="stage4-lab"' in text
    assert 'STAGE5_BASE="${ROOT_DIR}/lab/stages/stage-05-runtime/runtime-builder-base.yaml"' in text
    assert 'runtime-builder/deployment.yaml' in text
    assert 'install_scope_hook' in text
    assert 'git clone \\' in text
    assert '--branch "$GIT_BRANCH"' in text
    assert 'git -C "$repository_dir" diff --cached --quiet' in text
    assert 'git -C "$repository_dir" push origin "HEAD:${GIT_BRANCH}"' in text
    assert 'sync" == "Synced"' in text
    assert 'health" == "Healthy"' in text
    assert 'revision" == "$expected_revision"' in text


def test_orchestrator_has_deploy_reset_and_status_modes() -> None:
    text = script_text()

    assert "deploy|accept|reset|status" in text
    assert "reset_transient_resources" in text
    assert "show_status" in text
    assert "--skip-foundation" in text
    assert "--auto-approve" in text


def test_orchestrator_runs_acceptance_only_after_a_fresh_reset() -> None:
    text = script_text()
    accept_case = text[text.index("  accept)") :]

    assert 'ACCEPTANCE_SCRIPT="${SCRIPT_DIR}/acceptance.sh"' in text
    assert 'bash "$ACCEPTANCE_SCRIPT"' in accept_case
    assert accept_case.index("reset_transient_resources") < accept_case.index(
        'bash "$ACCEPTANCE_SCRIPT"'
    )


def test_acceptance_runs_stage_1_through_5_in_order() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")
    markers = [
        "[Stage 1]",
        "[Stage 2]",
        "[Stage 3]",
        "[Stage 4]",
        "[Stage 5]",
        "[Cleanup]",
    ]

    positions = [text.index(marker) for marker in markers]
    assert positions == sorted(positions)
    assert 'poc/ssrf_canary.py' in text
    assert 'poc/rce_marker.py' in text
    assert 'job/stage-02-secret-reader' in text
    assert 'stage-03/datasources' in text
    assert 'stage-03/query' in text
    assert 'stage-03/exchange/${stage3_ref}' in text
    assert 'wait_for_participant_argo_revision "$stage5_revision"' in text
    assert '["git_gateway"]' in text
    assert 'stage-04/application' in text
    assert '["runtime_relay"]' in text
    assert 'curl -fsS -X POST "${modelgate_url}${runtime_relay}"' in text


def test_acceptance_restores_the_reviewed_git_baseline() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")

    assert 'STAGE5_BASE=' in text
    assert 'STAGE5_DESIRED=' in text
    assert 'RESTORE_GIT_BASELINE=true' in text
    assert "point_git_remote_at_current_forward" in text
    assert 'remote set-url origin "$remote_url"' in text
    assert "restore runtime-builder baseline after acceptance" in text
    assert 'wait_for_argo_revision "$baseline_revision"' in text


def test_acceptance_uses_participant_runtime_relay_instead_of_operator_exec() -> None:
    text = ACCEPTANCE.read_text(encoding="utf-8")
    stage5 = text[text.index("[Stage 5]") : text.index("[Cleanup]")]

    assert "kubectl exec" not in stage5
    assert "crictl" not in stage5
    assert "stage-05/runtime/proof" in stage5
    assert "body_status" in stage5
