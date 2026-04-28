"""
pipeline/__init__.py – Combines all pipeline sub-routers into one.

Public surface: ``router`` (APIRouter with prefix="/pipeline")

Sub-modules:
    runs     – CRUD endpoints (POST /run, POST/GET /runs, DELETE /runs/{id})
    control  – Control endpoints (pause / resume / cancel)
    results  – Result & export endpoints
"""

from __future__ import annotations

from fastapi import APIRouter

from .control import router as _control_router
from .results import router as _results_router
from .runs import router as _runs_router

router = APIRouter(prefix="/pipeline", tags=["Pipeline"])

router.include_router(_runs_router)
router.include_router(_control_router)
router.include_router(_results_router)

__all__ = ["router"]
