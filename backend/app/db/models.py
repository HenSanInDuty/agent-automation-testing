"""
db/models.py – Beanie Document models for MongoDB.

These replace the V1 SQLAlchemy ORM models.  Each Document IS a Pydantic
BaseModel — no separate schema layer is needed for internal operations.

Documents:
    LLMProfileDocument        – LLM provider/model profiles
    AgentConfigDocument       – CrewAI agent configurations
    StageConfigDocument       – Pipeline stage configurations
    NodeType                  – Enum of DAG node types (V3)
    PipelineNodeConfig        – Embedded node definition in a pipeline DAG (V3)
    PipelineEdgeConfig        – Embedded edge definition in a pipeline DAG (V3)
    PipelineTemplateDocument  – Reusable pipeline DAG definition (V3)
    PipelineRunDocument       – Pipeline run records (V3, backward-compat with V2)
    PipelineResultDocument    – Per-node/per-agent output blobs (V3, backward-compat with V2)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from pymongo import IndexModel

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _now() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfileDocument
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfileDocument(Document):
    """MongoDB document that stores one LLM provider/model profile.

    A profile encapsulates everything needed to instantiate a LiteLLM / CrewAI
    ``LLM`` object at runtime: provider name, model identifier, credentials,
    and generation hyper-parameters.

    Only one profile may have ``is_default=True`` at any given time; this
    constraint is enforced at the CRUD layer (see ``db/crud.py``).

    Attributes:
        name:         Human-readable unique identifier shown in the admin UI.
        provider:     LLM provider slug (openai | anthropic | ollama |
                      huggingface | azure_openai | groq).
        model:        Provider-specific model name, e.g. ``"gpt-4o"``.
        api_key:      Raw API key (may be encrypted at rest when
                      ``ENCRYPT_API_KEYS=True``).  Always masked in API
                      responses.
        base_url:     Custom inference endpoint URL (Ollama, Azure, LM Studio,
                      vLLM, etc.).
        temperature:  Sampling temperature in [0, 2].
        max_tokens:   Upper token budget per LLM call.
        is_default:   When ``True`` this profile is used for any agent that
                      has no per-agent override assigned.
        created_at:   UTC timestamp set once on insert.
        updated_at:   UTC timestamp refreshed on every update.
    """

    name: Indexed(str, unique=True)  # type: ignore[valid-type]
    provider: str  # openai | anthropic | ollama | huggingface | azure_openai | groq
    model: str
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 2048
    is_default: bool = False
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "llm_profiles"
        indexes = [
            "provider",
            [("is_default", 1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfigDocument
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfigDocument(Document):
    """MongoDB document that stores the configuration for one CrewAI agent.

    Each of the 19 seeded agents has a unique ``agent_id`` slug that is used
    throughout the codebase to look up configurations at runtime.  Admins can
    customise ``role``, ``goal``, ``backstory``, ``max_iter``, and assign a
    per-agent LLM profile override through the admin UI.

    Attributes:
        agent_id:        Unique slug used in code, e.g. ``"requirement_analyzer"``.
        display_name:    Human-readable name shown in the admin UI.
        stage:           Pipeline stage this agent belongs to
                         (ingestion | testcase | execution | reporting).
        role:            CrewAI agent ``role`` prompt — short noun phrase
                         describing the agent's expertise.
        goal:            CrewAI agent ``goal`` prompt — what the agent is
                         trying to achieve in a single task.
        backstory:       CrewAI agent ``backstory`` prompt — personality and
                         expertise that shape the LLM's behaviour.
        llm_profile_id:  ObjectId string referencing a
                         :class:`LLMProfileDocument`.  ``None`` means "use
                         the global default profile".
        enabled:         When ``False`` the agent is skipped during pipeline
                         execution.
        verbose:         Pass ``verbose=True`` to the underlying CrewAI agent,
                         enabling detailed step logging.
        max_iter:        Maximum number of LLM reasoning iterations per task.
        is_custom:       ``True`` if the record was created by an admin via the
                         UI; ``False`` for the 19 seeded defaults.
        created_at:      UTC timestamp set once on insert.
        updated_at:      UTC timestamp refreshed on every update.
    """

    agent_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    display_name: str
    stage: Indexed(str) = "custom"  # type: ignore[valid-type]
    role: str
    goal: str
    backstory: str
    llm_profile_id: Optional[str] = None  # ObjectId string → ref to LLMProfileDocument
    enabled: bool = True
    verbose: bool = False
    max_iter: int = 5
    is_custom: bool = False  # True if user-created, False if seeded
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "agent_configs"
        indexes = [
            "stage",
            [("stage", 1), ("enabled", 1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# StageConfigDocument
# ─────────────────────────────────────────────────────────────────────────────


class StageConfigDocument(Document):
    """MongoDB document that stores the configuration for one pipeline stage.

    The four built-in stages (ingestion, testcase, execution, reporting) are
    seeded on startup.  Admins may reorder or disable stages, or create
    entirely new custom stages (``is_builtin=False``).

    Stages execute in ascending ``order`` — the four seeded stages use orders
    100, 200, 300, and 400, leaving plenty of room for custom stages to be
    inserted between or after them.

    Attributes:
        stage_id:        Unique slug, e.g. ``"testcase"``.
        display_name:    Human-readable stage name shown in the UI.
        description:     Optional longer description of what this stage does.
        order:           Ascending execution order; lower values run first.
        enabled:         When ``False`` the entire stage is skipped.
        crew_type:       Execution strategy —
                         ``"pure_python"`` | ``"crewai_sequential"`` |
                         ``"crewai_hierarchical"``.
        timeout_seconds: Maximum wall-clock seconds allowed for this stage
                         (0 = no timeout).
        is_builtin:      ``True`` for the four seeded stages; ``False`` for
                         admin-created stages.  Builtin stages cannot be
                         deleted.
        input_schema:    Optional JSON-Schema dict describing expected stage
                         inputs (informational / validation use).
        output_schema:   Optional JSON-Schema dict describing expected stage
                         outputs.
        created_at:      UTC timestamp set once on insert.
        updated_at:      UTC timestamp refreshed on every update.
    """

    stage_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    display_name: str
    description: str = ""
    order: int  # execution order; stages run ascending
    enabled: bool = True
    crew_type: str = (
        "crewai_sequential"  # pure_python | crewai_sequential | crewai_hierarchical
    )
    timeout_seconds: int = 300
    is_builtin: bool = True  # True for 4 default stages, False for user-created
    input_schema: Optional[dict] = None  # type: ignore[type-arg]
    output_schema: Optional[dict] = None  # type: ignore[type-arg]
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        """Beanie collection settings."""

        name = "stage_configs"
        indexes = [
            [("order", 1)],
            [("enabled", 1), ("order", 1)],
        ]


# ─────────────────────────────────────────────────────────────────────────────
# V3 Pipeline DAG – Enums & Embedded Models
# ─────────────────────────────────────────────────────────────────────────────


class NodeType(str, Enum):
    """Types of nodes in a pipeline DAG."""

    INPUT = "input"
    OUTPUT = "output"
    AGENT = "agent"
    PURE_PYTHON = "pure_python"


class PipelineNodeConfig(BaseModel):
    """A single node in the pipeline DAG (embedded in PipelineTemplateDocument)."""

    node_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_-]{2,49}$",
        description="Unique within this pipeline template",
    )
    node_type: NodeType = NodeType.AGENT
    agent_id: Optional[str] = Field(
        None,
        description="Reference to agent_configs.agent_id. Required for AGENT/PURE_PYTHON types.",
    )
    label: str = Field(
        ..., min_length=1, max_length=200, description="Display name on canvas"
    )
    description: str = ""

    # Visual position on canvas
    position_x: float = 0.0
    position_y: float = 0.0

    # Execution config
    timeout_seconds: int = Field(default=300, ge=10, le=7200)
    retry_count: int = Field(default=0, ge=0, le=5)
    enabled: bool = True

    # Custom data (agent overrides, etc.)
    config_overrides: dict = Field(
        default_factory=dict,
        description="Override agent config fields: llm_profile_id, max_iter, etc.",
    )


class PipelineEdgeConfig(BaseModel):
    """A directed edge connecting two nodes (embedded in PipelineTemplateDocument)."""

    edge_id: str = Field(..., description="Unique within this pipeline")
    source_node_id: str = Field(..., description="Output from this node")
    target_node_id: str = Field(..., description="Input to this node")
    source_handle: Optional[str] = Field(
        None,
        description="Named output port. Default: 'default'",
    )
    target_handle: Optional[str] = Field(
        None,
        description="Named input port. Default: 'default'",
    )
    label: Optional[str] = Field(None, description="Optional label on the edge")
    animated: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# PipelineTemplateDocument  (V3 NEW)
# ─────────────────────────────────────────────────────────────────────────────


class PipelineTemplateDocument(Document):
    """
    A reusable pipeline definition containing a DAG of agent nodes and edges.
    Each template can be run multiple times. V3 NEW.
    """

    template_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_-]{2,49}$",
        description="Unique identifier, URL-safe",
    )
    name: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    version: int = Field(default=1, description="Auto-incremented on each save")

    # DAG Definition
    nodes: list[PipelineNodeConfig] = Field(default_factory=list)
    edges: list[PipelineEdgeConfig] = Field(default_factory=list)

    # Metadata
    is_builtin: bool = False
    is_archived: bool = False
    tags: list[str] = Field(default_factory=list)
    thumbnail: Optional[str] = None  # Base64 or URL

    # Timestamps
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "pipeline_templates"
        indexes = [
            IndexModel([("template_id", 1)], unique=True),
            IndexModel([("is_archived", 1)]),
            IndexModel([("tags", 1)]),
            IndexModel([("created_at", -1)]),
        ]


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRunDocument  (V3 – backward-compatible with V2)
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunDocument(Document):
    """
    A single execution of a pipeline.
    V3: References a template_id, tracks node-level statuses.
    Backward-compatible with V2 runs (template_id optional).
    """

    run_id: Indexed(str, unique=True)  # type: ignore[valid-type]
    template_id: Optional[str] = Field(
        None,
        description="Which pipeline template to run (None = V2 legacy run)",
    )
    template_snapshot: Optional[dict] = Field(  # type: ignore[type-arg]
        None,
        description="Snapshot of template nodes+edges at run time (for reproducibility)",
    )

    # Run config
    document_name: str = ""
    document_path: Optional[str] = None  # V2 compat
    file_path: Optional[str] = None  # V3 alias
    llm_profile_id: Optional[str] = None
    run_params: dict = Field(default_factory=dict)  # type: ignore[type-arg]

    # Status
    status: Indexed(str) = "pending"  # type: ignore[valid-type]
    current_node: Optional[str] = None  # V3 (replaces current_stage)
    current_stage: Optional[str] = None  # V2 compat alias
    completed_nodes: list[str] = Field(default_factory=list)  # V3
    completed_stages: list[str] = Field(default_factory=list)  # V2 compat
    failed_nodes: list[str] = Field(default_factory=list)
    node_statuses: dict[str, str] = Field(
        default_factory=dict,
        description="{ node_id: 'pending'|'running'|'completed'|'failed'|'skipped' }",
    )
    agent_statuses: dict[str, str] = Field(default_factory=dict)  # V2 compat
    stage_results_summary: dict[str, dict] = Field(default_factory=dict)  # type: ignore[type-arg] # V2 compat

    # V3 fields
    execution_layers: list[list[str]] = Field(
        default_factory=list,
        description="Computed DAG layers: [[nodeA, nodeB], [nodeC], ...]",
    )
    duration_seconds: Optional[float] = None

    # Error
    error_message: Optional[str] = None
    error: Optional[str] = None  # V2 compat
    pause_reason: Optional[str] = None  # V2 compat

    # Timing
    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None  # V3 (replaces finished_at)
    finished_at: Optional[datetime] = None  # V2 compat
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None

    class Settings:
        name = "pipeline_runs"
        indexes = [
            IndexModel([("run_id", 1)], unique=True),
            IndexModel([("template_id", 1)]),
            IndexModel([("status", 1)]),
            IndexModel([("created_at", -1)]),
        ]


# ─────────────────────────────────────────────────────────────────────────────
# PipelineResultDocument  (V3 – backward-compatible with V2)
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResultDocument(Document):
    """
    Output from a single node/agent execution within a pipeline run.
    V3: Uses node_id (replaces stage). V2 stage field kept for compatibility.
    """

    run_id: Indexed(str)  # type: ignore[valid-type]
    node_id: Optional[str] = Field(
        None,
        description="Which DAG node produced this result (V3)",
    )
    agent_id: Optional[str] = Field(
        None,
        description="Which agent config was used (if AGENT type)",
    )
    stage: Optional[str] = None  # V2 compat (deprecated, use node_id in V3)
    result_type: str = "node_output"  # node_output | error | metadata
    output: Any = None  # stored as native BSON
    input_data: dict = Field(  # type: ignore[type-arg]
        default_factory=dict,
        description="What input this node received (for debugging/replay)",
    )

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # Status
    status: str = "completed"  # completed | failed | skipped
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "pipeline_results"
        indexes = [
            IndexModel([("run_id", 1), ("node_id", 1)]),
            IndexModel([("run_id", 1), ("stage", 1)]),
            IndexModel([("run_id", 1), ("agent_id", 1)]),
            IndexModel([("run_id", 1)]),
        ]
