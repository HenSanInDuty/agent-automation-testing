"""Private, versioned text-only transport for advisory Codex test generation."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from auto_at.contracts.codex_bridge import CodexUsage, FailureCode
from auto_at.contracts.generation import GeneratedTestPlannerOutput, VisionGroundedPlannerOutput
from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationProviderPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["codex_cli", "huggingface", "openrouter"]
    model: str = Field(min_length=1, max_length=200)
    text_transfer_accepted: bool = False
    max_seconds: int = Field(default=120, ge=10, le=120)

    @model_validator(mode="after")
    def codex_model(self):
        if self.provider == "codex_cli" and self.model != "gpt-6-luna":
            raise ValueError("unsupported Codex generation model")
        return self


class CodexGenerationJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    protocol: Literal["generation-v1"] = "generation-v1"
    job_id: UUID
    bridge_id: UUID
    tenant_id: str = Field(min_length=1, max_length=200)
    project_id: UUID
    correlation_id: UUID
    model: Literal["gpt-6-luna"] = "gpt-6-luna"
    stage: Literal["generation"] = "generation"
    kind: Literal["text", "vision"]
    prompt_version: Literal["codex-generation-v1"] = "codex-generation-v1"
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    input_bytes: int = Field(ge=1, le=100_000)
    max_output_bytes: int = Field(default=65_536, ge=1, le=65_536)
    created_at: datetime
    deadline: datetime

    @model_validator(mode="after")
    def bounded_deadline(self):
        if (self.created_at.tzinfo is None or self.deadline.tzinfo is None
                or not 0 < (self.deadline - self.created_at).total_seconds() <= 120):
            raise ValueError("invalid generation deadline")
        return self


class GenerationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    expires_at: datetime


class CodexGenerationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output: GeneratedTestPlannerOutput | VisionGroundedPlannerOutput | None = None
    failure_code: FailureCode | None = None
    usage: CodexUsage | None = None

    @model_validator(mode="after")
    def exclusive_result(self):
        if (self.output is None) == (self.failure_code is None):
            raise ValueError("exactly one generation result required")
        return self
