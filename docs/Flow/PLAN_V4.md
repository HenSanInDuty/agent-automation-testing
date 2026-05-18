# Auto-AT – Implementation Plan V4

> **Focus**: Dynamic Stage Management + Frontend ↔ Backend Route Synchronization
>
> **Predecessor**: PLAN_V3 (DAG Pipeline Builder)
>
> **Estimated Total**: ~5 ngày

---

## Table of Contents

1. [V3 Recap – What Already Exists](#1-v3-recap--what-already-exists)
2. [V4 Requirements – New Features](#2-v4-requirements--new-features)
3. [Feature 1 – Dynamic Stage Management](#3-feature-1--dynamic-stage-management)
4. [Feature 2 – Frontend ↔ Backend Route Synchronization](#4-feature-2--frontend--backend-route-synchronization)
5. [Detailed Bug Fixes & Sync Matrix](#5-detailed-bug-fixes--sync-matrix)
6. [Updated Data Models](#6-updated-data-models)
7. [Updated API Endpoints](#7-updated-api-endpoints)
8. [Updated Frontend Types & Components](#8-updated-frontend-types--components)
9. [Updated Folder Structure](#9-updated-folder-structure)
10. [Implementation Phases](#10-implementation-phases)

---

## 1. V3 Recap – What Already Exists

### Hệ thống hiện tại (đã hoàn thành trong V3)

- ✅ DAG Pipeline Builder (React Flow) — drag-and-drop visual wiring
- ✅ Pipeline Template CRUD API (`/api/v1/pipeline-templates`)
- ✅ DAG Pipeline Runner — layer-based parallel execution
- ✅ Multi-pipeline management (list / create / edit / clone / archive)
- ✅ Agent Config CRUD (`/api/v1/admin/agent-configs`)
- ✅ LLM Profile CRUD (`/api/v1/admin/llm-profiles`)
- ✅ Pipeline Run controls (pause / resume / cancel)
- ✅ Real-time WebSocket events (22 event types)
- ✅ Report export (HTML / DOCX)
- ✅ MongoDB + Beanie ORM
- ✅ 19 seeded agents across 4 stages

### Các giới hạn của V3

| # | Giới hạn | Mô tả |
|---|----------|-------|
| 1 | **4 stages cứng** | `AgentStage` type cố định = `"ingestion" \| "testcase" \| "execution" \| "reporting"`. Không thể tạo stage mới. |
| 2 | **Stage Config API bị deprecated** | Toàn bộ `/api/v1/admin/stage-configs` trả về **410 Gone**. Frontend `AddAgentDialog` dùng `useStageConfigs()` gọi API này → luôn fail. |
| 3 | **Agent grouping cứng** | Backend `AgentConfigGrouped` có 4 field cố định + `custom` bucket. Frontend chỉ render 4 nhóm → agent custom stage bị ẩn. |
| 4 | **Route mismatches FE ↔ BE** | 3 critical bugs (clone, import, export), 4 high-severity type mismatches, 5 medium issues. Chi tiết xem [Section 4](#4-feature-2--frontend--backend-route-synchronization). |
| 5 | **Dead code** | `stageConfigsApi` (FE), `useStageConfigs` hook, `/admin/stages` page — tất cả gọi API 410 Gone. |
| 6 | **Type mismatches** | `LLMProfileResponse.id` typed `number` (thực tế `string`), `ChatRequest.llm_profile_id` typed `number \| null` (thực tế `string`), response types sai nhiều endpoint. |

---

## 2. V4 Requirements – New Features

### Feature 1 – Dynamic Stage Management

- Cho phép tạo / sửa / xóa stage (không giới hạn 4 stages cứng)
- Stage Admin UI tích hợp vào trang `/admin/agents` (thay vì page riêng `/admin/stages`)
- Agent grouping theo dynamic stages — stage mới tự động hiển thị
- Mỗi stage có: `stage_id`, `display_name`, `description`, `order`, `color`, `icon`, `enabled`
- Giữ 4 built-in stages (ingestion / testcase / execution / reporting) — không xóa được, chỉ edit display
- Custom stages hỗ trợ `DynamicCrewAICrew` cho V2 runner

### Feature 2 – Frontend ↔ Backend Route Synchronization

- Fix tất cả 3 critical API bugs (clone, import/export template)
- Fix 4 high-severity type mismatches
- Clean up dead code (deprecated stage config calls)
- Đồng bộ response types giữa FE và BE
- Thêm missing endpoint (`GET /pipeline/runs/{run_id}/results/{node_id}`)
- Thêm `template_id` filter cho `GET /pipeline/runs`

### Tương thích ngược

- V3 DAG Pipeline hoạt động bình thường — không breaking changes
- 4 built-in stages vẫn được seed — migration tự động
- V2 Pipeline Runner vẫn hoạt động (đã deprecated nhưng functional)

---

## 3. Feature 1 – Dynamic Stage Management

### Mục tiêu

Biến "stage" từ khái niệm cứng (4 giá trị) thành entity quản lý được — user có thể tạo stage mới, assign agent vào stage, và thấy agent grouping cập nhật tự động trên `/admin/agents`.

### 3.1 Revive Stage Config API (Backend)

Stage Config API hiện tại trả 410 Gone. V4 sẽ **restore + mở rộng** nó.

> **Lý do**: Trong V3, stages bị deprecate vì DAG templates thay thế sequential pipeline. Nhưng `stage` vẫn là organizational concept quan trọng để group agents trong Admin UI. V4 giữ DAG cho execution, dùng stages cho categorization.

#### Updated StageConfigDocument

```python
# app/db/models.py — Updated

class StageConfigDocument(Document):
    """
    Organizational stage — used for agent grouping and categorization.
    
    NOT used for pipeline execution order (that's handled by DAG templates).
    Used by: Admin Agent UI grouping, Agent Catalog sidebar in Builder.
    """
    stage_id: str                           # URL-safe slug, e.g. "testcase", "my-custom-stage"
    display_name: str                       # Human-readable, e.g. "Test Case Generation"
    description: Optional[str] = None       # Optional description
    order: int = 0                          # Sort order in UI
    color: Optional[str] = None             # Hex color for UI accent, e.g. "#3B82F6"
    icon: Optional[str] = None              # Lucide icon name, e.g. "flask-conical"
    enabled: bool = True                    # Whether to show in UI
    is_builtin: bool = False                # True for 4 default stages — cannot delete
    
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "stage_configs"
        indexes = [
            IndexModel([("stage_id", 1)], unique=True),
            IndexModel([("order", 1), ("enabled", 1)]),
        ]
```

#### Updated Stage Config Schemas

```python
# app/schemas/stage_config.py — Updated

from pydantic import BaseModel, Field
from typing import Optional
import re


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
    id: str                          # MongoDB ObjectId as string
    stage_id: str
    display_name: str
    description: Optional[str] = None
    order: int
    color: Optional[str] = None
    icon: Optional[str] = None
    enabled: bool
    is_builtin: bool
    agent_count: int = 0             # Computed: number of agents in this stage
    created_at: str
    updated_at: str


class StageReorderRequest(BaseModel):
    """Reorder stages by providing ordered list of stage_ids."""
    stage_ids: list[str] = Field(
        ...,
        min_length=1,
        description="Ordered list of stage_ids. Position in list = display order.",
    )
```

#### Stage Config API Endpoints (Restored)

```python
# app/api/v1/stage_configs.py — Rewritten (was 410 Gone)

from fastapi import APIRouter, HTTPException, Query, status
from app.db import crud
from app.schemas.stage_config import (
    StageConfigCreate,
    StageConfigUpdate,
    StageConfigResponse,
    StageReorderRequest,
)

router = APIRouter(
    prefix="/admin/stage-configs",
    tags=["Admin – Stage Configs"],
)

BUILTIN_STAGE_IDS = {"ingestion", "testcase", "execution", "reporting"}


@router.get("", response_model=list[StageConfigResponse])
async def list_stage_configs(
    enabled_only: bool = Query(default=False),
):
    """
    List all stage configs, sorted by `order`.

    If `enabled_only=true`, only returns enabled stages.
    """
    stages = await crud.get_all_stage_configs(enabled_only=enabled_only)
    
    # Compute agent_count for each stage
    result = []
    for stage in stages:
        count = await crud.count_agents_by_stage(stage.stage_id)
        resp = _to_response(stage, agent_count=count)
        result.append(resp)
    
    return result


@router.get("/{stage_id}", response_model=StageConfigResponse)
async def get_stage_config(stage_id: str):
    """Get a single stage config by stage_id."""
    stage = await crud.get_stage_config(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage '{stage_id}' not found")
    count = await crud.count_agents_by_stage(stage_id)
    return _to_response(stage, agent_count=count)


@router.post("", response_model=StageConfigResponse, status_code=201)
async def create_stage_config(body: StageConfigCreate):
    """
    Create a new custom stage.

    The `stage_id` must be unique and URL-safe.
    Built-in stage IDs cannot be reused.
    """
    if body.stage_id in BUILTIN_STAGE_IDS:
        raise HTTPException(
            status_code=409,
            detail=f"'{body.stage_id}' is a built-in stage and cannot be recreated.",
        )
    
    existing = await crud.get_stage_config(body.stage_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Stage '{body.stage_id}' already exists.",
        )
    
    stage = await crud.create_stage_config(body)
    return _to_response(stage, agent_count=0)


@router.put("/{stage_id}", response_model=StageConfigResponse)
async def update_stage_config(stage_id: str, body: StageConfigUpdate):
    """
    Update a stage config.

    Built-in stages can be updated (display_name, color, etc.)
    but cannot change `stage_id` or `is_builtin`.
    """
    stage = await crud.get_stage_config(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage '{stage_id}' not found")
    
    updated = await crud.update_stage_config(stage_id, body)
    count = await crud.count_agents_by_stage(stage_id)
    return _to_response(updated, agent_count=count)


@router.delete("/{stage_id}", status_code=204)
async def delete_stage_config(stage_id: str):
    """
    Delete a custom stage.

    Built-in stages cannot be deleted.
    Agents in this stage will have their stage set to "custom".
    """
    stage = await crud.get_stage_config(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage '{stage_id}' not found")
    
    if stage.is_builtin:
        raise HTTPException(
            status_code=403,
            detail=f"Cannot delete built-in stage '{stage_id}'.",
        )
    
    # Reassign orphaned agents to "custom" stage
    await crud.reassign_agents_stage(stage_id, "custom")
    await crud.delete_stage_config(stage_id)


@router.post("/reorder", response_model=list[StageConfigResponse])
async def reorder_stages(body: StageReorderRequest):
    """
    Reorder stages. Provide the full ordered list of stage_ids.
    
    Position in list determines the display order (0-based).
    """
    stages = await crud.reorder_stages(body.stage_ids)
    result = []
    for stage in stages:
        count = await crud.count_agents_by_stage(stage.stage_id)
        result.append(_to_response(stage, agent_count=count))
    return result


def _to_response(stage, agent_count: int = 0) -> StageConfigResponse:
    return StageConfigResponse(
        id=str(stage.id),
        stage_id=stage.stage_id,
        display_name=stage.display_name,
        description=stage.description,
        order=stage.order,
        color=stage.color,
        icon=stage.icon,
        enabled=stage.enabled,
        is_builtin=stage.is_builtin,
        agent_count=agent_count,
        created_at=stage.created_at.isoformat(),
        updated_at=stage.updated_at.isoformat(),
    )
```

#### New CRUD Functions

```python
# app/db/crud.py — New functions to add

async def count_agents_by_stage(stage: str) -> int:
    """Count agents belonging to a specific stage."""
    return await AgentConfigDocument.find(
        AgentConfigDocument.stage == stage,
        AgentConfigDocument.enabled == True,
    ).count()


async def reassign_agents_stage(from_stage: str, to_stage: str) -> int:
    """
    Move all agents from one stage to another.
    Returns the number of agents affected.
    """
    result = await AgentConfigDocument.find(
        AgentConfigDocument.stage == from_stage,
    ).update_many({"$set": {"stage": to_stage, "updated_at": _now()}})
    return result.modified_count


async def get_all_stage_configs(enabled_only: bool = False) -> list[StageConfigDocument]:
    """Get all stage configs, sorted by order."""
    query = {}
    if enabled_only:
        query["enabled"] = True
    return await StageConfigDocument.find(query).sort("+order").to_list()


async def get_stage_config(stage_id: str) -> Optional[StageConfigDocument]:
    """Get a single stage config by stage_id."""
    return await StageConfigDocument.find_one(
        StageConfigDocument.stage_id == stage_id
    )


async def create_stage_config(data: StageConfigCreate) -> StageConfigDocument:
    """Create a new stage config."""
    doc = StageConfigDocument(
        stage_id=data.stage_id,
        display_name=data.display_name,
        description=data.description,
        order=data.order,
        color=data.color,
        icon=data.icon,
        enabled=data.enabled,
        is_builtin=False,
    )
    await doc.insert()
    return doc


async def update_stage_config(
    stage_id: str, data: StageConfigUpdate
) -> StageConfigDocument:
    """Partial update a stage config."""
    stage = await get_stage_config(stage_id)
    update_data = data.model_dump(exclude_unset=True)
    update_data["updated_at"] = _now()
    await stage.update({"$set": update_data})
    return await get_stage_config(stage_id)


async def delete_stage_config(stage_id: str) -> bool:
    """Delete a stage config by stage_id."""
    stage = await get_stage_config(stage_id)
    if stage:
        await stage.delete()
        return True
    return False


async def reorder_stages(stage_ids: list[str]) -> list[StageConfigDocument]:
    """Reorder stages by updating their `order` field."""
    for idx, stage_id in enumerate(stage_ids):
        await StageConfigDocument.find_one(
            StageConfigDocument.stage_id == stage_id
        ).update({"$set": {"order": idx * 100, "updated_at": _now()}})
    return await get_all_stage_configs()
```

#### Updated Seed Data

```python
# app/db/seed.py — Updated DEFAULT_STAGES

DEFAULT_STAGES = [
    {
        "stage_id": "ingestion",
        "display_name": "Document Ingestion",
        "description": "Parse and chunk uploaded documents for downstream processing.",
        "order": 100,
        "color": "#6366F1",      # Indigo
        "icon": "file-input",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "testcase",
        "display_name": "Test Case Generation",
        "description": "Analyze requirements and generate comprehensive test cases.",
        "order": 200,
        "color": "#8B5CF6",      # Violet
        "icon": "flask-conical",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "execution",
        "display_name": "Test Execution",
        "description": "Execute generated test cases against the target system.",
        "order": 300,
        "color": "#F59E0B",      # Amber
        "icon": "play",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "reporting",
        "display_name": "Reporting",
        "description": "Analyze results, identify root causes, and generate reports.",
        "order": 400,
        "color": "#10B981",      # Emerald
        "icon": "file-bar-chart",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "custom",
        "display_name": "Custom / Unassigned",
        "description": "Catch-all stage for user-created agents not assigned to a specific stage.",
        "order": 9999,
        "color": "#6B7280",      # Gray
        "icon": "puzzle",
        "enabled": True,
        "is_builtin": True,
    },
]
```

### 3.2 Dynamic Agent Grouping (Backend)

#### Thay đổi `AgentConfigGrouped`

Hiện tại `AgentConfigGrouped` có 4+1 field cứng:

```python
# TRƯỚC (V3) — app/schemas/agent_config.py
class AgentConfigGrouped(BaseModel):
    ingestion: list[AgentConfigSummary] = []
    testcase: list[AgentConfigSummary] = []
    execution: list[AgentConfigSummary] = []
    reporting: list[AgentConfigSummary] = []
    custom: list[AgentConfigSummary] = []

    @classmethod
    def from_list(cls, agents):
        known_stages = {"ingestion", "testcase", "execution", "reporting"}
        grouped = {s: [] for s in known_stages}
        grouped["custom"] = []
        for agent in agents:
            if agent.stage in known_stages:
                grouped[agent.stage].append(agent)
            else:
                grouped["custom"].append(agent)
        return cls(**grouped)
```

Thay đổi thành dynamic:

```python
# SAU (V4) — app/schemas/agent_config.py

from app.db.models import StageConfigDocument


class AgentGroupEntry(BaseModel):
    """One stage group with its metadata and agents."""
    stage_id: str
    display_name: str
    description: Optional[str] = None
    order: int = 0
    color: Optional[str] = None
    icon: Optional[str] = None
    is_builtin: bool = False
    agents: list[AgentConfigSummary] = []


class AgentConfigGroupedResponse(BaseModel):
    """Dynamic agent grouping — no fixed fields."""
    groups: list[AgentGroupEntry]
    total_agents: int

    @classmethod
    async def from_list(
        cls, agents: list[AgentConfigSummary]
    ) -> "AgentConfigGroupedResponse":
        """Group agents by their stage, using stage configs from DB."""
        # Load all stages from DB
        stages = await StageConfigDocument.find().sort("+order").to_list()
        stage_map: dict[str, StageConfigDocument] = {
            s.stage_id: s for s in stages
        }
        
        # Build groups
        groups_dict: dict[str, list[AgentConfigSummary]] = {}
        for stage in stages:
            groups_dict[stage.stage_id] = []
        
        # Assign agents to groups
        for agent in agents:
            stage_id = agent.stage or "custom"
            if stage_id not in groups_dict:
                # Agent references a stage that doesn't exist anymore
                groups_dict.setdefault("custom", [])
                groups_dict["custom"].append(agent)
            else:
                groups_dict[stage_id].append(agent)
        
        # Build response
        groups = []
        for stage in stages:
            agents_in_stage = groups_dict.get(stage.stage_id, [])
            groups.append(AgentGroupEntry(
                stage_id=stage.stage_id,
                display_name=stage.display_name,
                description=stage.description,
                order=stage.order,
                color=stage.color,
                icon=stage.icon,
                is_builtin=stage.is_builtin,
                agents=agents_in_stage,
            ))
        
        return cls(
            groups=groups,
            total_agents=len(agents),
        )
```

#### Updated Agent Configs API

```python
# app/api/v1/agent_configs.py — Updated grouped endpoint

@router.get("", response_model=...) 
async def list_agent_configs(
    grouped: bool = Query(default=False),
    stage: Optional[str] = Query(default=None),
    enabled_only: bool = Query(default=False),
):
    """
    List agent configs.

    - `?grouped=true` → Returns `AgentConfigGroupedResponse` with dynamic stage groups
    - `?stage=testcase` → Filter by stage
    - `?enabled_only=true` → Only enabled agents
    """
    agents = await crud.get_all_agent_configs(
        stage=stage,
        enabled_only=enabled_only,
    )
    summaries = [_to_summary(a) for a in agents]
    
    if grouped:
        return await AgentConfigGroupedResponse.from_list(summaries)
    
    return summaries
```

### 3.3 Dynamic Stage UI (Frontend)

#### Updated TypeScript Types

```typescript
// src/types/index.ts — Updated stage types

// TRƯỚC (V3):
// export type AgentStage = "ingestion" | "testcase" | "execution" | "reporting";
// export const STAGE_LABELS: Record<AgentStage, string> = { ... };
// export const STAGE_ORDER: AgentStage[] = [ ... ];

// SAU (V4):
export interface StageConfig {
  id: string;
  stage_id: string;
  display_name: string;
  description?: string | null;
  order: number;
  color?: string | null;
  icon?: string | null;
  enabled: boolean;
  is_builtin: boolean;
  agent_count: number;
  created_at: string;
  updated_at: string;
}

export interface StageConfigCreate {
  stage_id: string;
  display_name: string;
  description?: string | null;
  order?: number;
  color?: string | null;
  icon?: string | null;
  enabled?: boolean;
}

export interface StageConfigUpdate {
  display_name?: string;
  description?: string | null;
  order?: number;
  color?: string | null;
  icon?: string | null;
  enabled?: boolean;
}

// Keep for backwards compat but derive from StageConfig
export type AgentStage = string;

// Dynamic grouping response
export interface AgentGroupEntry {
  stage_id: string;
  display_name: string;
  description?: string | null;
  order: number;
  color?: string | null;
  icon?: string | null;
  is_builtin: boolean;
  agents: AgentConfigSummary[];
}

export interface AgentConfigGroupedResponse {
  groups: AgentGroupEntry[];
  total_agents: number;
}

// Remove old static types:
// - AgentConfigGrouped (replaced by AgentConfigGroupedResponse)
// - STAGE_LABELS (derived from StageConfig[])
// - STAGE_ORDER (derived from StageConfig[])
```

#### Updated `useStageConfigs` Hook

```typescript
// src/hooks/useStageConfigs.ts — Rewritten (was calling 410 Gone API)

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { stageConfigsApi } from "@/lib/api";
import { queryKeys } from "@/lib/queryClient";
import type { StageConfig, StageConfigCreate, StageConfigUpdate } from "@/types";

export function useStageConfigs(enabledOnly = false) {
  return useQuery<StageConfig[]>({
    queryKey: queryKeys.stageConfigs.list({ enabled_only: enabledOnly }),
    queryFn: () => stageConfigsApi.list(enabledOnly),
    staleTime: 5 * 60 * 1000, // 5 minutes — stages change rarely
  });
}

export function useStageConfig(stageId: string) {
  return useQuery<StageConfig>({
    queryKey: queryKeys.stageConfigs.detail(stageId),
    queryFn: () => stageConfigsApi.get(stageId),
    enabled: !!stageId,
  });
}

export function useCreateStageConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: StageConfigCreate) => stageConfigsApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
    },
  });
}

export function useUpdateStageConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ stageId, data }: { stageId: string; data: StageConfigUpdate }) =>
      stageConfigsApi.update(stageId, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
    },
  });
}

export function useDeleteStageConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stageId: string) => stageConfigsApi.delete(stageId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
      qc.invalidateQueries({ queryKey: queryKeys.agentConfigs.all });
    },
  });
}

export function useReorderStages() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (stageIds: string[]) => stageConfigsApi.reorder(stageIds),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.stageConfigs.all });
    },
  });
}
```

#### Updated `useAgentConfigs` Hook

```typescript
// src/hooks/useAgentConfigs.ts — Updated grouped query

import type { AgentConfigGroupedResponse } from "@/types";

export function useAgentConfigsGrouped() {
  return useQuery<AgentConfigGroupedResponse>({
    queryKey: queryKeys.agentConfigs.grouped(),
    queryFn: () => agentConfigsApi.listGrouped(),
  });
}
```

#### Integrated Admin Agents Page

Trang `/admin/agents` sẽ được thiết kế lại để tích hợp cả Stage Management:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Agent Configs                                                     [+ Agent] │
│  ─────────────────────────────────────────────────────────────────────────── │
│  [Search agents...]   [Stage filter ▾]   [Manage Stages]                     │
│                                                                              │
│  ┌─── 📥 Document Ingestion (1 agent) ──────────── order: 100 ───────────┐  │
│  │  ┌─────────────────┐                                                   │  │
│  │  │ ingestion_pipe.. │  [Edit] [Reset]                                  │  │
│  │  └─────────────────┘                                                   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─── 🧪 Test Case Generation (10 agents) ──────── order: 200 ──────────┐  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │  │
│  │  │ requirement_an.. │  │ rule_parser     │  │ scope_classif.. │  ...   │  │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘        │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─── ▶️ Test Execution (5 agents) ──────────────── order: 300 ──────────┐  │
│  │  ...                                                                   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─── 📊 Reporting (3 agents) ───────────────────── order: 400 ──────────┐  │
│  │  ...                                                                   │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌─── 🔧 My Custom Stage (2 agents) ────────────── order: 500 ──────────┐  │
│  │  ┌─────────────────┐  ┌─────────────────┐                             │  │
│  │  │ custom_agent_1  │  │ custom_agent_2  │                             │  │
│  │  └─────────────────┘  └─────────────────┘                             │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

**"Manage Stages" Dialog:**

```
┌─────────────────── Manage Stages ────────────────────┐
│                                                       │
│  Drag to reorder. Built-in stages cannot be deleted.  │
│                                                       │
│  ⠿  📥 Document Ingestion     [100]  🔒  [Edit]      │
│  ⠿  🧪 Test Case Generation   [200]  🔒  [Edit]      │
│  ⠿  ▶️ Test Execution          [300]  🔒  [Edit]      │
│  ⠿  📊 Reporting              [400]  🔒  [Edit]      │
│  ⠿  🔧 My Custom Stage        [500]      [Edit] [🗑] │
│                                                       │
│  [+ Add Stage]                                        │
│                                                       │
│  ─────────────────────────────────────────────────    │
│  [Cancel]                              [Save Order]   │
└───────────────────────────────────────────────────────┘
```

#### Updated `AgentList.tsx` Component

```typescript
// src/components/admin/agents/AgentList.tsx — Key changes

"use client";

import { useAgentConfigsGrouped } from "@/hooks/useAgentConfigs";
import { useStageConfigs } from "@/hooks/useStageConfigs";
import { AgentGroupSection } from "./AgentGroupSection";
import { ManageStagesDialog } from "./ManageStagesDialog";  // NEW
import type { AgentGroupEntry } from "@/types";

export function AgentList() {
  const [search, setSearch] = useState("");
  const [stageFilter, setStageFilter] = useState<string>("all");
  const [manageStagesOpen, setManageStagesOpen] = useState(false);

  const { data: groupedData, isLoading } = useAgentConfigsGrouped();
  const { data: stages } = useStageConfigs();

  // Dynamic stage filter options — built from API data, not constants
  const stageFilterOptions = useMemo(() => {
    if (!stages) return [{ value: "all", label: "All Stages" }];
    return [
      { value: "all", label: "All Stages" },
      ...stages.map((s) => ({ value: s.stage_id, label: s.display_name })),
    ];
  }, [stages]);

  // Filter groups
  const filteredGroups = useMemo(() => {
    if (!groupedData?.groups) return [];
    
    return groupedData.groups
      .filter((group) => {
        if (stageFilter !== "all" && group.stage_id !== stageFilter) return false;
        return true;
      })
      .map((group) => ({
        ...group,
        agents: group.agents.filter((agent) => {
          if (!search) return true;
          const q = search.toLowerCase();
          return (
            agent.display_name.toLowerCase().includes(q) ||
            agent.agent_id.toLowerCase().includes(q)
          );
        }),
      }))
      .filter((group) => group.agents.length > 0 || !search);
  }, [groupedData, stageFilter, search]);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold">Agent Configs</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setManageStagesOpen(true)}>
            Manage Stages
          </Button>
          <AddAgentButton />
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-6">
        <Input placeholder="Search agents..." value={search} onChange={...} />
        <Select value={stageFilter} onValueChange={setStageFilter}>
          {stageFilterOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </Select>
      </div>

      {/* Dynamic Groups */}
      {filteredGroups.map((group) => (
        <AgentGroupSection
          key={group.stage_id}
          stageId={group.stage_id}
          displayName={group.display_name}
          description={group.description}
          color={group.color}
          icon={group.icon}
          isBuiltin={group.is_builtin}
          agents={group.agents}
        />
      ))}

      {/* Manage Stages Dialog */}
      <ManageStagesDialog
        open={manageStagesOpen}
        onOpenChange={setManageStagesOpen}
      />
    </div>
  );
}
```

#### New `ManageStagesDialog.tsx` Component

```typescript
// src/components/admin/agents/ManageStagesDialog.tsx — NEW

"use client";

import { useState, useEffect } from "react";
import {
  useStageConfigs,
  useCreateStageConfig,
  useUpdateStageConfig,
  useDeleteStageConfig,
  useReorderStages,
} from "@/hooks/useStageConfigs";
import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { StageConfig, StageConfigCreate } from "@/types";

interface ManageStagesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ManageStagesDialog({ open, onOpenChange }: ManageStagesDialogProps) {
  const { data: stages, isLoading } = useStageConfigs();
  const createMutation = useCreateStageConfig();
  const updateMutation = useUpdateStageConfig();
  const deleteMutation = useDeleteStageConfig();
  const reorderMutation = useReorderStages();

  const [orderedStages, setOrderedStages] = useState<StageConfig[]>([]);
  const [showAddForm, setShowAddForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Sync local state with fetched data
  useEffect(() => {
    if (stages) setOrderedStages([...stages]);
  }, [stages]);

  // Drag-and-drop reorder handler
  const handleDragEnd = (fromIndex: number, toIndex: number) => {
    const updated = [...orderedStages];
    const [moved] = updated.splice(fromIndex, 1);
    updated.splice(toIndex, 0, moved);
    setOrderedStages(updated);
  };

  const handleSaveOrder = async () => {
    const stageIds = orderedStages.map((s) => s.stage_id);
    await reorderMutation.mutateAsync(stageIds);
  };

  const handleCreateStage = async (data: StageConfigCreate) => {
    await createMutation.mutateAsync(data);
    setShowAddForm(false);
  };

  const handleDeleteStage = async (stageId: string) => {
    if (!confirm(`Delete stage "${stageId}"? Agents will be moved to "Custom".`)) return;
    await deleteMutation.mutateAsync(stageId);
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange} title="Manage Stages">
      <p className="text-sm text-muted-foreground mb-4">
        Drag to reorder. Built-in stages cannot be deleted.
      </p>

      <div className="space-y-2">
        {orderedStages.map((stage, index) => (
          <StageRow
            key={stage.stage_id}
            stage={stage}
            index={index}
            isEditing={editingId === stage.stage_id}
            onEdit={() => setEditingId(stage.stage_id)}
            onCancelEdit={() => setEditingId(null)}
            onSaveEdit={(data) => {
              updateMutation.mutate({ stageId: stage.stage_id, data });
              setEditingId(null);
            }}
            onDelete={() => handleDeleteStage(stage.stage_id)}
            onDragEnd={handleDragEnd}
          />
        ))}
      </div>

      {showAddForm ? (
        <AddStageForm
          onSubmit={handleCreateStage}
          onCancel={() => setShowAddForm(false)}
          isLoading={createMutation.isPending}
        />
      ) : (
        <Button variant="outline" className="mt-4 w-full" onClick={() => setShowAddForm(true)}>
          + Add Stage
        </Button>
      )}

      <div className="flex justify-end gap-2 mt-6 pt-4 border-t">
        <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
        <Button onClick={handleSaveOrder} disabled={reorderMutation.isPending}>
          Save Order
        </Button>
      </div>
    </Modal>
  );
}
```

#### Updated `AgentGroupSection.tsx`

```typescript
// src/components/admin/agents/AgentGroupSection.tsx — Updated

interface AgentGroupSectionProps {
  stageId: string;
  displayName: string;
  description?: string | null;
  color?: string | null;        // Dynamic color from StageConfig
  icon?: string | null;         // Dynamic icon name
  isBuiltin: boolean;
  agents: AgentConfigSummary[];
}

// TRƯỚC: STAGE_ACCENTS was a hardcoded Record<AgentStage, { bg, border, text, badge }>
// SAU:   Derive accent from the `color` prop

function getAccentFromColor(color: string | null | undefined) {
  if (!color) {
    return {
      bg: "bg-gray-50 dark:bg-gray-900/30",
      border: "border-gray-200 dark:border-gray-800",
      text: "text-gray-700 dark:text-gray-300",
      badge: "bg-gray-100 text-gray-700",
    };
  }
  // Use CSS custom properties for dynamic theming
  return {
    bg: `bg-opacity-5`,
    border: `border-opacity-20`,
    text: `text-opacity-90`,
    badge: `bg-opacity-10`,
    style: { "--stage-color": color } as React.CSSProperties,
  };
}

export function AgentGroupSection({
  stageId,
  displayName,
  description,
  color,
  icon,
  isBuiltin,
  agents,
}: AgentGroupSectionProps) {
  const accent = getAccentFromColor(color);
  
  return (
    <div
      className="rounded-lg border p-4 mb-4"
      style={{ borderColor: color ?? "#e5e7eb" }}
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {/* Dynamic icon - use a Lucide icon lookup */}
          <StageIcon name={icon} color={color} />
          <h3 className="font-semibold text-lg">{displayName}</h3>
          <span className="text-sm text-muted-foreground">
            ({agents.length} agent{agents.length !== 1 ? "s" : ""})
          </span>
          {isBuiltin && (
            <span className="text-xs px-2 py-0.5 rounded bg-blue-100 text-blue-700">
              Built-in
            </span>
          )}
        </div>
      </div>
      
      {description && (
        <p className="text-sm text-muted-foreground mb-3">{description}</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {agents.map((agent) => (
          <AgentCard key={agent.agent_id} agent={agent} stageColor={color} />
        ))}
      </div>
    </div>
  );
}
```

#### Updated `AddAgentDialog.tsx`

```typescript
// src/components/admin/agents/AddAgentDialog.tsx — Đã dùng useStageConfigs()

// AddAgentDialog đã gần đúng. Chỉ cần update:
// 1. Import từ updated useStageConfigs (không còn 410 Gone)
// 2. Fallback "custom" stage nếu không chọn stage

// Phần tạo agent:
const createAgentSchema = z.object({
  agent_id: z.string()
    .min(2).max(50)
    .regex(/^[a-z][a-z0-9_-]{1,49}$/),
  display_name: z.string().min(2).max(100),
  stage: z.string().min(1),        // Thay vì enum cứng, dùng string (validated against stage list)
  role: z.string().min(10),
  goal: z.string().min(10),
  backstory: z.string().min(10),
  llm_profile_id: z.string().optional().nullable(),
  max_iter: z.number().int().min(1).max(20).default(5),
});

// Stage dropdown sử dụng dynamic stages:
const { data: stages } = useStageConfigs(true); // enabled only

const stageOptions = useMemo(() => {
  if (!stages) return [];
  return stages.map((s) => ({
    value: s.stage_id,
    label: s.display_name,
  }));
}, [stages]);
```

### 3.4 Pipeline Builder Integration

#### Agent Catalog Sidebar — Dynamic Grouping

```typescript
// src/components/pipeline-builder/AgentCatalogSidebar.tsx — Updated

// TRƯỚC: Grouped agents using STAGE_ORDER constant
// SAU:   Use dynamic stages from useStageConfigs

export function AgentCatalogSidebar() {
  const { data: groupedData } = useAgentConfigsGrouped();
  const { data: stages } = useStageConfigs(true);

  // Build catalog groups from dynamic data
  const catalogGroups = useMemo(() => {
    const groups: CatalogGroup[] = [];

    // Special items (Input/Output nodes)
    groups.push({
      label: "Pipeline I/O",
      items: [
        { agentId: "__input__", label: "Input", nodeType: "input", description: "Pipeline input node" },
        { agentId: "__output__", label: "Output", nodeType: "output", description: "Pipeline output node" },
      ],
    });

    // Dynamic stage groups
    if (groupedData?.groups) {
      for (const group of groupedData.groups) {
        if (group.agents.length === 0) continue;
        groups.push({
          label: group.display_name,
          color: group.color,
          icon: group.icon,
          items: group.agents.map((agent) => ({
            agentId: agent.agent_id,
            label: agent.display_name,
            nodeType: agent.stage === "ingestion" ? "pure_python" : "agent",
            description: `${agent.display_name} (${group.display_name})`,
            stage: agent.stage,
          })),
        });
      }
    }

    return groups;
  }, [groupedData]);

  // ... rest of component
}
```

---

## 4. Feature 2 – Frontend ↔ Backend Route Synchronization

### 4.1 Critical Bugs (🔴 Will Fail at Runtime)

#### Bug 1: `pipelineTemplatesApi.clone()` — Query params vs Body

**Problem**: Frontend sends clone name in request body. Backend expects `new_template_id` and `new_name` as required query parameters.

**Fix (Backend)**: Change backend to accept body instead of query params (more RESTful).

```python
# app/api/v1/pipeline_templates.py — BEFORE:
async def clone_template(
    template_id: str,
    new_template_id: str = Query(...),
    new_name: str = Query(...),
):

# AFTER:
class CloneTemplateRequest(BaseModel):
    new_template_id: str = Field(
        ...,
        pattern=r"^[a-z][a-z0-9_-]{2,49}$",
        description="URL-safe slug for the cloned template.",
    )
    new_name: str = Field(
        ...,
        min_length=2,
        max_length=200,
        description="Display name for the cloned template.",
    )

@router.post("/{template_id}/clone", response_model=PipelineTemplateResponse)
async def clone_template(
    template_id: str,
    body: CloneTemplateRequest,
):
    ...
```

**Fix (Frontend)**: Update API call to send both fields:

```typescript
// src/lib/api.ts — BEFORE:
clone: async (templateId: string, newName?: string) => {
  const { data } = await apiClient.post(
    `/api/v1/pipeline-templates/${templateId}/clone`,
    newName ? { name: newName } : {},
  );
  return data;
},

// AFTER:
clone: async (
  templateId: string,
  newTemplateId: string,
  newName: string,
): Promise<PipelineTemplate> => {
  const { data } = await apiClient.post<PipelineTemplate>(
    `/api/v1/pipeline-templates/${templateId}/clone`,
    { new_template_id: newTemplateId, new_name: newName },
  );
  return data;
},
```

---

#### Bug 2: `pipelineTemplatesApi.importTemplate()` — Wrong payload shape

**Problem**: Frontend sends raw `PipelineTemplate` object. Backend expects envelope `{ export_type: "pipeline_template", template: {...} }`.

**Fix (Frontend)**:

```typescript
// src/lib/api.ts — BEFORE:
importTemplate: async (templateData: PipelineTemplate): Promise<PipelineTemplate> => {
  const { data } = await apiClient.post<PipelineTemplate>(
    "/api/v1/pipeline-templates/import",
    templateData,
  );
  return data;
},

// AFTER:
importTemplate: async (templateData: PipelineTemplate): Promise<PipelineTemplate> => {
  const envelope = {
    auto_at_version: "3.0",
    export_type: "pipeline_template",
    template: templateData,
  };
  const { data } = await apiClient.post<PipelineTemplate>(
    "/api/v1/pipeline-templates/import",
    envelope,
  );
  return data;
},
```

---

#### Bug 3: `pipelineTemplatesApi.exportTemplate()` — Response shape mismatch

**Problem**: Backend returns `{ auto_at_version, export_type, template: {...} }`. Frontend expects flat `PipelineTemplate`.

**Fix (Frontend)**:

```typescript
// src/lib/api.ts — BEFORE:
exportTemplate: async (templateId: string): Promise<PipelineTemplate> => {
  const { data } = await apiClient.get<PipelineTemplate>(
    `/api/v1/pipeline-templates/${templateId}/export`,
  );
  return data;
},

// AFTER:
interface TemplateExportEnvelope {
  auto_at_version: string;
  export_type: "pipeline_template";
  template: PipelineTemplate;
}

exportTemplate: async (templateId: string): Promise<TemplateExportEnvelope> => {
  const { data } = await apiClient.get<TemplateExportEnvelope>(
    `/api/v1/pipeline-templates/${templateId}/export`,
  );
  return data;
},

// Helper to extract template from envelope
exportTemplateRaw: async (templateId: string): Promise<PipelineTemplate> => {
  const envelope = await pipelineTemplatesApi.exportTemplate(templateId);
  return envelope.template;
},
```

### 4.2 High Severity Fixes (🟠 Wrong Data)

#### Bug 4: `pipelineApi.getNodeResult()` — Backend endpoint doesn't exist

**Problem**: Frontend calls `GET /pipeline/runs/{run_id}/results/{node_id}` — no such route.

**Fix (Backend)**: Add the missing endpoint.

```python
# app/api/v1/pipeline.py — NEW endpoint

@router.get(
    "/runs/{run_id}/results/{node_id}",
    response_model=PipelineResultResponse,
    summary="Get result for a specific node in a pipeline run",
)
async def get_node_result(run_id: str, node_id: str):
    """Get the pipeline result for a specific node."""
    result = await crud.get_pipeline_result_by_node(run_id, node_id)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No result found for node '{node_id}' in run '{run_id}'.",
        )
    return _result_to_response(result)
```

```python
# app/db/crud.py — NEW function

async def get_pipeline_result_by_node(
    run_id: str, node_id: str
) -> Optional[PipelineResultDocument]:
    """Get a single pipeline result by run_id + node_id."""
    return await PipelineResultDocument.find_one(
        PipelineResultDocument.run_id == run_id,
        PipelineResultDocument.node_id == node_id,
    )
```

---

#### Bug 5: `pipelineApi.cancelRun()` — Response type mismatch

**Problem**: Frontend expects `PipelineRunResponse`, backend returns `{ status, run_id, message }`.

**Fix (Backend)**: Return consistent response schema.

```python
# app/api/v1/pipeline.py — BEFORE:
return {
    "status": "cancel_requested",
    "run_id": run_id,
    "message": "Cancellation signal sent...",
}

# AFTER — return a PipelineActionResponse (new schema):
class PipelineActionResponse(BaseModel):
    """Response for pipeline actions (pause/resume/cancel)."""
    status: str
    run_id: str
    message: str

@router.post("/runs/{run_id}/cancel", response_model=PipelineActionResponse)
async def cancel_pipeline(run_id: str):
    ...
    return PipelineActionResponse(
        status="cancel_requested",
        run_id=run_id,
        message="Cancellation signal sent. The pipeline will stop at the next checkpoint.",
    )
```

**Fix (Frontend)**:

```typescript
// src/types/index.ts — NEW
export interface PipelineActionResponse {
  status: string;
  run_id: string;
  message: string;
}

// src/lib/api.ts — BEFORE:
cancelRun: async (runId: string): Promise<PipelineRunResponse> => { ... }

// AFTER:
cancelRun: async (runId: string): Promise<PipelineActionResponse> => {
  const { data } = await apiClient.post<PipelineActionResponse>(
    `/api/v1/pipeline/runs/${runId}/cancel`,
  );
  return data;
},

// Same fix for pauseRun and resumeRun:
pauseRun: async (runId: string): Promise<PipelineActionResponse> => { ... },
resumeRun: async (runId: string): Promise<PipelineActionResponse> => { ... },
```

---

#### Bug 6: `pipelineApi.getStageResults()` — Response type mismatch

**Problem**: Frontend expects `Record<string, unknown>` (dict), backend returns `list[PipelineResultResponse]` (array).

**Fix (Frontend)**: Match the backend's actual response type.

```typescript
// src/lib/api.ts — BEFORE:
getStageResults: async (runId: string, stage?: string): Promise<Record<string, unknown>> => { ... }

// AFTER:
getRunResults: async (
  runId: string,
  params?: { stage?: string; agent_id?: string; node_id?: string },
): Promise<PipelineNodeResult[]> => {
  const { data } = await apiClient.get<PipelineNodeResult[]>(
    `/api/v1/pipeline/runs/${runId}/results`,
    { params },
  );
  return data;
},
```

---

#### Bug 7: `pipelineApi.listRuns()` — `template_id` filter ignored

**Problem**: Frontend sends `template_id` query param, backend doesn't accept it.

**Fix (Backend)**:

```python
# app/api/v1/pipeline.py — BEFORE:
async def list_pipeline_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
):

# AFTER:
async def list_pipeline_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    template_id: Optional[str] = Query(
        default=None,
        description="Filter runs by pipeline template ID",
    ),
):
    ...
    runs = await crud.get_all_pipeline_runs(
        page=page,
        page_size=page_size,
        status=status_filter,
        template_id=template_id,      # NEW
    )
```

```python
# app/db/crud.py — Updated

async def get_all_pipeline_runs(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    template_id: Optional[str] = None,   # NEW
) -> tuple[list[PipelineRunDocument], int]:
    query = {}
    if status:
        query["status"] = status
    if template_id:
        query["template_id"] = template_id
    
    total = await PipelineRunDocument.find(query).count()
    runs = await (
        PipelineRunDocument.find(query)
        .sort("-created_at")
        .skip((page - 1) * page_size)
        .limit(page_size)
        .to_list()
    )
    return runs, total
```

### 4.3 Medium Severity Fixes (🟡 Type Issues / Dead Code)

#### Bug 8: Dead `stageConfigsApi` code

**Fix**: Update `stageConfigsApi` in `api.ts` to work with restored Stage Config API.

```typescript
// src/lib/api.ts — Rewrite stageConfigsApi

export const stageConfigsApi = {
  list: async (enabledOnly = false): Promise<StageConfig[]> => {
    const { data } = await apiClient.get<StageConfig[]>(
      "/api/v1/admin/stage-configs",
      { params: enabledOnly ? { enabled_only: true } : {} },
    );
    return data;
  },

  get: async (stageId: string): Promise<StageConfig> => {
    const { data } = await apiClient.get<StageConfig>(
      `/api/v1/admin/stage-configs/${stageId}`,
    );
    return data;
  },

  create: async (body: StageConfigCreate): Promise<StageConfig> => {
    const { data } = await apiClient.post<StageConfig>(
      "/api/v1/admin/stage-configs",
      body,
    );
    return data;
  },

  update: async (stageId: string, body: StageConfigUpdate): Promise<StageConfig> => {
    const { data } = await apiClient.put<StageConfig>(
      `/api/v1/admin/stage-configs/${stageId}`,
      body,
    );
    return data;
  },

  delete: async (stageId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/admin/stage-configs/${stageId}`);
  },

  reorder: async (stageIds: string[]): Promise<StageConfig[]> => {
    const { data } = await apiClient.post<StageConfig[]>(
      "/api/v1/admin/stage-configs/reorder",
      { stage_ids: stageIds },
    );
    return data;
  },
};
```

---

#### Bug 9: `LLMProfileResponse.id` typed as `number`

**Fix (Frontend)**:

```typescript
// src/types/index.ts — BEFORE:
export interface LLMProfileResponse {
  id: number;      // ❌ MongoDB ObjectId is string
  name: string;
  ...
}

// AFTER:
export interface LLMProfileResponse {
  id: string;      // ✅ MongoDB ObjectId string
  name: string;
  ...
}

// Same fix for ChatProfileItem:
export interface ChatProfileItem {
  id: string;      // Was: number
  name: string;
  provider: string;
  model: string;
}
```

---

#### Bug 10: Agent `delete` response type mismatch

**Problem**: Backend returns 204 No Content. Frontend expects `{ deleted: string }`.

**Fix (Frontend)**:

```typescript
// src/lib/api.ts — BEFORE:
delete: async (agentId: string): Promise<{ deleted: string }> => {
  const { data } = await apiClient.delete<{ deleted: string }>(
    `/api/v1/admin/agent-configs/${agentId}`,
  );
  return data;
},

// AFTER:
delete: async (agentId: string): Promise<void> => {
  await apiClient.delete(`/api/v1/admin/agent-configs/${agentId}`);
},
```

---

#### Bug 11: `ChatRequest.llm_profile_id` type

**Fix (Frontend)**:

```typescript
// src/types/index.ts — BEFORE:
export interface ChatRequest {
  messages: { role: ChatRole; content: string }[];
  llm_profile_id?: number | null;     // ❌
  system_prompt?: string | null;
}

// AFTER:
export interface ChatRequest {
  messages: { role: ChatRole; content: string }[];
  llm_profile_id?: string | null;     // ✅ MongoDB ObjectId string
  system_prompt?: string | null;
}
```

---

#### Bug 12: `pipelineTemplatesApi.list()` return shape

**Problem**: Backend returns `list[PipelineTemplateListItem]`, frontend wraps into `{ items, total }`.

**Fix (Backend)**: Return paginated envelope to match frontend expectations.

```python
# app/api/v1/pipeline_templates.py — BEFORE:
return templates

# AFTER:
class PaginatedTemplateResponse(BaseModel):
    items: list[PipelineTemplateListItem]
    total: int
    page: int
    page_size: int

@router.get("", response_model=PaginatedTemplateResponse)
async def list_templates(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    ...
):
    ...
    return PaginatedTemplateResponse(
        items=[_to_list_item(t) for t in templates],
        total=total,
        page=page,
        page_size=page_size,
    )
```

---

### 4.4 Deprecated Page Cleanup

#### Remove `/admin/stages` page

```
DELETE: src/app/admin/stages/page.tsx
```

Remove breadcrumb handling for `/admin/stages` in `src/app/admin/layout.tsx`.

The stage management is now integrated into `/admin/agents` via the "Manage Stages" dialog.

---

## 5. Detailed Bug Fixes & Sync Matrix

### Complete Sync Matrix

| # | Severity | Area | Frontend | Backend | Fix Location | Status |
|---|----------|------|----------|---------|-------------|--------|
| 1 | 🔴 Critical | Template Clone | Sends body | Expects query params | **BE**: Accept body | New |
| 2 | 🔴 Critical | Template Import | Sends raw template | Expects envelope | **FE**: Wrap in envelope | New |
| 3 | 🔴 Critical | Template Export | Expects flat template | Returns envelope | **FE**: Unwrap envelope | New |
| 4 | 🟠 High | Node Result | Calls endpoint | Endpoint missing | **BE**: Add endpoint | New |
| 5 | 🟠 High | Cancel Run | Expects `PipelineRunResponse` | Returns `{status, run_id, message}` | **Both**: New schema | New |
| 6 | 🟠 High | Stage Results | Expects `Record<string, unknown>` | Returns `list[...]` | **FE**: Fix type | New |
| 7 | 🟠 High | List Runs | Sends `template_id` | Doesn't accept it | **BE**: Add filter | New |
| 8 | 🟡 Medium | Stage Configs API | Calls active API | Returns 410 Gone | **BE**: Restore API | New |
| 9 | 🟡 Medium | LLM Profile ID | Typed `number` | Returns `string` | **FE**: Fix type | New |
| 10 | 🟡 Medium | Agent Delete | Expects `{deleted}` | Returns 204 | **FE**: Fix type | New |
| 11 | 🟡 Medium | Chat LLM ID | Typed `number \| null` | Expects `string` | **FE**: Fix type | New |
| 12 | 🟡 Medium | Template List | Expects `{items, total}` | Returns array | **BE**: Return envelope | New |
| 13 | 🟢 Low | Pagination | Sends `skip/limit` | Expects `page/page_size` | **FE**: Use page/page_size | New |
| 14 | 🟢 Low | `/admin/stages` | Exists but orphaned | N/A | **FE**: Remove page | New |

---

## 6. Updated Data Models

### Model Changes Summary (V3 → V4)

| Collection | Change | Description |
|-----------|--------|-------------|
| `stage_configs` | **Restored + Updated** | Added `color`, `icon`, `description` fields. `is_builtin` flag. |
| `agent_configs` | Minor | `stage` field now accepts any valid `stage_id` (not just 4 hardcoded) |
| `pipeline_runs` | No change | |
| `pipeline_results` | No change | |
| `pipeline_templates` | No change | |
| `llm_profiles` | No change | |

### Updated Indexes

```javascript
// stage_configs
db.stage_configs.createIndex({ "stage_id": 1 }, { unique: true })
db.stage_configs.createIndex({ "order": 1, "enabled": 1 })

// agent_configs — existing index on stage is fine (string field)
db.agent_configs.createIndex({ "agent_id": 1 }, { unique: true })
db.agent_configs.createIndex({ "stage": 1 })
```

---

## 7. Updated API Endpoints

### Complete Endpoint Map V4

#### Health
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/` | Root info |

#### Pipeline Templates (No Change)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/pipeline-templates` | List templates (paginated) — **FIX: return envelope** |
| `POST` | `/api/v1/pipeline-templates` | Create template |
| `GET` | `/api/v1/pipeline-templates/{id}` | Get template |
| `PUT` | `/api/v1/pipeline-templates/{id}` | Update template |
| `DELETE` | `/api/v1/pipeline-templates/{id}` | Delete template |
| `POST` | `/api/v1/pipeline-templates/{id}/clone` | Clone — **FIX: accept body** |
| `POST` | `/api/v1/pipeline-templates/{id}/archive` | Archive/unarchive |
| `POST` | `/api/v1/pipeline-templates/{id}/validate` | Validate DAG |
| `GET` | `/api/v1/pipeline-templates/{id}/export` | Export (envelope) |
| `POST` | `/api/v1/pipeline-templates/import` | Import (expects envelope) |

#### Pipeline Runs (UPDATED)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/pipeline/run` | V2 legacy run |
| `POST` | `/api/v1/pipeline/runs` | V3 DAG run |
| `GET` | `/api/v1/pipeline/runs` | List runs — **FIX: add `template_id` filter** |
| `GET` | `/api/v1/pipeline/runs/{run_id}` | Get run detail |
| `DELETE` | `/api/v1/pipeline/runs/{run_id}` | Delete run |
| `POST` | `/api/v1/pipeline/runs/{run_id}/pause` | Pause — **FIX: return `PipelineActionResponse`** |
| `POST` | `/api/v1/pipeline/runs/{run_id}/resume` | Resume — **FIX: return `PipelineActionResponse`** |
| `POST` | `/api/v1/pipeline/runs/{run_id}/cancel` | Cancel — **FIX: return `PipelineActionResponse`** |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results` | List all results |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results/{node_id}` | **NEW**: Get single node result |
| `GET` | `/api/v1/pipeline/runs/{run_id}/export/html` | Export HTML report |
| `GET` | `/api/v1/pipeline/runs/{run_id}/export/docx` | Export DOCX report |

#### WebSocket (No Change)
| Path | Description |
|------|-------------|
| `WS /ws/pipeline/{run_id}` | Real-time events |

#### Admin — LLM Profiles (No Change)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/llm-profiles` | List profiles |
| `POST` | `/api/v1/admin/llm-profiles` | Create profile |
| `GET` | `/api/v1/admin/llm-profiles/{id}` | Get profile |
| `PUT` | `/api/v1/admin/llm-profiles/{id}` | Update profile |
| `DELETE` | `/api/v1/admin/llm-profiles/{id}` | Delete profile |
| `POST` | `/api/v1/admin/llm-profiles/{id}/set-default` | Set default |
| `POST` | `/api/v1/admin/llm-profiles/{id}/test` | Test connection |

#### Admin — Agent Configs (UPDATED)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/agent-configs` | List (flat or grouped) — **FIX: dynamic grouping** |
| `GET` | `/api/v1/admin/agent-configs/{agent_id}` | Get agent |
| `POST` | `/api/v1/admin/agent-configs` | Create agent |
| `PUT` | `/api/v1/admin/agent-configs/{agent_id}` | Update agent |
| `DELETE` | `/api/v1/admin/agent-configs/{agent_id}` | Delete agent — **FIX: FE handle 204** |
| `POST` | `/api/v1/admin/agent-configs/{agent_id}/reset` | Reset to seed |
| `POST` | `/api/v1/admin/agent-configs/reset-all` | Reset all to seed |

#### Admin — Stage Configs (RESTORED)
| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/admin/stage-configs` | List all stages |
| `GET` | `/api/v1/admin/stage-configs/{stage_id}` | Get stage |
| `POST` | `/api/v1/admin/stage-configs` | Create custom stage |
| `PUT` | `/api/v1/admin/stage-configs/{stage_id}` | Update stage |
| `DELETE` | `/api/v1/admin/stage-configs/{stage_id}` | Delete custom stage |
| `POST` | `/api/v1/admin/stage-configs/reorder` | Reorder stages |

#### Chat (No Change)
| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/chat/send` | Stream chat response |
| `GET` | `/api/v1/chat/profiles` | List chat profiles |

---

## 8. Updated Frontend Types & Components

### Route Map V4

| Route | Component | Change |
|-------|-----------|--------|
| `/` | redirect → `/pipelines` | No change |
| `/pipelines` | `<PipelineListPage />` | No change |
| `/pipelines/new` | Create template form | No change |
| `/pipelines/[templateId]` | `<PipelineBuilder />` | Updated: dynamic catalog groups |
| `/pipelines/[templateId]/run` | `<PipelineRunPage />` | No change |
| `/pipelines/[templateId]/runs` | `<PipelineRunHistoryPage />` | Fix: template_id filter works |
| `/chat` | `<ChatPage />` | No change |
| `/admin/llm` | `<LLMProfileList />` | No change |
| `/admin/agents` | `<AgentList />` | **Updated**: dynamic stages + "Manage Stages" |
| `/admin/stages` | ~~Deprecated page~~ | **Removed** |

### New Components

| Component | Path | Description |
|-----------|------|-------------|
| `ManageStagesDialog` | `src/components/admin/agents/ManageStagesDialog.tsx` | Create/edit/delete/reorder stages |
| `StageRow` | `src/components/admin/agents/StageRow.tsx` | Single stage row in manage dialog |
| `AddStageForm` | `src/components/admin/agents/AddStageForm.tsx` | Inline form to create new stage |
| `StageIcon` | `src/components/admin/agents/StageIcon.tsx` | Dynamic Lucide icon renderer |

### Updated Components

| Component | Change |
|-----------|--------|
| `AgentList.tsx` | Dynamic grouping, "Manage Stages" button, dynamic filter options |
| `AgentGroupSection.tsx` | Accept dynamic props (`color`, `icon`, `description`) instead of hardcoded `STAGE_ACCENTS` |
| `AgentCard.tsx` | Accept `stageColor` prop for dynamic badge coloring |
| `AddAgentDialog.tsx` | Already uses `useStageConfigs` — just works now (API restored) |
| `AgentDialog.tsx` | Stage badge uses dynamic color |
| `AgentCatalogSidebar.tsx` | Dynamic stage groups in pipeline builder |
| `PipelineTemplateCard.tsx` | Fix clone mutation to pass required params |
| `PipelineRunHistoryPage.tsx` | template_id filter now works |
| `PipelineProgress.tsx` | Remove hardcoded `STAGE_AGENT_COUNTS`, compute dynamically |
| `StageResultsPanel.tsx` | Remove hardcoded `DEFAULT_STAGES`, use dynamic stage list |
| `ResultsViewer.tsx` | Remove hardcoded stage string comparisons |

### Updated Hooks

| Hook | Change |
|------|--------|
| `useStageConfigs.ts` | **Rewritten** — works with restored API |
| `useAgentConfigs.ts` | `useAgentConfigsGrouped` returns `AgentConfigGroupedResponse` |
| `usePipeline.ts` | Fix `useNodeResult`, `useCancelPipeline` types |
| `usePipelineTemplates.ts` | Fix `useCloneTemplate`, `useImportTemplate`, `useExportTemplate` |

### Updated Types (`src/types/index.ts`)

| Type | Change |
|------|--------|
| `AgentStage` | `string` (was 4-member union) |
| `AgentConfigGrouped` | **Removed** (replaced by `AgentConfigGroupedResponse`) |
| `AgentConfigGroupedResponse` | **New** — `{ groups: AgentGroupEntry[], total_agents: number }` |
| `AgentGroupEntry` | **New** — `{ stage_id, display_name, color, agents[] }` |
| `StageConfig` | **Updated** — added `color`, `icon`, `description`, `agent_count` |
| `StageConfigCreate` | **Updated** — added `color`, `icon`, `description` |
| `StageConfigUpdate` | **Updated** — added `color`, `icon`, `description` |
| `LLMProfileResponse.id` | `string` (was `number`) |
| `ChatProfileItem.id` | `string` (was `number`) |
| `ChatRequest.llm_profile_id` | `string \| null` (was `number \| null`) |
| `PipelineActionResponse` | **New** — `{ status, run_id, message }` |
| `TemplateExportEnvelope` | **New** — `{ auto_at_version, export_type, template }` |
| `STAGE_LABELS` | **Removed** (derived from StageConfig API) |
| `STAGE_ORDER` | **Removed** (derived from StageConfig API) |

### Updated Query Keys

```typescript
// src/lib/queryClient.ts — Add stage config keys

export const queryKeys = {
  // ... existing keys ...
  
  stageConfigs: {
    all: ["stage-configs"] as const,
    list: (params?: Record<string, unknown>) => 
      ["stage-configs", "list", params] as const,
    detail: (stageId: string) => 
      ["stage-configs", "detail", stageId] as const,
  },
};
```

---

## 9. Updated Folder Structure

### Changes Only (relative to V3)

```
backend/
  app/
    api/v1/
      stage_configs.py          # REWRITTEN (was 410 Gone stubs)
      pipeline.py               # UPDATED (add node result endpoint, template_id filter)
      pipeline_templates.py     # UPDATED (clone accepts body, list returns envelope)
      agent_configs.py          # UPDATED (dynamic grouping)
    db/
      crud.py                   # UPDATED (new stage CRUD functions)
      models.py                 # UPDATED (StageConfigDocument fields)
      seed.py                   # UPDATED (stage seed data with colors/icons)
    schemas/
      agent_config.py           # UPDATED (AgentConfigGroupedResponse)
      stage_config.py           # UPDATED (new fields)
      pipeline.py               # UPDATED (PipelineActionResponse)

frontend/
  src/
    app/admin/stages/           # DELETED (deprecated page removed)
    components/admin/agents/
      AgentList.tsx              # UPDATED (dynamic grouping)
      AgentGroupSection.tsx      # UPDATED (dynamic props)
      AgentCard.tsx              # UPDATED (dynamic badge color)
      ManageStagesDialog.tsx     # NEW
      StageRow.tsx               # NEW
      AddStageForm.tsx           # NEW
      StageIcon.tsx              # NEW
    components/admin/stages/     # DELETED (no longer needed)
    components/pipeline-builder/
      AgentCatalogSidebar.tsx    # UPDATED (dynamic groups)
    hooks/
      useStageConfigs.ts         # REWRITTEN
      useAgentConfigs.ts         # UPDATED
      usePipeline.ts             # UPDATED (fix types)
      usePipelineTemplates.ts    # UPDATED (fix types)
    lib/
      api.ts                     # UPDATED (fix all API calls)
      queryClient.ts             # UPDATED (add stageConfigs keys)
    types/
      index.ts                   # UPDATED (fix types, add new interfaces)
```

---

## 10. Implementation Phases

### Phase 22 – Backend: Restore Stage Config API + Dynamic Grouping `~1.5 ngày` ✅ DONE

**Tasks:**
1. ✅ Update `StageConfigDocument` model — add `color`, `icon`, `description` fields
2. ✅ Rewrite `stage_configs.py` router — full CRUD + reorder (remove 410 Gone)
3. ✅ Add new CRUD functions: `count_agents_by_stage`, `reassign_agents_stage`
4. ✅ Update `AgentConfigGrouped` → `AgentConfigGroupedResponse` with dynamic grouping
5. ✅ Update seed data — add colors and icons for 4 built-in stages + "custom" catch-all
6. ✅ Register restored stage config router in `main.py`

**Test:**
- `POST /api/v1/admin/stage-configs` creates custom stage
- `GET /api/v1/admin/stage-configs` returns all stages with `agent_count`
- `GET /api/v1/admin/agent-configs?grouped=true` returns dynamic `{ groups, total_agents }`
- `DELETE /api/v1/admin/stage-configs/{custom_stage_id}` reassigns agents to "custom"
- Built-in stages reject DELETE with 403

---

### Phase 23 – Backend: Route Sync Fixes `~1 ngày` ✅ DONE

**Tasks:**
1. ✅ Fix `clone_template` — accept body (`CloneTemplateRequest`) instead of query params
2. ✅ Fix `list_pipeline_runs` — add `template_id` filter param
3. ✅ Fix `cancel/pause/resume` — return `PipelineActionResponse` schema
4. ✅ Add `GET /pipeline/runs/{run_id}/results/{node_id}` endpoint
5. ✅ Add `get_pipeline_result_by_node` CRUD function
6. ✅ Fix `list_templates` — return paginated envelope `{ items, total, page, page_size }`

**Test:**
- `POST /api/v1/pipeline-templates/{id}/clone` with body `{ new_template_id, new_name }` works
- `GET /api/v1/pipeline/runs?template_id=xxx` returns filtered results
- `POST /api/v1/pipeline/runs/{id}/cancel` returns `{ status, run_id, message }`
- `GET /api/v1/pipeline/runs/{run_id}/results/{node_id}` returns single result
- `GET /api/v1/pipeline-templates` returns `{ items: [...], total, page, page_size }`

---

### Phase 24 – Frontend: Type Fixes + API Sync `~1 ngày` ✅ DONE

**Tasks:**
1. ✅ Fix `LLMProfileResponse.id` → `string`
2. ✅ Fix `ChatProfileItem.id` → `string`
3. ✅ Fix `ChatRequest.llm_profile_id` → `string | null`
4. ✅ Add `PipelineActionResponse` type
5. ✅ Add `TemplateExportEnvelope` type
6. ✅ Update `AgentStage` to `string`
7. ✅ Replace `AgentConfigGrouped` with `AgentConfigGroupedResponse`
8. ✅ Add `AgentGroupEntry` interface
9. ✅ Update `StageConfig` interface — add new fields
10. ✅ Remove `STAGE_LABELS`, `STAGE_ORDER` constants
11. ✅ Rewrite `stageConfigsApi` in `api.ts`
12. ✅ Fix `pipelineTemplatesApi.clone()` — send body with both params
13. ✅ Fix `pipelineTemplatesApi.importTemplate()` — wrap in envelope
14. ✅ Fix `pipelineTemplatesApi.exportTemplate()` — return envelope type
15. ✅ Fix `pipelineApi.cancelRun/pauseRun/resumeRun()` — use `PipelineActionResponse`
16. ✅ Fix `pipelineApi.getStageResults()` → `getRunResults()` — correct return type
17. ✅ Fix `agentConfigsApi.delete()` — handle 204 No Content
18. ✅ Rewrite `useStageConfigs.ts` hook
19. ✅ Update `useAgentConfigs.ts` — grouped response type
20. ✅ Update `usePipeline.ts` — fix `useNodeResult`, `useCancelPipeline`
21. ✅ Update `usePipelineTemplates.ts` — fix clone/import/export
22. ✅ Add `stageConfigs` to `queryKeys`

**Test:**
- TypeScript compilation passes with zero type errors related to these changes
- All API calls match backend contract
- `useStageConfigs()` returns data (not 410 Gone)

---

### Phase 25 – Frontend: Dynamic Stage UI `~1.5 ngày` ✅ DONE

**Tasks:**
1. ✅ Create `ManageStagesDialog.tsx` — full stage CRUD + drag-to-reorder
2. ✅ Create `StageRow.tsx` — individual stage row component
3. ✅ Create `AddStageForm.tsx` — inline form for creating new stage
4. ✅ Create `StageIcon.tsx` — dynamic Lucide icon renderer
5. ✅ Rewrite `AgentList.tsx` — dynamic grouping, "Manage Stages" button, dynamic filters
6. ✅ Rewrite `AgentGroupSection.tsx` — accept dynamic props (color, icon, description)
7. ✅ Update `AgentCard.tsx` — dynamic stage badge color
8. ✅ Update `AgentCatalogSidebar.tsx` — dynamic stage groups in pipeline builder
9. ✅ Update `PipelineProgress.tsx` — remove hardcoded stage counts
10. ✅ Update `StageResultsPanel.tsx` — remove hardcoded stages
11. ✅ Update `ResultsViewer.tsx` — remove hardcoded stage comparisons
12. ✅ Delete `/admin/stages` page directory
13. ✅ Remove `components/admin/stages/` directory (deprecated components)
14. ✅ Update `admin/layout.tsx` — remove `/admin/stages` breadcrumb handling

**Test:**
- `/admin/agents` shows dynamic stage groups from API
- "Manage Stages" dialog opens with all stages listed
- Creating a new stage makes it appear in agent list immediately
- Deleting a custom stage reassigns its agents to "Custom"
- Reordering stages updates display order
- Pipeline builder catalog shows agents grouped by dynamic stages
- No TypeScript errors
- No console errors

---

### Phase Timeline Summary

| Phase | Name | Duration | Dependencies |
|-------|------|----------|-------------|
| 22 | Backend: Stage Config API + Dynamic Grouping | ~1.5 ngày | None |
| 23 | Backend: Route Sync Fixes | ~1 ngày | None |
| 24 | Frontend: Type Fixes + API Sync | ~1 ngày | Phase 22 + 23 |
| 25 | Frontend: Dynamic Stage UI | ~1.5 ngày | Phase 24 |
| | **Total** | **~5 ngày** | |

> **Note**: Phase 22 và 23 có thể thực hiện song song (không phụ thuộc nhau).
> Phase 24 phải chờ cả 2 phase backend hoàn thành.
> Phase 25 phải chờ Phase 24.`
>
> **Critical Path**: 22 → 24 → 25 = **4 ngày**
> **Parallel Path**: 23 chạy song song với 22

---

## Appendix A: Files Changed Summary

### Backend — Modified Files

| File | Type | Description |
|------|------|-------------|
| `app/db/models.py` | Modified | StageConfigDocument updated |
| `app/db/crud.py` | Modified | New stage CRUD + agent reassign functions |
| `app/db/seed.py` | Modified | Stage seed data with colors/icons |
| `app/schemas/stage_config.py` | Modified | New fields (color, icon, description) |
| `app/schemas/agent_config.py` | Modified | AgentConfigGroupedResponse (dynamic) |
| `app/schemas/pipeline.py` | Modified | PipelineActionResponse |
| `app/schemas/pipeline_template.py` | Modified | CloneTemplateRequest, PaginatedTemplateResponse |
| `app/api/v1/stage_configs.py` | Rewritten | Full CRUD (was 410 Gone) |
| `app/api/v1/agent_configs.py` | Modified | Dynamic grouping |
| `app/api/v1/pipeline.py` | Modified | Node result endpoint, template_id filter, action response |
| `app/api/v1/pipeline_templates.py` | Modified | Clone body, list envelope |
| `app/main.py` | Modified | Re-register stage config router |

### Frontend — Modified Files

| File | Type | Description |
|------|------|-------------|
| `src/types/index.ts` | Modified | Fix types, add new interfaces |
| `src/lib/api.ts` | Modified | Fix all API mismatches |
| `src/lib/queryClient.ts` | Modified | Add stageConfigs query keys |
| `src/hooks/useStageConfigs.ts` | Rewritten | Full hook rewrite |
| `src/hooks/useAgentConfigs.ts` | Modified | Grouped response type |
| `src/hooks/usePipeline.ts` | Modified | Fix types |
| `src/hooks/usePipelineTemplates.ts` | Modified | Fix clone/import/export |
| `src/components/admin/agents/AgentList.tsx` | Modified | Dynamic stages |
| `src/components/admin/agents/AgentGroupSection.tsx` | Modified | Dynamic props |
| `src/components/admin/agents/AgentCard.tsx` | Modified | Dynamic color |
| `src/components/admin/agents/AgentDialog.tsx` | Modified | Dynamic stage badge |
| `src/components/pipeline-builder/AgentCatalogSidebar.tsx` | Modified | Dynamic groups |
| `src/components/pipeline/PipelineProgress.tsx` | Modified | Remove hardcoded counts |
| `src/components/pipeline/StageResultsPanel.tsx` | Modified | Remove hardcoded stages |
| `src/components/pipeline/ResultsViewer.tsx` | Modified | Remove hardcoded comparisons |
| `src/components/pipelines/PipelineTemplateCard.tsx` | Modified | Fix clone params |
| `src/app/admin/layout.tsx` | Modified | Remove stages breadcrumb |

### Frontend — New Files

| File | Description |
|------|-------------|
| `src/components/admin/agents/ManageStagesDialog.tsx` | Stage management dialog |
| `src/components/admin/agents/StageRow.tsx` | Stage row component |
| `src/components/admin/agents/AddStageForm.tsx` | Add stage inline form |
| `src/components/admin/agents/StageIcon.tsx` | Dynamic icon renderer |

### Frontend — Deleted Files

| File | Reason |
|------|--------|
| `src/app/admin/stages/page.tsx` | Deprecated — stages managed in `/admin/agents` |
| `src/components/admin/stages/*` | Deprecated — replaced by new components |