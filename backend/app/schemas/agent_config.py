"""
schemas/agent_config.py – Pydantic schemas for pipeline agent configurations.

Changes in V2 (Phase 7-9):
- IDs are now MongoDB ObjectId strings instead of ints
- AgentConfigCreate added for Phase 8 (Dynamic Agent Management)
- VALID_STAGES validation removed — stages are now dynamic, stored in MongoDB
- is_custom field added to distinguish built-in vs user-created agents
- AgentConfigGrouped includes a `custom` bucket for non-standard stages
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.llm_profile import LLMProfileResponse

# ─────────────────────────────────────────────────────────────────────────────
# Create — used for Phase 8 dynamic agent creation
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigCreate(BaseModel):
    """Schema for creating a new custom agent (Phase 8: Dynamic Agent Management)."""

    agent_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]{2,49}$",
        description="Unique snake_case identifier (3-50 chars, must start with a letter)",
    )
    display_name: str = Field(..., min_length=2, max_length=150)
    stage: str = Field(..., description="stage_id of an existing stage config")

    # CrewAI prompts
    role: str = Field(..., min_length=10)
    goal: str = Field(..., min_length=10)
    backstory: str = Field(..., min_length=10)

    # LLM override — None means "use global default profile"
    llm_profile_id: Optional[str] = Field(
        default=None,
        description="MongoDB ObjectId of the LLM profile to use. None → inherit global default.",
    )

    # Behaviour flags
    enabled: bool = True
    verbose: bool = False
    max_iter: int = Field(default=5, ge=1, le=50)


# ─────────────────────────────────────────────────────────────────────────────
# Update — all fields optional so partial updates are supported (PUT / PATCH)
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigUpdate(BaseModel):
    """
    Payload for PUT /admin/agent-configs/{agent_id}.
    All fields are optional — only supplied fields are updated.
    Stage validation is intentionally omitted; stages are now dynamic.
    """

    display_name: Optional[str] = Field(default=None, min_length=1, max_length=150)
    stage: Optional[str] = None

    role: Optional[str] = Field(default=None, min_length=1)
    goal: Optional[str] = Field(default=None, min_length=1)
    backstory: Optional[str] = Field(default=None, min_length=1)

    llm_profile_id: Optional[str] = None  # MongoDB ObjectId string

    enabled: Optional[bool] = None
    verbose: Optional[bool] = None
    max_iter: Optional[int] = Field(default=None, ge=1, le=50)


# ─────────────────────────────────────────────────────────────────────────────
# Response — what the API returns
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigResponse(BaseModel):
    """Full agent config returned by the API, including joined LLM profile."""

    model_config = ConfigDict(from_attributes=True)

    id: str  # MongoDB ObjectId string
    agent_id: str = Field(description="Unique slug, e.g. 'requirement_analyzer'")
    display_name: str
    stage: str

    # CrewAI prompts
    role: str
    goal: str
    backstory: str

    # FK + joined relation
    llm_profile_id: Optional[str] = None  # MongoDB ObjectId string
    llm_profile: Optional[LLMProfileResponse] = None

    # Behaviour
    enabled: bool
    verbose: bool
    max_iter: int

    # Provenance
    is_custom: bool = False  # True for user-created agents, False for built-ins

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

    id: str  # MongoDB ObjectId string
    agent_id: str
    display_name: str
    stage: str
    llm_profile_id: Optional[str] = None  # MongoDB ObjectId string
    llm_profile_name: Optional[str] = Field(
        default=None,
        description="Display name of the assigned LLM profile, if any.",
    )
    enabled: bool
    verbose: bool
    max_iter: int
    is_custom: bool = False  # True for user-created agents, False for built-ins
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Grouped list response — agents grouped by stage for the admin UI
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigGrouped(BaseModel):
    """
    Response shape for GET /admin/agent-configs?grouped=true.
    Groups agents by pipeline stage for easier rendering in the admin UI.
    Agents in non-standard stages fall into the `custom` bucket.
    """

    ingestion: list[AgentConfigSummary] = []
    testcase: list[AgentConfigSummary] = []
    execution: list[AgentConfigSummary] = []
    reporting: list[AgentConfigSummary] = []
    custom: list[AgentConfigSummary] = []  # agents in dynamically-created stages

    @classmethod
    def from_list(cls, agents: list[AgentConfigSummary]) -> "AgentConfigGrouped":
        known_stages = {"ingestion", "testcase", "execution", "reporting"}
        grouped: dict[str, list[AgentConfigSummary]] = {
            "ingestion": [],
            "testcase": [],
            "execution": [],
            "reporting": [],
            "custom": [],
        }
        for agent in agents:
            if agent.stage in known_stages:
                grouped[agent.stage].append(agent)
            else:
                grouped["custom"].append(agent)
        return cls(**grouped)


# ─────────────────────────────────────────────────────────────────────────────
# Reset response
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigResetResponse(BaseModel):
    """Returned after a reset operation."""

    agent_id: str
    message: str = "Agent config has been reset to default values."
    config: AgentConfigResponse
