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


JsonObject = dict[str, Any]
