"""
schemas/pipeline_template.py – Pydantic schemas for Pipeline Template operations.

All schemas in this module are used by the Pipeline Templates API
(``api/v1/pipeline_templates.py``).

Classes:
    PipelineNodeInput       – Input schema for a single node
    PipelineEdgeInput       – Input schema for a single edge
    PipelineTemplateCreate  – Create a new pipeline template
    PipelineTemplateUpdate  – Update an existing template (all fields optional)
    PipelineTemplateResponse – Full template response (includes nodes + edges)
    PipelineTemplateListItem – Lightweight summary for list endpoints
    DAGValidationResponse    – Result of DAG validation endpoint
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# ─────────────────────────────────────────────────────────────────────────────
# Node & Edge Input Schemas
# ─────────────────────────────────────────────────────────────────────────────


class PipelineNodeInput(BaseModel):
    """Input/output schema for a node within a pipeline template."""

    node_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_-]{2,49}$",
        description="Unique node identifier within this pipeline (URL-safe slug)",
    )
    node_type: str = Field(
        default="agent",
        description="Node type: input | output | agent | pure_python",
    )
    agent_id: Optional[str] = Field(
        None,
        description="References agent_configs.agent_id. Required for agent/pure_python nodes.",
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

    # Agent config overrides (e.g. llm_profile_id, max_iter)
    config_overrides: dict = Field(default_factory=dict)  # type: ignore[type-arg]


class PipelineEdgeInput(BaseModel):
    """Input/output schema for a directed edge between two nodes."""

    edge_id: str = Field(..., description="Unique edge identifier within this pipeline")
    source_node_id: str = Field(..., description="node_id of the source (output) node")
    target_node_id: str = Field(..., description="node_id of the target (input) node")
    source_handle: Optional[str] = Field(
        None,
        description="Named output port on the source node. Defaults to 'default'.",
    )
    target_handle: Optional[str] = Field(
        None,
        description="Named input port on the target node. Defaults to 'default'.",
    )
    label: Optional[str] = Field(None, description="Optional visual label for the edge")
    animated: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Create / Update Schemas
# ─────────────────────────────────────────────────────────────────────────────


class PipelineTemplateCreate(BaseModel):
    """Request body for creating a new pipeline template."""

    template_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_-]{2,49}$",
        description="Globally unique URL-safe identifier for this template",
    )
    name: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    nodes: list[PipelineNodeInput] = Field(
        default_factory=list,
        description="DAG nodes — can be empty when creating a blank template",
    )
    edges: list[PipelineEdgeInput] = Field(
        default_factory=list,
        description="DAG edges — can be empty when creating a blank template",
    )
    tags: list[str] = Field(default_factory=list)


class PipelineTemplateUpdate(BaseModel):
    """Request body for updating an existing pipeline template.

    All fields are optional — only provided fields are updated.
    If ``nodes`` or ``edges`` are provided, the entire DAG is replaced
    and re-validated.
    """

    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    nodes: Optional[list[PipelineNodeInput]] = None
    edges: Optional[list[PipelineEdgeInput]] = None
    tags: Optional[list[str]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class PipelineTemplateResponse(BaseModel):
    """Full pipeline template response (returned by create / get / update)."""

    id: str = Field(description="MongoDB ObjectId string")
    template_id: str
    name: str
    description: str
    version: int

    nodes: list[PipelineNodeInput]
    edges: list[PipelineEdgeInput]

    is_builtin: bool
    is_archived: bool
    tags: list[str]

    node_count: int
    edge_count: int

    created_at: datetime
    updated_at: datetime


class PipelineTemplateListItem(BaseModel):
    """Lightweight summary item for the pipeline template list endpoint."""

    id: str = Field(description="MongoDB ObjectId string")
    template_id: str
    name: str
    description: str
    version: int

    is_builtin: bool
    is_archived: bool
    tags: list[str]

    node_count: int
    edge_count: int

    # Last run metadata (may be None if never run)
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None

    created_at: datetime
    updated_at: datetime


class DAGValidationResponse(BaseModel):
    """Response from the ``POST /pipeline-templates/{id}/validate`` endpoint."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    execution_layers: list[list[str]] = Field(
        default_factory=list,
        description="Computed execution layers if valid. Each sub-list runs in parallel.",
    )
    total_layers: int = 0
    total_nodes: int = 0
    estimated_parallel_speedup: Optional[float] = Field(
        None,
        description=(
            "Ratio of total_nodes / total_layers. "
            "1.0 = fully sequential, >1.0 = parallel gain."
        ),
    )
