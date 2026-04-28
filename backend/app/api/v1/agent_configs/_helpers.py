"""
agent_configs/_helpers.py – Shared helpers and converters for agent config endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException, status

from app.db import crud
from app.db.models import AgentConfigDocument
from app.db.seed import DEFAULT_AGENT_CONFIGS
from app.schemas.agent_config import (
    AgentConfigResponse,
    AgentConfigSummary,
)
from app.schemas.llm_profile import LLMProfileResponse

logger = logging.getLogger(__name__)

# Pre-build a lookup map of defaults keyed by agent_id for O(1) reset access.
_DEFAULTS_MAP: dict[str, dict[str, Any]] = {
    d["agent_id"]: d for d in DEFAULT_AGENT_CONFIGS
}


async def _get_or_404(agent_id: str) -> AgentConfigDocument:
    """Fetch an agent config by slug, or raise HTTP 404."""
    doc = await crud.get_agent_config(agent_id)
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent config with agent_id={agent_id!r} not found.",
        )
    return doc


def _doc_to_summary(doc: AgentConfigDocument) -> AgentConfigSummary:
    """Convert a Beanie document to the lightweight summary schema."""
    return AgentConfigSummary(
        id=str(doc.id),
        agent_id=doc.agent_id,
        display_name=doc.display_name,
        stage=doc.stage,
        llm_profile_id=doc.llm_profile_id,
        llm_profile_name=None,
        enabled=doc.enabled,
        verbose=doc.verbose,
        max_iter=doc.max_iter,
        is_custom=doc.is_custom,
        updated_at=doc.updated_at,
    )


def _doc_to_response(doc: AgentConfigDocument) -> AgentConfigResponse:
    """Convert a Beanie document to the full response schema."""
    return AgentConfigResponse(
        id=str(doc.id),
        agent_id=doc.agent_id,
        display_name=doc.display_name,
        stage=doc.stage,
        role=doc.role,
        goal=doc.goal,
        backstory=doc.backstory,
        llm_profile_id=doc.llm_profile_id,
        llm_profile=None,
        enabled=doc.enabled,
        verbose=doc.verbose,
        max_iter=doc.max_iter,
        is_custom=doc.is_custom,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


async def _enrich_response_with_profile(
    doc: AgentConfigDocument,
) -> AgentConfigResponse:
    """Build an AgentConfigResponse with the nested LLM profile populated."""
    llm_profile_resp: Optional[LLMProfileResponse] = None
    if doc.llm_profile_id is not None:
        profile_doc = await crud.get_llm_profile(doc.llm_profile_id)
        if profile_doc is not None:
            llm_profile_resp = LLMProfileResponse.model_validate(profile_doc)

    resp = _doc_to_response(doc)
    resp.llm_profile = llm_profile_resp
    return resp
