from __future__ import annotations

"""
pipeline_templates/__init__.py – Combines all pipeline-templates sub-routers.

Public surface: ``router`` (APIRouter with prefix="/pipeline-templates")

Sub-modules:
    crud        – CRUD endpoints (list, create, get, update, delete, archive)
    operations  – Special ops (import, export, validate, clone, node-stage, nodes)
"""

from fastapi import APIRouter

from .crud import router as _crud_router
from .operations import router as _operations_router

router = APIRouter(prefix="/pipeline-templates", tags=["Pipeline Templates"])

# operations router must come first so static paths like /import
# are registered before the /{template_id} catch-all in crud router.
router.include_router(_operations_router)
router.include_router(_crud_router)

__all__ = ["router"]
