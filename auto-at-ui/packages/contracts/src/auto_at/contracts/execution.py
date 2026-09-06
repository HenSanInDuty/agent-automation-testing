from __future__ import annotations

import hashlib
import re
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

_SHA256 = r"^[a-f0-9]{64}$"
_DISALLOWED_SOURCE_PATTERNS = (
    re.compile(r"\b(?:require|eval|Function|fetch|XMLHttpRequest|WebSocket|Worker)\b"),
    re.compile(r"\b(?:process|Buffer|__dirname|__filename)\b"),
    re.compile(r"\b(?:child_process|cluster|dgram|dns|fs|net|tls|vm|worker_threads)\b"),
    re.compile(r"\bimport\s*\("),
)
_IMPORT_PATTERN = re.compile(
    r"\b(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?(?P<quote>['\"])(?P<module>[^'\"]+)(?P=quote)"
)


def sha256_text(value: str) -> str:
    """Return the lowercase SHA-256 digest used by v1 text-bearing contracts."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def validate_playwright_test_source(value: str) -> str:
    """Reject source that exceeds the deliberately narrow generated-test subset."""
    for pattern in _DISALLOWED_SOURCE_PATTERNS:
        if pattern.search(value):
            raise ValueError("generated source uses a prohibited API")
    for match in _IMPORT_PATTERN.finditer(value):
        if match.group("module") != "@playwright/test":
            raise ValueError("generated source may import only @playwright/test")
    return value


class TargetType(StrEnum):
    WEB_UI = "web_ui"
    API = "api"
    GAME = "game"


class RunStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERRORED = "errored"
    SKIPPED = "skipped"


class ArtifactPolicy(BaseModel):
    trace_on_failure: bool = True
    video_on_failure: bool = True
    screenshot_on_failure: bool = True
    # Visual evidence is retained for successful runs by default so reviewers can
    # inspect what the browser actually did, not merely its terminal verdict.
    trace_on_success: bool = True
    video_on_success: bool = True
    screenshot_on_success: bool = True
    retain_days: int = Field(default=30, ge=1, le=3650)


class TestExecutionRequest(BaseModel):
    contract_version: Literal["v1"] = "v1"
    run_id: UUID = Field(default_factory=uuid4)
    correlation_id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    test_case_id: str = Field(min_length=1, max_length=200)
    target_type: TargetType
    target_url: HttpUrl | None = None
    revision: str = Field(min_length=7, max_length=128)
    runner_config: dict[str, Any] = Field(default_factory=dict)
    artifact_policy: ArtifactPolicy = Field(default_factory=ArtifactPolicy)


class PlaywrightTestSourceMode(BaseModel):
    """Validated v1 runner configuration for approved generated source."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["playwright_test_source"] = "playwright_test_source"
    playwright_test_source: str = Field(min_length=1, max_length=100_000)
    source_hash: str = Field(pattern=_SHA256)
    allowed_origins: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_source(self) -> PlaywrightTestSourceMode:
        validate_playwright_test_source(self.playwright_test_source)
        if self.source_hash != sha256_text(self.playwright_test_source):
            raise ValueError("source_hash must match playwright_test_source")
        for origin in self.allowed_origins:
            if origin == "*":
                continue
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.path not in {"", "/"}
                or parsed.query
                or parsed.fragment
                or parsed.username
                or parsed.password
            ):
                raise ValueError("allowed_origins must contain canonical HTTP(S) origins")
        return self


class Artifact(BaseModel):
    kind: str
    uri: str
    content_type: str | None = None


class TestExecutionResult(BaseModel):
    contract_version: Literal["v1"] = "v1"
    run_id: UUID
    correlation_id: UUID
    status: RunStatus
    started_at: str
    completed_at: str
    summary: str
    artifacts: list[Artifact] = Field(default_factory=list)
    runner_metadata: dict[str, Any] = Field(default_factory=dict)
