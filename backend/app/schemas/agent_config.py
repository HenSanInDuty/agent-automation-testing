from __future__ import annotations

from datetime import datetime
from typing import Optional

from app.schemas.llm_profile import LLMProfileResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

# ─────────────────────────────────────────────────────────────────────────────
# Enums / Constants
# ─────────────────────────────────────────────────────────────────────────────

VALID_STAGES = {"ingestion", "testcase", "execution", "reporting"}


# ─────────────────────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigBase(BaseModel):
    """Shared fields used in create / update payloads."""

    display_name: str = Field(..., min_length=1, max_length=150)
    stage: str = Field(..., description="ingestion | testcase | execution | reporting")

    # CrewAI prompts
    role: str = Field(..., min_length=1, description="CrewAI agent role")
    goal: str = Field(..., min_length=1, description="CrewAI agent goal")
    backstory: str = Field(..., min_length=1, description="CrewAI agent backstory")

    # LLM override — None means "use global default profile"
    llm_profile_id: Optional[int] = Field(
        default=None,
        description="ID of the LLM profile to use. None → inherit global default.",
    )

    # Behaviour flags
    enabled: bool = Field(
        default=True, description="Whether this agent runs in the pipeline"
    )
    verbose: bool = Field(
        default=False, description="Enable CrewAI verbose logging for this agent"
    )
    max_iter: int = Field(
        default=5, ge=1, le=50, description="Max LLM iterations per task"
    )

    @model_validator(mode="after")
    def validate_stage(self) -> "AgentConfigBase":
        if self.stage not in VALID_STAGES:
            raise ValueError(
                f"stage must be one of {sorted(VALID_STAGES)}, got {self.stage!r}"
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Update — all fields optional so partial updates are supported (PATCH)
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigUpdate(BaseModel):
    """
    Payload for PUT /admin/agent-configs/{agent_id}.
    All fields are optional — only supplied fields are updated.
    """

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    stage: Optional[str] = None

    role: Optional[str] = Field(default=None, min_length=1)
    goal: Optional[str] = Field(default=None, min_length=1)
    backstory: Optional[str] = Field(default=None, min_length=1)

    llm_profile_id: Optional[int] = None

    enabled: Optional[bool] = None
    verbose: Optional[bool] = None
    max_iter: Optional[int] = Field(default=None, ge=1, le=50)

    @model_validator(mode="after")
    def validate_stage_if_provided(self) -> "AgentConfigUpdate":
        if self.stage is not None and self.stage not in VALID_STAGES:
            raise ValueError(
                f"stage must be one of {sorted(VALID_STAGES)}, got {self.stage!r}"
            )
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Response — what the API returns
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigResponse(BaseModel):
    """Full agent config returned by the API, including joined LLM profile."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str = Field(description="Unique slug, e.g. 'requirement_analyzer'")
    display_name: str
    stage: str

    # CrewAI prompts
    role: str
    goal: str
    backstory: str

    # FK + joined relation
    llm_profile_id: Optional[int] = None
    llm_profile: Optional[LLMProfileResponse] = None

    # Behaviour
    enabled: bool
    verbose: bool
    max_iter: int

    # Timestamps
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Summary — lightweight version for list views
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigSummary(BaseModel):
    """
    Lightweight version of AgentConfigResponse used in list endpoints.
    Omits long text fields (role, goal, backstory) to reduce payload size.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    agent_id: str
    display_name: str
    stage: str
    llm_profile_id: Optional[int] = None
    llm_profile_name: Optional[str] = Field(
        default=None,
        description="Display name of the assigned LLM profile, if any.",
    )
    enabled: bool
    verbose: bool
    max_iter: int
    updated_at: datetime

    @model_validator(mode="after")
    def populate_llm_profile_name(self) -> "AgentConfigSummary":
        # When built from_attributes, llm_profile is not a field here
        # so we rely on the caller to populate llm_profile_name directly.
        return self


# ─────────────────────────────────────────────────────────────────────────────
# Grouped list response — agents grouped by stage for the admin UI
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigGrouped(BaseModel):
    """
    Response shape for GET /admin/agent-configs?grouped=true.
    Groups agents by pipeline stage for easier rendering in the admin UI.
    """

    ingestion: list[AgentConfigSummary] = []
    testcase: list[AgentConfigSummary] = []
    execution: list[AgentConfigSummary] = []
    reporting: list[AgentConfigSummary] = []

    @classmethod
    def from_list(cls, agents: list[AgentConfigSummary]) -> "AgentConfigGrouped":
        grouped: dict[str, list[AgentConfigSummary]] = {
            "ingestion": [],
            "testcase": [],
            "execution": [],
            "reporting": [],
        }
        for agent in agents:
            if agent.stage in grouped:
                grouped[agent.stage].append(agent)
        return cls(**grouped)


# ─────────────────────────────────────────────────────────────────────────────
# Reset response
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigResetResponse(BaseModel):
    """Returned after a reset operation."""

    agent_id: str
    message: str = "Agent config has been reset to default values."
    config: AgentConfigResponse
