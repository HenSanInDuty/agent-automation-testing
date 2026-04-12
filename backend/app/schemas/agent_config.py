"""
schemas/agent_config.py – Pydantic schemas for pipeline agent configurations.

Changes in V2 (Phase 7-9):
- IDs are now MongoDB ObjectId strings instead of ints
- AgentConfigCreate added for Phase 8 (Dynamic Agent Management)
- VALID_STAGES validation removed — stages are now dynamic, stored in MongoDB
- is_custom field added to distinguish built-in vs user-created agents
- AgentConfigGrouped includes a `custom` bucket for non-standard stages

Changes in V4:
- AgentGroupEntry added: represents a single stage group with its DB metadata and agents
- AgentConfigGroupedResponse added: dynamic grouping response driven by StageConfigDocument
  records from MongoDB (replaces static AgentConfigGrouped for the main list endpoint)
- AgentConfigGrouped retained for backward compatibility with existing imports
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
    stage: str = Field(
        default="custom",
        description="stage_id of a stage config. Defaults to 'custom' in V3 DAG mode.",
    )

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
# Dynamic grouped response — V4, driven by StageConfigDocument in MongoDB
# ─────────────────────────────────────────────────────────────────────────────


class AgentGroupEntry(BaseModel):
    """One stage group with its metadata and agents."""

    stage_id: str
    display_name: str
    description: Optional[str] = None
    order: int = 0
    color: Optional[str] = None
    icon: Optional[str] = None
    is_builtin: bool = False
    agents: list[AgentConfigSummary] = []


class AgentConfigGroupedResponse(BaseModel):
    """Dynamic agent grouping response — groups loaded from DB stage configs."""

    groups: list[AgentGroupEntry]
    total_agents: int

    @classmethod
    async def from_list(
        cls, agents: list[AgentConfigSummary]
    ) -> "AgentConfigGroupedResponse":
        """Group agents by their stage, using stage configs from DB.

        Args:
            agents: Flat list of agent summaries.

        Returns:
            An :class:`AgentConfigGroupedResponse` with agents grouped by stage.
        """
        from app.db.models import StageConfigDocument

        # Load all stages from DB, sorted by order
        stages = await StageConfigDocument.find_all().sort("+order").to_list()

        # Build a bucket for every known stage
        groups_dict: dict[str, list[AgentConfigSummary]] = {
            s.stage_id: [] for s in stages
        }

        # Assign agents to their stage bucket
        for agent in agents:
            stage_id = agent.stage or "custom"
            if stage_id in groups_dict:
                groups_dict[stage_id].append(agent)
            else:
                # Agent references a stage that no longer exists → fall into custom
                groups_dict.setdefault("custom", [])
                groups_dict["custom"].append(agent)

        # Build the response list
        groups: list[AgentGroupEntry] = []
        for stage in stages:
            groups.append(
                AgentGroupEntry(
                    stage_id=stage.stage_id,
                    display_name=stage.display_name,
                    description=stage.description,
                    order=stage.order,
                    color=stage.color,
                    icon=stage.icon,
                    is_builtin=stage.is_builtin,
                    agents=groups_dict.get(stage.stage_id, []),
                )
            )

        return cls(groups=groups, total_agents=len(agents))


# ─────────────────────────────────────────────────────────────────────────────
# Reset response
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigResetResponse(BaseModel):
    """Returned after a reset operation."""

    agent_id: str
    message: str = "Agent config has been reset to default values."
    config: AgentConfigResponse
