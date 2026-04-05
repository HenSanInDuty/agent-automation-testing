"""
schemas/stage_config.py – Pydantic schemas for pipeline stage configurations.

New in V2: stages are stored in MongoDB and can be dynamically configured.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StageConfigCreate(BaseModel):
    """Schema for creating a new custom stage."""

    stage_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_]{2,49}$",
        description="Unique snake_case identifier (3-50 chars)",
    )
    display_name: str = Field(..., min_length=2, max_length=150)
    description: str = ""
    order: int = Field(
        ...,
        ge=1,
        description=(
            "Execution order. Stages run in ascending order. "
            "Use gaps (100, 200) for easy insertion."
        ),
    )
    enabled: bool = True
    crew_type: str = Field(
        default="crewai_sequential",
        description="pure_python | crewai_sequential | crewai_hierarchical",
    )
    timeout_seconds: int = Field(default=300, ge=30, le=3600)


class StageConfigUpdate(BaseModel):
    """Schema for partial update of a stage config."""

    display_name: Optional[str] = Field(default=None, min_length=2, max_length=150)
    description: Optional[str] = None
    order: Optional[int] = Field(default=None, ge=1)
    enabled: Optional[bool] = None
    crew_type: Optional[str] = None
    timeout_seconds: Optional[int] = Field(default=None, ge=30, le=3600)


class StageReorderRequest(BaseModel):
    """Schema for batch reordering stages."""

    stages: list[dict] = Field(
        ...,
        description='List of {"stage_id": "...", "order": N} objects',
    )


class StageConfigResponse(BaseModel):
    """Full stage config returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str  # MongoDB ObjectId string
    stage_id: str
    display_name: str
    description: str
    order: int
    enabled: bool
    crew_type: str
    timeout_seconds: int
    is_builtin: bool
    created_at: datetime
    updated_at: datetime
