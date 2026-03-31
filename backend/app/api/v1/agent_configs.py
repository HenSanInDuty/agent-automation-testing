from __future__ import annotations

import logging
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_db
from app.db import crud
from app.db.seed import DEFAULT_AGENT_CONFIGS
from app.schemas.agent_config import (
    AgentConfigGrouped,
    AgentConfigResetResponse,
    AgentConfigResponse,
    AgentConfigSummary,
    AgentConfigUpdate,
)
from app.schemas.llm_profile import LLMProfileResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/agent-configs", tags=["Admin – Agent Configs"])

# ─────────────────────────────────────────────────────────────────────────────
# Dependency alias
# ─────────────────────────────────────────────────────────────────────────────

DB = Annotated[Session, Depends(get_db)]

# Pre-build a lookup map of defaults keyed by agent_id for O(1) reset access
_DEFAULTS_MAP: dict[str, dict[str, Any]] = {
    d["agent_id"]: d for d in DEFAULT_AGENT_CONFIGS
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _get_or_404(db: Session, agent_id: str):
    """Return the AgentConfig ORM object or raise 404."""
    config = crud.get_agent_config(db, agent_id)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )
    return config


def _orm_to_summary(config) -> AgentConfigSummary:
    """Convert an AgentConfig ORM instance to AgentConfigSummary."""
    llm_name: Optional[str] = None
    if config.llm_profile is not None:
        llm_name = config.llm_profile.name

    return AgentConfigSummary(
        id=config.id,
        agent_id=config.agent_id,
        display_name=config.display_name,
        stage=config.stage,
        llm_profile_id=config.llm_profile_id,
        llm_profile_name=llm_name,
        enabled=config.enabled,
        verbose=config.verbose,
        max_iter=config.max_iter,
        updated_at=config.updated_at,
    )


def _orm_to_response(config) -> AgentConfigResponse:
    """Convert an AgentConfig ORM instance to full AgentConfigResponse."""
    llm_profile_resp: Optional[LLMProfileResponse] = None
    if config.llm_profile is not None:
        llm_profile_resp = LLMProfileResponse.model_validate(config.llm_profile)

    return AgentConfigResponse(
        id=config.id,
        agent_id=config.agent_id,
        display_name=config.display_name,
        stage=config.stage,
        role=config.role,
        goal=config.goal,
        backstory=config.backstory,
        llm_profile_id=config.llm_profile_id,
        llm_profile=llm_profile_resp,
        enabled=config.enabled,
        verbose=config.verbose,
        max_iter=config.max_iter,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agent-configs
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "",
    summary="List all agent configs",
    description=(
        "Returns all agent configurations. "
        "Pass `grouped=true` to receive results grouped by pipeline stage "
        "(ingestion / testcase / execution / reporting). "
        "Pass `stage=<name>` to filter by a specific stage. "
        "Pass `enabled_only=true` to include only enabled agents."
    ),
)
def list_agent_configs(
    db: DB,
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
) -> AgentConfigGrouped | list[AgentConfigSummary]:
    configs = crud.get_all_agent_configs(db, stage=stage, enabled_only=enabled_only)
    summaries = [_orm_to_summary(c) for c in configs]

    if grouped:
        return AgentConfigGrouped.from_list(summaries)
    return summaries


# ─────────────────────────────────────────────────────────────────────────────
# GET /admin/agent-configs/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/{agent_id}",
    response_model=AgentConfigResponse,
    summary="Get a single agent config",
    description=(
        "Returns the full configuration for a single agent, including its "
        "role, goal, backstory, and associated LLM profile (if any)."
    ),
)
def get_agent_config(db: DB, agent_id: str) -> AgentConfigResponse:
    config = _get_or_404(db, agent_id)
    return _orm_to_response(config)


# ─────────────────────────────────────────────────────────────────────────────
# PUT /admin/agent-configs/{agent_id}
# ─────────────────────────────────────────────────────────────────────────────


@router.put(
    "/{agent_id}",
    response_model=AgentConfigResponse,
    summary="Update an agent config (partial update supported)",
    description=(
        "Updates the configuration for a single agent. Only fields present "
        "in the request body are modified — omitted fields keep their current values. "
        "To assign a per-agent LLM profile override, set `llm_profile_id`. "
        "To fall back to the global default, set `llm_profile_id` to `null`."
    ),
)
def update_agent_config(
    db: DB,
    agent_id: str,
    payload: AgentConfigUpdate,
) -> AgentConfigResponse:
    # Validate llm_profile_id exists if provided
    if payload.llm_profile_id is not None:
        profile = crud.get_llm_profile(db, payload.llm_profile_id)
        if profile is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"LLM profile with id={payload.llm_profile_id} not found. "
                    "Create the profile first before assigning it to an agent."
                ),
            )

    config = crud.update_agent_config(db, agent_id, payload)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )

    logger.info("[AgentConfig] Updated agent_id=%r", agent_id)
    return _orm_to_response(config)


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/agent-configs/{agent_id}/reset
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/{agent_id}/reset",
    response_model=AgentConfigResetResponse,
    summary="Reset a single agent config to factory defaults",
    description=(
        "Restores the agent's role, goal, backstory, and behaviour flags to their "
        "original shipped values. Also clears any per-agent LLM profile override "
        "so the agent inherits the global default. "
        "Custom `display_name` changes are also reverted."
    ),
)
def reset_agent_config(db: DB, agent_id: str) -> AgentConfigResetResponse:
    defaults = _DEFAULTS_MAP.get(agent_id)
    if defaults is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No factory defaults found for agent_id={agent_id!r}. "
                "This agent may have been added outside the standard seed."
            ),
        )

    config = crud.reset_agent_config(db, agent_id, defaults)
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )

    logger.info("[AgentConfig] Reset agent_id=%r to factory defaults", agent_id)
    return AgentConfigResetResponse(
        agent_id=agent_id,
        message="Agent config has been reset to default values.",
        config=_orm_to_response(config),
    )


# ─────────────────────────────────────────────────────────────────────────────
# POST /admin/agent-configs/reset-all
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/reset-all",
    summary="Reset ALL agent configs to factory defaults",
    description=(
        "Restores every agent's role, goal, backstory, and behaviour flags to their "
        "original shipped values. Clears all per-agent LLM profile overrides. "
        "**This action cannot be undone.**"
    ),
)
def reset_all_agent_configs(db: DB) -> dict[str, Any]:
    configs = crud.reset_all_agent_configs(db, DEFAULT_AGENT_CONFIGS)
    logger.info(
        "[AgentConfig] Reset ALL %d agent configs to factory defaults", len(configs)
    )
    return {
        "message": f"All {len(configs)} agent configs have been reset to factory defaults.",
        "reset_count": len(configs),
        "agent_ids": [c.agent_id for c in configs],
    }
