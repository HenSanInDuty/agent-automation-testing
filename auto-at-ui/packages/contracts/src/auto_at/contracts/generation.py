"""Versioned contracts for governed generated Web UI test drafts."""

from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from auto_at.contracts.execution import (
    PlaywrightTestSourceMode,
    TestExecutionRequest,
    sha256_text,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_SHA256 = r"^[a-f0-9]{64}$"
_CREDENTIAL_PATTERNS = (
    re.compile(r"(?i)\b(password|passwd|token|api[_ -]?key|secret)\b\s*([:=]|is)\s*([^\s,;]+)"),
    re.compile(r"(?i)(https?://[^\s/:@]+:)([^@\s]+)(@)"),
)
_REDACTED = "[REDACTED]"
WILDCARD_ORIGIN = "*"


def redact_generation_request(value: str) -> str:
    """Remove common credential values before text crosses the planning boundary."""
    redacted = value
    redacted = _CREDENTIAL_PATTERNS[0].sub(r"\1\2 " + _REDACTED, redacted)
    return _CREDENTIAL_PATTERNS[1].sub(r"\1" + _REDACTED + r"\3", redacted)


def request_hash(value: str) -> str:
    """Return the reproducibility hash of the already-redacted request text."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_origin(value: str) -> str:
    """Validate and normalize an HTTP(S) origin for policy comparison."""
    if value == WILDCARD_ORIGIN:
        return WILDCARD_ORIGIN
    parsed = urlsplit(value)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("origin must use http or https and include a host")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("origin must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("origin must not include a path, query, or fragment")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("origin has an invalid port") from error
    host = parsed.hostname.encode("idna").decode("ascii").lower()
    if ":" in host:
        host = f"[{host}]"
    scheme = parsed.scheme.lower()
    if port is None or (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def origin_for_url(value: str) -> str:
    """Extract a canonical HTTP(S) origin from a destination URL."""
    parsed = urlsplit(value)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("target URL must not contain credentials")
    return canonical_origin(f"{parsed.scheme}://{parsed.netloc}")


class ProjectExecutionPolicy(BaseModel):
    """Project-owned destination constraints for generated Web UI execution."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = "v1"
    project_id: UUID
    allowed_origins: list[str] = Field(min_length=1, max_length=100)

    @field_validator("allowed_origins")
    @classmethod
    def normalize_origins(cls, origins: list[str]) -> list[str]:
        normalized = [canonical_origin(origin) for origin in origins]
        if len(set(normalized)) != len(normalized):
            raise ValueError("allowed_origins must be unique after canonicalization")
        return normalized

    def allows(self, target_url: str) -> bool:
        origin = origin_for_url(target_url)
        return WILDCARD_ORIGIN in self.allowed_origins or origin in self.allowed_origins


class DraftState(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class PlanningProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=100)
    redaction_policy_version: str = Field(min_length=1, max_length=100)


class TestGenerationPlanningRequest(BaseModel):
    """Only redacted natural-language input is valid at the planner boundary."""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = "v1"
    id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID
    project_id: UUID
    target_url: str
    redacted_request: str = Field(min_length=1, max_length=8_000)
    request_hash: str = Field(pattern=_SHA256)

    @field_validator("target_url")
    @classmethod
    def require_http_origin(cls, value: str) -> str:
        origin_for_url(value)
        return value

    @field_validator("redacted_request")
    @classmethod
    def reject_unredacted_credentials(cls, value: str) -> str:
        secrets = _CREDENTIAL_PATTERNS[0].findall(value)
        contains_unredacted_secret = any(secret != _REDACTED for _, _, secret in secrets)
        if contains_unredacted_secret or _CREDENTIAL_PATTERNS[1].search(value):
            raise ValueError("planning request must be redacted before persistence or model use")
        return value

    @model_validator(mode="after")
    def validate_request_hash(self) -> TestGenerationPlanningRequest:
        if self.request_hash != request_hash(self.redacted_request):
            raise ValueError("request_hash must match redacted_request")
        return self


class GeneratedTestDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = "v1"
    id: UUID = Field(default_factory=uuid4)
    planning_request_id: UUID
    correlation_id: UUID
    state: DraftState = DraftState.PENDING_REVIEW
    title: str = Field(min_length=1, max_length=200)
    playwright_test_source: str = Field(min_length=1, max_length=100_000)
    source_hash: str = Field(pattern=_SHA256)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)
    provenance: PlanningProvenance
    linked_test_case_id: str | None = Field(default=None, max_length=200)
    linked_run_id: UUID | None = None

    @model_validator(mode="after")
    def validate_source_hash(self) -> GeneratedTestDraft:
        if self.source_hash != sha256_text(self.playwright_test_source):
            raise ValueError("source_hash must match playwright_test_source")
        return self


class GeneratedTestPlannerOutput(BaseModel):
    """Untrusted structured response accepted from the tool-less planner."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    playwright_test_source: str = Field(min_length=1, max_length=100_000)
    assumptions: list[str] = Field(default_factory=list, max_length=50)
    stop_conditions: list[str] = Field(default_factory=list, max_length=50)


class DraftDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: str = "v1"
    draft_id: UUID
    approved: bool
    decided_by: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=4_000)
    linked_test_case_id: str | None = Field(default=None, max_length=200)
    linked_run_id: UUID | None = None


def validate_generated_execution_request(
    request: TestExecutionRequest, policy: ProjectExecutionPolicy
) -> PlaywrightTestSourceMode:
    """Validate a generated-source v1 request against its project policy before dispatch."""
    if request.project_id != policy.project_id:
        raise ValueError("execution policy belongs to a different project")
    if request.target_type.value != "web_ui":
        raise ValueError("generated test source supports only web_ui targets")
    if request.target_url is None or not policy.allows(str(request.target_url)):
        raise ValueError("target URL origin is not allowed by the project execution policy")
    runner_config = dict(request.runner_config)
    # The policy is control-plane authority.  Attach its canonical snapshot at
    # dispatch time rather than trusting a draft or an older caller to supply it.
    runner_config["allowed_origins"] = policy.allowed_origins
    return PlaywrightTestSourceMode.model_validate(runner_config)
