"""Retained, redacted page inventory; never authorizes a browser action."""

from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from auto_at.contracts.vision import Fingerprint, validate_locator_value
from pydantic import BaseModel, ConfigDict, Field, field_validator


def safe_page_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or len(value) > 2000
            or any(ord(char) < 32 for char in value)):
        raise ValueError("invalid redacted page URL")
    return value


class VisualPageControl(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    key: Fingerprint
    button_kind: Literal["native", "styled_link", "custom"] | None = None
    role: str = Field(pattern=r"^[a-z]{1,32}$")
    name: str = Field(max_length=120)
    status: Literal["pending", "queued", "completed", "failed", "rejected"] = "pending"
    proposal_id: UUID | None = None
    operation_id: UUID | None = None

    @field_validator("name")
    @classmethod
    def safe_name(cls, value):
        if value:
            validate_locator_value(value)
        return value


class VisualPageInventory(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    state_id: UUID
    checkpoint_id: UUID
    page_url: str | None = None
    url_fingerprint: Fingerprint
    controls: tuple[VisualPageControl, ...] = Field(default=(), max_length=100)
    interaction_scope: Literal["all", "buttons", "visual_buttons"] = "all"
    truncated: bool = False
    scrollable: bool = False
    skipped_count: int = Field(default=0, ge=0, le=5000)

    _safe_url = field_validator("page_url")(safe_page_url)
