"""
schemas/stage_config.py – Pydantic schemas for pipeline stage configurations.

V4: Stages are now purely organizational (agent grouping / categorization).
    They are NOT used for pipeline execution order — that's handled by DAG templates.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class StageConfigCreate(BaseModel):
    """Create a new custom stage."""

    stage_id: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z][a-z0-9_-]{1,49}$",
        description="URL-safe slug identifier",
        examples=["security-testing", "performance-check"],
    )
    display_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    order: int = Field(default=500, ge=0, le=9999)
    color: Optional[str] = Field(
        None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
        description="Hex color code",
        examples=["#3B82F6"],
    )
    icon: Optional[str] = Field(None, max_length=50)
    enabled: bool = True


class StageConfigUpdate(BaseModel):
    """Partial update for a stage."""

    display_name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    order: Optional[int] = Field(None, ge=0, le=9999)
    color: Optional[str] = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    icon: Optional[str] = Field(None, max_length=50)
    enabled: Optional[bool] = None


class StageConfigResponse(BaseModel):
    """Stage config as returned by the API."""

    id: str  # MongoDB ObjectId as string
    stage_id: str
    display_name: str
    description: Optional[str] = None
    order: int
    color: Optional[str] = None
    icon: Optional[str] = None
    enabled: bool
    is_builtin: bool
    agent_count: int = 0  # Computed: number of agents in this stage
    created_at: str
    updated_at: str


class StageReorderRequest(BaseModel):
    """Reorder stages by providing ordered list of stage_ids."""

    stage_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of stage_ids. Position in list = display order.",
    )
