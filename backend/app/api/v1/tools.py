"""
api/v1/tools.py – REST endpoints for Tool Registry management.

Provides introspection into the available tools and supports assigning
tool slugs to agent configs.

Endpoints:
    GET    /admin/tools                         – list all registered tools
    GET    /admin/tools/{slug}                  – get one tool's metadata
    GET    /admin/tools/agent/{agent_id}        – get tools assigned to an agent
    PUT    /admin/tools/agent/{agent_id}        – update tool list for an agent
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Body, HTTPException, status
from pydantic import BaseModel, Field

from app.db import crud
from app.db.models import AgentConfigDocument
from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/tools", tags=["Admin – Tools"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class ToolInfo(BaseModel):
    """Metadata for a single registered tool."""

    slug: str = Field(description="Unique identifier used in agent tool_names list")
    class_name: str = Field(alias="class", description="Python class name")
    description: str = Field(description="Human-readable description from the tool")

    model_config = {"populate_by_name": True}


class ToolListResponse(BaseModel):
    """Paginated tool list."""

    total: int
    items: list[ToolInfo]


class AgentToolsResponse(BaseModel):
    """Current tool assignment for an agent."""

    agent_id: str
    tool_names: list[str]


class AgentToolsUpdate(BaseModel):
    """Request body for updating an agent's tool list."""

    tool_names: list[str] = Field(
        description=(
            "Full replacement list of tool slugs. "
            "Each slug must be a key registered in ToolRegistry. "
            "Pass an empty list to remove all tools."
        )
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/tools
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/",
    summary="List all registered tools",
    description=(
        "Returns every tool registered in the ``ToolRegistry``. "
        "Slugs from this list can be used in the ``tool_names`` field of agent configs."
    ),
    response_model=ToolListResponse,
)
async def list_tools() -> ToolListResponse:
    """Return metadata for all registered tools."""
    raw = ToolRegistry.describe()
    items = [
        ToolInfo(
            slug=t["slug"],
            **{"class": t["class"]},
            description=t["description"],
        )
        for t in raw
    ]
    return ToolListResponse(total=len(items), items=items)


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/tools/{slug}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{slug}",
    summary="Get tool metadata by slug",
    response_model=ToolInfo,
)
async def get_tool(slug: str) -> ToolInfo:
    """Return metadata for a single tool by its registry slug."""
    available = ToolRegistry.available()
    if slug not in available:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{slug}' is not registered. Available: {available}",
        )
    # Describe returns all; filter to the requested slug
    raw = next((t for t in ToolRegistry.describe() if t["slug"] == slug), None)
    if raw is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Tool '{slug}' not found")
    return ToolInfo(slug=raw["slug"], **{"class": raw["class"]}, description=raw["description"])


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/tools/agent/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/agent/{agent_id}",
    summary="Get tools assigned to an agent",
    response_model=AgentToolsResponse,
)
async def get_agent_tools(agent_id: str) -> AgentToolsResponse:
    """Return the list of tool slugs currently assigned to an agent config."""
    doc: AgentConfigDocument | None = await crud.get_agent_config(agent_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return AgentToolsResponse(agent_id=agent_id, tool_names=doc.tool_names or [])


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/tools/agent/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/agent/{agent_id}",
    summary="Update tool list for an agent",
    response_model=AgentToolsResponse,
)
async def update_agent_tools(
    agent_id: str,
    payload: Annotated[AgentToolsUpdate, Body()],
) -> AgentToolsResponse:
    """Replace the tool_names list for an agent config.

    Unknown tool slugs are rejected to prevent silent misconfiguration.
    """
    doc: AgentConfigDocument | None = await crud.get_agent_config(agent_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )

    # Validate that all requested slugs are registered
    available = set(ToolRegistry.available())
    unknown = [name for name in payload.tool_names if name not in available]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Unknown tool slug(s) — not registered in ToolRegistry",
                "unknown": unknown,
                "available": sorted(available),
            },
        )

    # Persist
    doc.tool_names = payload.tool_names
    await doc.save()

    logger.info(
        "[ToolsAPI] Updated tool_names for agent %r: %s", agent_id, payload.tool_names
    )
    return AgentToolsResponse(agent_id=agent_id, tool_names=doc.tool_names)
