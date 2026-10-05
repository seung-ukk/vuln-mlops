from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$")
    artifact_uri: str = Field(min_length=1, max_length=2048)
    description: str | None = Field(default=None, max_length=2048)


class WebhookEvent(BaseModel):
    entity: str = Field(min_length=1, max_length=64)
    action: str = Field(min_length=1, max_length=64)


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    url: str = Field(min_length=1, max_length=2048)
    events: list[WebhookEvent] = Field(min_length=1)
    description: str | None = Field(default=None, max_length=1024)
    secret: str | None = Field(default=None, max_length=512)


class WebhookTest(BaseModel):
    event: WebhookEvent | None = None


class LegacyWebhookProbe(BaseModel):
    service: str = Field(description="Synthetic in-cluster service name")
    namespace: str | None = Field(
        description="Kubernetes namespace when running in the EKS lab"
    )
    port: int = Field(description="Legacy probe TCP port")
    path: str = Field(description="Legacy probe HTTP path")


class SystemInfo(BaseModel):
    service: str
    environment: str
    legacy_webhook_probe: LegacyWebhookProbe


class FootholdRuleReview(BaseModel):
    namespace: str
    resource_rules: list[dict[str, Any]]
    non_resource_rules: list[dict[str, Any]]
    incomplete: bool


class Stage2JobStatus(BaseModel):
    name: str
    namespace: str
    created: bool
    active: int
    succeeded: int
    failed: int


class Stage2JobLog(BaseModel):
    name: str
    namespace: str
    pod: str
    encoded_proof: str
    next: str


class Stage3Datasource(BaseModel):
    uid: str
    name: str
    type: str


class Stage3DatasourceList(BaseModel):
    datasources: list[Stage3Datasource]
    next: str


class Stage3Topology(BaseModel):
    application: str
    branch: str
    broker: str
    credential_ref: str
    destination: str
    path: str
    repository: str
    next: str


class Stage3Credential(BaseModel):
    flag: str
    username: str
    token: str
    repository: str
    branch: str
    path: str
    application: str
    destination: str
    git_gateway: str
    application_status: str


class Stage4ApplicationStatus(BaseModel):
    name: str
    namespace: str
    sync: str
    health: str
    revision: str
    stage4_proof: str | None
    stage5_mode: str | None
    runtime_relay: str | None
    builder_endpoint: str | None


class Stage5RuntimeProof(BaseModel):
    proof: str
    success: bool
    evidence: str
    flag: str


class Stage5BuildRequest(BaseModel):
    source_ref: str = Field(min_length=1, max_length=128)


class Stage5BuildStatus(BaseModel):
    status: str


class Stage5IamProof(BaseModel):
    account: str
    role: str
    flag: str


JsonObject = dict[str, Any]
