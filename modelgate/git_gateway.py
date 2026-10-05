from __future__ import annotations

import httpx


GITEA_BASE_URL = "http://gitea.stage-04-gitops.svc:3000"
GITEA_REPOSITORY_PATH = "/stage3-lab-writer/vuln-mlops-gitops.git"
STAGE4_REPOSITORY = "vuln-mlops-gitops"
STAGE4_GIT_MAX_BYTES = 8 * 1024 * 1024
STAGE4_GIT_SERVICES = frozenset({"git-upload-pack", "git-receive-pack"})


def build_git_gateway_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=GITEA_BASE_URL,
        follow_redirects=False,
        timeout=httpx.Timeout(35.0),
    )
