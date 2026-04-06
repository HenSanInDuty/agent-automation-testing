from __future__ import annotations

"""
api/v1/stage_configs.py – DEPRECATED in V3.

Stage-based pipeline configuration is replaced by the DAG Pipeline Template
system (api/v1/pipeline_templates.py). All endpoints return 410 Gone.

See: POST /api/v1/pipeline-templates for the V3 replacement.
"""

import logging

from fastapi import APIRouter, HTTPException, status

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/stage-configs", tags=["Admin – Stage Configs (Deprecated)"]
)

_GONE_DETAIL = (
    "The Stage Config API is deprecated in V3. "
    "Use the Pipeline Templates API (/api/v1/pipeline-templates) instead."
)


@router.get("", deprecated=True)
async def list_stage_configs():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)


@router.post("", deprecated=True)
async def create_stage_config():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)


@router.post("/reorder", deprecated=True)
async def reorder_stages():
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)


@router.get("/{stage_id}", deprecated=True)
async def get_stage_config(stage_id: str):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)


@router.put("/{stage_id}", deprecated=True)
async def update_stage_config(stage_id: str):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)


@router.delete("/{stage_id}", deprecated=True)
async def delete_stage_config(stage_id: str):
    raise HTTPException(status_code=status.HTTP_410_GONE, detail=_GONE_DETAIL)
