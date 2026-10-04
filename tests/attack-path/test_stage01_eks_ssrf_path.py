from pathlib import Path

import yaml

from poc.ssrf_canary import CANARY_TARGETS, CANARY_VALUE, selected_canary_target


ROOT = Path(__file__).resolve().parents[2]
OVERLAY = ROOT / "deploy" / "eks-lab" / "stage-03"


def canary_resources() -> dict[tuple[str, str], dict]:
    documents = yaml.safe_load_all(
        (OVERLAY / "ssrf-canary.yaml").read_text(encoding="utf-8")
    )
    return {
        (document["kind"], document["metadata"]["name"]): document
        for document in documents
    }


def test_eks_poc_uses_only_the_fixed_internal_canary(monkeypatch) -> None:
    assert CANARY_VALUE == "MODELGATE_INTERNAL_SSRF_PROOF"
    assert CANARY_TARGETS == {
        "compose": "http://lab-canary:9000/canary",
        "eks": "http://lab-canary.stage-01-canary.svc.cluster.local:9000/canary",
    }

    monkeypatch.setenv("POC_CANARY_TARGET", "eks")
    assert selected_canary_target() == CANARY_TARGETS["eks"]


def test_eks_overlay_composes_the_canary_and_exact_modelgate_patch() -> None:
    overlay = yaml.safe_load(
        (OVERLAY / "kustomization.yaml").read_text(encoding="utf-8")
    )
    assert overlay["resources"].count("ssrf-canary.yaml") == 1
    canary_patches = [
        patch
        for patch in overlay["patches"]
        if patch["path"] == "modelgate-canary-egress-patch.yaml"
    ]
    assert canary_patches == [
        {
            "path": "modelgate-canary-egress-patch.yaml",
            "target": {
                "group": "networking.k8s.io",
                "version": "v1",
                "kind": "NetworkPolicy",
                "name": "modelgate",
                "namespace": "modelgate-lab",
            },
        }
    ]


def test_eks_canary_is_a_restricted_cluster_only_workload() -> None:
    resources = canary_resources()
    namespace = resources[("Namespace", "stage-01-canary")]
    deployment = resources[("Deployment", "lab-canary")]
    service = resources[("Service", "lab-canary")]

    assert namespace["metadata"]["labels"] == {
        "pod-security.kubernetes.io/enforce": "restricted",
        "pod-security.kubernetes.io/audit": "restricted",
        "pod-security.kubernetes.io/warn": "restricted",
    }
    assert service["spec"]["type"] == "ClusterIP"
    assert service["spec"]["ports"] == [
        {"name": "http", "port": 9000, "targetPort": "http"}
    ]

    pod_spec = deployment["spec"]["template"]["spec"]
    container = pod_spec["containers"][0]
    assert pod_spec["automountServiceAccountToken"] is False
    assert pod_spec["securityContext"]["runAsUser"] == 10001
    assert pod_spec["securityContext"]["seccompProfile"]["type"] == "RuntimeDefault"
    assert container["image"] == "ghcr.io/seung-ukk/vuln-mlops:main"
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }


def test_network_policies_allow_only_modelgate_to_reach_canary() -> None:
    canary_policy = canary_resources()[("NetworkPolicy", "lab-canary")]
    assert canary_policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert canary_policy["spec"]["egress"] == []
    assert canary_policy["spec"]["ingress"] == [
        {
            "from": [
                {
                    "namespaceSelector": {
                        "matchLabels": {
                            "kubernetes.io/metadata.name": "modelgate-lab"
                        }
                    },
                    "podSelector": {
                        "matchLabels": {"app.kubernetes.io/name": "modelgate"}
                    },
                }
            ],
            "ports": [{"protocol": "TCP", "port": 9000}],
        }
    ]

    patch = yaml.safe_load(
        (OVERLAY / "modelgate-canary-egress-patch.yaml").read_text(encoding="utf-8")
    )
    assert patch == [
        {
            "op": "add",
            "path": "/spec/egress/-",
            "value": {
                "to": [
                    {
                        "namespaceSelector": {
                            "matchLabels": {
                                "kubernetes.io/metadata.name": "stage-01-canary"
                            }
                        },
                        "podSelector": {
                            "matchLabels": {
                                "app.kubernetes.io/name": "lab-canary"
                            }
                        },
                    }
                ],
                "ports": [{"protocol": "TCP", "port": 9000}],
            },
        }
    ]
