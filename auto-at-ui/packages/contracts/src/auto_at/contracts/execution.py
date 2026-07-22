from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, HttpUrl


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

