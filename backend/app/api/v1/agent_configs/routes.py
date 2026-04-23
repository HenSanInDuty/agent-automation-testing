from __future__ import annotations

"""
agent_configs/routes.py – Route handlers for CrewAI agent configuration.

Endpoints:
    GET    /admin/agent-configs                           – list / grouped list
    GET    /admin/agent-configs/by-pipeline               – grouped by pipeline → stage
    GET    /admin/agent-configs/by-pipeline/{template_id} – single pipeline
    GET    /admin/agent-configs/{agent_id}                – get one
    POST   /admin/agent-configs                           – create custom agent
    PUT    /admin/agent-configs/{agent_id}                – partial update
    DELETE /admin/agent-configs/{agent_id}                – delete custom agent
    POST   /admin/agent-configs/{agent_id}/reset          – reset to factory defaults
    POST   /admin/agent-configs/reset-all                 – reset every agent
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.db import crud
from app.db.seed import DEFAULT_AGENT_CONFIGS
from app.schemas.agent_config import (
    AgentConfigByPipelineResponse,
    AgentConfigCreate,
    AgentConfigGroupedResponse,
    AgentConfigResetResponse,
    AgentConfigResponse,
    AgentConfigSummary,
    AgentConfigUpdate,
    PipelineAgentGroup,
)

from ._helpers import (
    _DEFAULTS_MAP,
    _doc_to_response,
    _doc_to_summary,
    _enrich_response_with_profile,
    _get_or_404,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agent-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List all agent configs",
    description=(
        "Returns all agent configurations. "
        "Pass ``grouped=true`` to receive results grouped by pipeline stage. "
        "Pass ``stage=<name>`` to filter by a specific stage. "
        "Pass ``enabled_only=true`` to include only enabled agents."
    ),
)
async def list_agent_configs(
    grouped: bool = Query(
        default=False,
        description="Group results by pipeline stage",
    ),
    stage: Optional[str] = Query(
        default=None,
        description="Filter by stage: ingestion | testcase | execution | reporting",
    ),
    enabled_only: bool = Query(
        default=False,
        description="Return only agents that are currently enabled",
    ),
) -> AgentConfigGroupedResponse | list[AgentConfigSummary]:
    """Return all agent configs, optionally filtered and/or grouped by stage."""
    docs = await crud.get_all_agent_configs(stage=stage, enabled_only=enabled_only)
    summaries = [_doc_to_summary(d) for d in docs]

    if grouped:
        return await AgentConfigGroupedResponse.from_list(summaries)
    return summaries


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agent-configs/by-pipeline
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/by-pipeline",
    response_model=AgentConfigByPipelineResponse,
    summary="Get agents grouped by pipeline template → stage",
    description=(
        "Returns all agents organised by pipeline template, then by stage "
        "within each template."
    ),
)
async def get_agents_by_pipeline(response: Response) -> AgentConfigByPipelineResponse:
    """Return agents grouped by pipeline template → stage."""
    response.headers["Cache-Control"] = "no-store"
    return await crud.get_agents_by_pipeline()


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agent-configs/by-pipeline/{template_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/by-pipeline/{template_id}",
    response_model=PipelineAgentGroup,
    summary="Get agents for a specific pipeline template grouped by stage",
)
async def get_agents_for_pipeline_template(
    template_id: str, response: Response
) -> PipelineAgentGroup:
    """Return agents grouped by stage for a single pipeline template."""
    response.headers["Cache-Control"] = "no-store"
    group = await crud.get_agents_for_pipeline_template(template_id)
    if group is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pipeline template '{template_id}' not found.",
        )
    return group


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/agent-configs/reset-all
# NOTE: Must be declared BEFORE /{agent_id} to avoid path-param capture.
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/reset-all",
    summary="Reset ALL agent configs to factory defaults",
    description=(
        "Restores every agent's role, goal, backstory, and behaviour flags to "
        "their original shipped values. Clears all per-agent LLM profile "
        "overrides. **This action cannot be undone.**"
    ),
)
async def reset_all_agent_configs() -> dict[str, Any]:
    """Reset every agent config to its seeded factory defaults."""
    docs = await crud.reset_all_agent_configs(DEFAULT_AGENT_CONFIGS)
    logger.info(
        "[AgentConfig] Reset ALL %d agent configs to factory defaults", len(docs)
    )
    return {
        "message": (
            f"All {len(docs)} agent configs have been reset to factory defaults."
        ),
        "reset_count": len(docs),
        "agent_ids": [d.agent_id for d in docs],
    }


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agent-configs/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{agent_id}",
    response_model=AgentConfigResponse,
    summary="Get a single agent config",
    description=(
        "Returns the full configuration for a single agent including its "
        "role, goal, backstory, and the associated LLM profile (if any)."
    ),
)
async def get_agent_config(agent_id: str) -> AgentConfigResponse:
    """Retrieve one agent config by its unique slug."""
    doc = await _get_or_404(agent_id)
    return await _enrich_response_with_profile(doc)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/agent-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=AgentConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new custom agent config",
    description=(
        "Creates a new custom agent configuration (``is_custom=true``). "
        "The ``agent_id`` must be a unique snake_case slug."
    ),
)
async def create_agent_config(
    payload: AgentConfigCreate,
) -> AgentConfigResponse:
    """Create a new custom (user-defined) agent config."""
    existing = await crud.get_agent_config(payload.agent_id)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"An agent config with agent_id={payload.agent_id!r} already "
                f"exists (id={str(existing.id)})."
            ),
        )

    if payload.llm_profile_id is not None:
        profile = await crud.get_llm_profile(payload.llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"LLM profile with id={payload.llm_profile_id!r} not found. "
                    "Create the profile first before assigning it to an agent."
                ),
            )

    doc = await crud.create_agent_config(payload.model_dump())
    logger.info("[AgentConfig] Created agent_id=%r id=%s", doc.agent_id, str(doc.id))
    return await _enrich_response_with_profile(doc)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/agent-configs/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{agent_id}",
    response_model=AgentConfigResponse,
    summary="Update an agent config (partial update supported)",
    description=(
        "Updates the configuration for a single agent. Only fields present "
        "in the request body are modified."
    ),
)
async def update_agent_config(
    agent_id: str,
    payload: AgentConfigUpdate,
) -> AgentConfigResponse:
    """Partially update an agent config by its slug."""
    if payload.llm_profile_id is not None:
        profile = await crud.get_llm_profile(payload.llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"LLM profile with id={payload.llm_profile_id!r} not found. "
                    "Create the profile first before assigning it to an agent."
                ),
            )

    update_data = payload.model_dump(exclude_unset=True)
    doc = await crud.update_agent_config(agent_id, update_data)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )

    logger.info("[AgentConfig] Updated agent_id=%r", agent_id)
    return await _enrich_response_with_profile(doc)


# ─────────────────────────────────────────────────────────────────────────────
# DELETE /admin/agent-configs/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a custom agent config",
    description=(
        "Deletes a custom (user-created) agent config.  "
        "Built-in seeded agents cannot be deleted via this endpoint."
    ),
)
async def delete_agent_config(agent_id: str) -> None:
    """Delete a custom agent config."""
    try:
        deleted = await crud.delete_agent_config(agent_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )
    logger.info("[AgentConfig] Deleted agent_id=%r", agent_id)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/agent-configs/{agent_id}/reset
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{agent_id}/reset",
    response_model=AgentConfigResetResponse,
    summary="Reset a single agent config to factory defaults",
    description=(
        "Restores the agent's role, goal, backstory, and behaviour flags to "
        "their original shipped values."
    ),
)
async def reset_agent_config(agent_id: str) -> AgentConfigResetResponse:
    """Reset one agent config to its seeded factory defaults."""
    defaults = _DEFAULTS_MAP.get(agent_id)
    if defaults is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No factory defaults found for agent_id={agent_id!r}. "
                "This agent may have been added outside the standard seed."
            ),
        )

    doc = await crud.reset_agent_config(agent_id, defaults)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )

    logger.info("[AgentConfig] Reset agent_id=%r to factory defaults", agent_id)
    return AgentConfigResetResponse(
        agent_id=agent_id,
        message="Agent config has been reset to default values.",
        config=_doc_to_response(doc),
    )
