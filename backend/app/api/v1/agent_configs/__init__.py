from __future__ import annotations

"""
agent_configs/__init__.py – Combines all agent config sub-routers.

Public surface: ``router`` (APIRouter with prefix="/admin/agent-configs")
"""

from fastapi import APIRouter

from .routes import router as _routes_router

router = APIRouter(prefix="/admin/agent-configs", tags=["Admin – Agent Configs"])

router.include_router(_routes_router)

__all__ = ["router"]
