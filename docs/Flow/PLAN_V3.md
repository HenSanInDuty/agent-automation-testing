# Auto-AT – Implementation Plan V3

> CrewAI Multi-Agent System + Full-Stack Web Application
> **V3 – Multi-Pipeline, DAG Agent Flow, Visual Drag-and-Drop Builder**

---

## Table of Contents

1. [V2 Recap – What Already Exists](#1-v2-recap--what-already-exists)
2. [V3 Requirements – New Features](#2-v3-requirements--new-features)
3. [Core Concept Changes (V2 → V3)](#3-core-concept-changes-v2--v3)
4. [Tech Stack Changes](#4-tech-stack-changes)
5. [System Architecture V3](#5-system-architecture-v3)
6. [Data Model – Pipeline Template & DAG](#6-data-model--pipeline-template--dag)
7. [Feature 1 – Multi-Pipeline Management](#7-feature-1--multi-pipeline-management)
8. [Feature 2 – DAG Agent Flow (Agent-to-Agent Wiring)](#8-feature-2--dag-agent-flow-agent-to-agent-wiring)
9. [Feature 3 – Visual Pipeline Builder (Drag-and-Drop)](#9-feature-3--visual-pipeline-builder-drag-and-drop)
10. [Feature 4 – DAG Pipeline Execution Engine](#10-feature-4--dag-pipeline-execution-engine)
11. [Feature 5 – Pipeline Template CRUD API](#11-feature-5--pipeline-template-crud-api)
12. [Feature 6 – Pipeline Builder Frontend](#12-feature-6--pipeline-builder-frontend)
13. [Updated Data Models](#13-updated-data-models)
14. [Updated API Endpoints](#14-updated-api-endpoints)
15. [Updated WebSocket Events](#15-updated-websocket-events)
16. [Updated Frontend Pages & Components](#16-updated-frontend-pages--components)
17. [Updated Database Schema (MongoDB)](#17-updated-database-schema-mongodb)
18. [Updated Environment Variables](#18-updated-environment-variables)
19. [Updated Folder Structure](#19-updated-folder-structure)
20. [Migration Guide (V2 → V3)](#20-migration-guide-v2--v3)
21. [Implementation Phases](#21-implementation-phases)
22. [Updated Dependencies](#22-updated-dependencies)

---

## 1. V2 Recap – What Already Exists

### Hệ thống hiện tại (đã hoàn thành trong V2)

| Layer | Đã triển khai |
|-------|--------------|
| **Backend** | FastAPI + Motor/Beanie/MongoDB + CrewAI dynamic pipeline |
| **Frontend** | Next.js 15 + React 19 + Tailwind CSS v4 + TanStack Query v5 |
| **Pipeline** | Dynamic stages (ordered, enabled/disabled) → mỗi stage có dynamic agents |
| **Real-time** | WebSocket progress streaming + persistent session (Zustand) |
| **Admin** | LLM Profile CRUD + Agent Config CRUD (create/delete custom) + Stage Config CRUD (reorder, enable/disable) |
| **Controls** | Pause / Resume / Cancel pipeline |
| **Export** | HTML + DOCX report download |
| **Chat** | SSE streaming chat with LLM profiles |
| **Docker** | docker-compose for backend + frontend + MongoDB |

### Các giới hạn của V2

| # | Giới hạn | Ảnh hưởng |
|---|----------|-----------|
| L1 | Chỉ có **1 pipeline duy nhất** — mọi run dùng chung cấu hình stages/agents | Không thể tạo các pipeline riêng biệt cho các mục đích khác nhau |
| L2 | Stages chạy **tuần tự** (sequential) — không hỗ trợ nhánh song song | Không tận dụng được concurrency, một stage chậm block cả pipeline |
| L3 | Agent nhận input từ **toàn bộ output stage trước** — không tùy chỉnh được input source | Không flexible cho flow phức tạp (vd: agent C cần output từ cả agent A và B) |
| L4 | Không có **visual builder** — cấu hình pipeline qua form/table | Khó hình dung flow, không trực quan |
| L5 | Stage grouping **cứng nhắc** — agents trong cùng stage chạy cùng crew | Không cho phép wiring chi tiết giữa agent-to-agent |

---

## 2. V3 Requirements – New Features

| # | Yêu cầu | Mô tả | Giải quyết |
|---|---------|-------|-----------|
| **F1** | Multi-Pipeline | Cho phép tạo **nhiều pipeline templates** — mỗi pipeline là một cấu hình riêng biệt | L1 |
| **F2** | DAG Agent Flow | Mỗi pipeline là một **DAG (Directed Acyclic Graph)** — agents là nodes, edges định nghĩa luồng dữ liệu. Cho phép tùy chỉnh agent nhận input từ agent nào | L2, L3, L5 |
| **F3** | Visual Pipeline Builder | Giao diện **kéo thả (drag-and-drop)** để xây dựng pipeline — kéo agents vào canvas, nối bằng edges | L4 |
| **F4** | Parallel Execution | Agents không phụ thuộc nhau chạy **song song** (DAG topological execution) | L2 |
| **F5** | Pipeline Templates | Pipelines có thể **clone**, **export/import** dưới dạng JSON | Tái sử dụng |

### Tương thích ngược

- **Giữ nguyên** tất cả features V2: LLM profiles, agent configs, export, pause/resume/cancel, chat
- **Stage concept được thay thế** bằng DAG nodes — V2 stages trở thành "Legacy Pipeline Template" (auto-migrated)
- V2 `stage_configs` collection **deprecated** — thay bằng `pipeline_templates` + nodes/edges bên trong

---

## 3. Core Concept Changes (V2 → V3)

### Mental Model Shift

```
V2 Model (Sequential Stages):
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ Stage 1  │───▶│ Stage 2  │───▶│ Stage 3  │───▶│ Stage 4  │
│ Agent A  │    │ Agent C  │    │ Agent F  │    │ Agent I  │
│ Agent B  │    │ Agent D  │    │ Agent G  │    │          │
│          │    │ Agent E  │    │ Agent H  │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
      ↓ (toàn bộ output) ↓ (toàn bộ output)  ↓ (toàn bộ output)

V3 Model (DAG Agent Flow):
                  ┌─────────┐
           ┌─────▶│ Agent C │──────┐
           │      └─────────┘      │
┌─────────┐│      ┌─────────┐      │    ┌─────────┐    ┌─────────┐
│ Agent A │├─────▶│ Agent D │──────┼───▶│ Agent F │───▶│ Agent H │
└─────────┘│      └─────────┘      │    └─────────┘    └─────────┘
           │      ┌─────────┐      │    ┌─────────┐
           └─────▶│ Agent E │──────┘ ┌─▶│ Agent G │──────┐
                  └─────────┘        │  └─────────┘      │
┌─────────┐                          │                    ▼
│ Agent B │──────────────────────────┘              ┌─────────┐
└─────────┘                                        │ Agent I │
                                                   └─────────┘
```

### Thuật ngữ mới

| Thuật ngữ | V2 tương đương | V3 Mô tả |
|-----------|---------------|-----------|
| **Pipeline Template** | _(1 global pipeline)_ | Bản thiết kế pipeline — có tên, mô tả, chứa nodes + edges |
| **Pipeline Node** | Stage + Agent | Một agent instance đặt trên canvas, có vị trí (x,y) |
| **Pipeline Edge** | _(implicit: stage order)_ | Kết nối giữa 2 nodes, định nghĩa dataflow (output A → input B) |
| **Source Node** | _(không có)_ | Node đặc biệt: **Input** — điểm bắt đầu pipeline (file upload, etc.) |
| **Sink Node** | _(không có)_ | Node đặc biệt: **Output** — điểm kết thúc pipeline (final result) |
| **Agent Catalog** | Agent Configs | Danh sách agents có sẵn để kéo vào pipeline |
| **Pipeline Run** | Pipeline Run | Một lần chạy cụ thể của một Pipeline Template |
| **Execution Layer** | _(trong DAG)_ | Nhóm nodes cùng depth level — chạy song song |

### Ví dụ: Pipeline "Auto Testing" (V2 migrated)

```
                    ┌───────────────────┐
                    │ 📥 INPUT          │   ← Source Node
                    │ (file upload)     │
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │ Ingestion Agent   │   ← Node (pure_python type)
                    │ (parse document)  │
                    └────────┬──────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼────┐  ┌─────▼──────┐  ┌───▼──────────┐
     │ TC Analyzer │  │ TC Writer  │  │ TC Reviewer  │   ← 3 nodes song song
     └────────┬────┘  └─────┬──────┘  └───┬──────────┘
              │              │              │
              └──────────────┼──────────────┘
                             │
                    ┌────────▼──────────┐
                    │ Test Executor     │
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │ Report Generator  │
                    └────────┬──────────┘
                             │
                    ┌────────▼──────────┐
                    │ 📤 OUTPUT         │   ← Sink Node
                    └───────────────────┘
```

---

## 4. Tech Stack Changes

### Backend – Thay đổi so với V2

| Thành phần | V2 | V3 | Lý do |
|---|---|---|---|
| Pipeline runner | `PipelineRunnerV2` (sequential stage loop) | **`DAGPipelineRunner`** (topological sort + parallel exec) | Hỗ trợ DAG execution, parallel branches |
| DAG validation | _(không có)_ | **`networkx`** hoặc custom topo-sort | Validate DAG (no cycles), compute execution layers |
| Stage configs | `stage_configs` collection | **Deprecated** → merged into `pipeline_templates` | Nodes/Edges thay thế stages |
| Execution | Sequential `for stage in stages` | **`asyncio.gather`** per execution layer | Song song cho independent nodes |

### Frontend – Thay đổi so với V2

| Thành phần | V2 | V3 | Lý do |
|---|---|---|---|
| Pipeline builder | Form-based stage config | **React Flow** (`@xyflow/react`) visual builder | Kéo thả trực quan, DAG visualization |
| Agent palette | Admin table | **Sidebar catalog** — kéo agent vào canvas | UX tốt hơn |
| Stage admin | `/admin/stages` page | **Removed** — thay bằng Pipeline Builder | Stages không còn là concept riêng |
| Pipeline list | _(1 global pipeline)_ | **Pipeline list page** `/pipelines` — CRUD templates | Multi-pipeline |
| DnD library | `@dnd-kit/*` (list reorder) | **`@xyflow/react`** (canvas-based node graph) | Full DAG builder, không chỉ list reorder |

---

## 5. System Architecture V3

```
┌────────────────────────────────────────────────────────────────────────┐
│                     🖥️ Frontend (Next.js 15)                          │
│                                                                        │
│  ┌─────────────┐  ┌─────────────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Pipeline    │  │ Pipeline Builder │  │ Admin     │  │ Chat      │  │
│  │ List        │  │ (React Flow)    │  │ LLM/Agent │  │ Page      │  │
│  │ /pipelines  │  │ /pipelines/:id  │  │ /admin/*  │  │ /chat     │  │
│  └──────┬──────┘  └───────┬─────────┘  └─────┬─────┘  └─────┬─────┘  │
│         │                 │                   │              │         │
│  ┌──────┴─────────────────┴───────────────────┴──────────────┴──────┐  │
│  │                    Zustand Stores + React Query                  │  │
│  │  pipelineStore  │  builderStore  │  catalogStore                │  │
│  └──────────────────────────┬──────────────────────────────────────┘  │
│                             │                                         │
│  ┌──────────────────────────┴──────────────────────────────────────┐  │
│  │              WebSocket Manager (singleton)                      │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │ REST + WS
┌─────────────────────────────────┴──────────────────────────────────────┐
│                     ⚙️ Backend (FastAPI)                               │
│                                                                        │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐    │
│  │ REST API     │  │ WebSocket     │  │ Export Service            │    │
│  │ /api/v1/*    │  │ /ws/run/:id   │  │ HTML / DOCX              │    │
│  └──────┬───────┘  └───────┬───────┘  └──────────┬───────────────┘    │
│         │                  │                      │                    │
│  ┌──────┴──────────────────┴──────────────────────┴────────────────┐  │
│  │                  DAG Pipeline Runner                             │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐ │  │
│  │  │ DAG Resolver│  │ Layer Exec   │  │ Signal Manager         │ │  │
│  │  │ (topo sort) │  │ (parallel)   │  │ (pause/resume/cancel)  │ │  │
│  │  └─────────────┘  └──────────────┘  └────────────────────────┘ │  │
│  └──────┬──────────────────────────────────────────────────────────┘  │
│         │                                                              │
│  ┌──────┴──────────────────────────────────────────────────────────┐  │
│  │  Agent Factory + LLM Factory (LiteLLM)                          │  │
│  └─────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────┬──────────────────────────────────────┘
                                  │
┌─────────────────────────────────┴──────────────────────────────────────┐
│                     🗄️ MongoDB                                        │
│                                                                        │
│  ┌───────────────┐  ┌───────────────┐  ┌────────────────────────────┐ │
│  │ llm_profiles  │  │ agent_configs │  │ pipeline_templates         │ │
│  └───────────────┘  └───────────────┘  │  (nodes + edges embedded) │ │
│                                        └────────────────────────────┘ │
│  ┌───────────────┐  ┌───────────────┐                                 │
│  │ pipeline_runs │  │ pipeline_     │                                 │
│  │               │  │ results       │                                 │
│  └───────────────┘  └───────────────┘                                 │
└────────────────────────────────────────────────────────────────────────┘
```

### Pipeline Execution Flow V3 (DAG)

```
┌────────────────────────────────────────────────┐
│  Pipeline Template  (loaded from MongoDB)       │
│  nodes: [A, B, C, D, E, F]                     │
│  edges: [A→C, A→D, B→D, C→E, D→E, D→F]       │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────┐
│  DAG Resolver (Topological Sort)               │
│                                                │
│  Layer 0: [INPUT]        ← source node         │
│  Layer 1: [A, B]         ← no deps, run ∥     │
│  Layer 2: [C, D]         ← deps resolved       │
│  Layer 3: [E, F]         ← deps resolved       │
│  Layer 4: [OUTPUT]       ← sink node           │
└────────────────────┬───────────────────────────┘
                     │
                     ▼
┌────────────────────────────────────────────────┐
│  Layer Executor                                │
│                                                │
│  for layer in layers:                          │
│    ┌──────────────────────────────────┐        │
│    │ CHECK SIGNAL (pause/cancel)      │        │
│    └──────────────┬───────────────────┘        │
│                   │                            │
│    ┌──────────────▼───────────────────┐        │
│    │ asyncio.gather(                  │        │
│    │   run_node(A, inputs={...}),     │        │
│    │   run_node(B, inputs={...}),     │        │
│    │ )                                │        │
│    │ ← parallel execution per layer   │        │
│    └──────────────┬───────────────────┘        │
│                   │                            │
│    ┌──────────────▼───────────────────┐        │
│    │ Store outputs → feed to next     │        │
│    │ layer as inputs via edges        │        │
│    └──────────────────────────────────┘        │
│                                                │
└────────────────────────────────────────────────┘
```

---

## 6. Data Model – Pipeline Template & DAG

### 6.1 Pipeline Template Document

```python
# db/models.py — NEW

class NodeType(str, Enum):
    """Types of nodes in a pipeline DAG."""
    INPUT = "input"          # Source node — pipeline entry point
    OUTPUT = "output"        # Sink node — pipeline final output
    AGENT = "agent"          # CrewAI agent node
    PURE_PYTHON = "pure_python"  # Non-LLM processing node (e.g., ingestion)


class PipelineNodeConfig(BaseModel):
    """A single node in the pipeline DAG (embedded in PipelineTemplate)."""
    node_id: str = Field(
        ...,
        pattern=r'^[a-z][a-z0-9_-]{2,49}$',
        description="Unique within this pipeline template"
    )
    node_type: NodeType = NodeType.AGENT
    agent_id: Optional[str] = Field(
        None,
        description="Reference to agent_configs.agent_id. Required for AGENT/PURE_PYTHON types."
    )
    label: str = Field(..., min_length=1, max_length=200, description="Display name on canvas")
    description: str = ""

    # ── Visual position on canvas ──
    position_x: float = 0.0
    position_y: float = 0.0

    # ── Execution config ──
    timeout_seconds: int = Field(default=300, ge=10, le=7200)
    retry_count: int = Field(default=0, ge=0, le=5)
    enabled: bool = True

    # ── Custom data (agent overrides, etc.) ──
    config_overrides: dict = Field(
        default_factory=dict,
        description="Override agent config fields: llm_profile_id, max_iter, etc."
    )


class PipelineEdgeConfig(BaseModel):
    """A directed edge connecting two nodes (embedded in PipelineTemplate)."""
    edge_id: str = Field(..., description="Unique within this pipeline")
    source_node_id: str = Field(..., description="Output from this node")
    target_node_id: str = Field(..., description="Input to this node")
    source_handle: Optional[str] = Field(
        None,
        description="Named output port (for agents with multiple outputs). Default: 'default'"
    )
    target_handle: Optional[str] = Field(
        None,
        description="Named input port. Default: 'default'"
    )
    label: Optional[str] = Field(None, description="Optional label on the edge")
    animated: bool = False  # Visual — animated edge on canvas


class PipelineTemplateDocument(Document):
    """
    A reusable pipeline definition containing a DAG of agent nodes and edges.
    Each template can be run multiple times.
    """
    template_id: str = Field(
        ...,
        pattern=r'^[a-z][a-z0-9_-]{2,49}$',
        description="Unique identifier, URL-safe"
    )
    name: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    version: int = Field(default=1, description="Auto-incremented on each save")

    # ── DAG Definition ──
    nodes: list[PipelineNodeConfig] = Field(default_factory=list)
    edges: list[PipelineEdgeConfig] = Field(default_factory=list)

    # ── Metadata ──
    is_builtin: bool = False
    is_archived: bool = False
    tags: list[str] = Field(default_factory=list)
    thumbnail: Optional[str] = None  # Base64 or URL — auto-generated from canvas

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "pipeline_templates"
        indexes = [
            IndexModel([("template_id", 1)], unique=True),
            IndexModel([("is_archived", 1)]),
            IndexModel([("tags", 1)]),
            IndexModel([("created_at", -1)]),
        ]
```

### 6.2 Updated Pipeline Run Document

```python
# db/models.py — UPDATED

class PipelineRunDocument(Document):
    """
    A single execution of a pipeline template.
    V3: Now references a template_id instead of running the global pipeline.
    """
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    template_id: str = Field(..., description="Which pipeline template to run")
    template_snapshot: Optional[dict] = Field(
        None,
        description="Snapshot of template at run time (nodes + edges) for reproducibility"
    )

    # ── Run config ──
    document_name: str = ""
    file_path: Optional[str] = None
    llm_profile_id: Optional[str] = None
    run_params: dict = Field(default_factory=dict, description="Extra params passed at run time")

    # ── Status ──
    status: str = "pending"  # pending | running | paused | completed | failed | cancelled
    current_node: Optional[str] = None
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    node_statuses: dict[str, str] = Field(
        default_factory=dict,
        description="{ node_id: 'pending'|'running'|'completed'|'failed'|'skipped' }"
    )

    # ── Timing ──
    created_at: datetime = Field(default_factory=_now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None

    # ── Results summary ──
    execution_layers: list[list[str]] = Field(
        default_factory=list,
        description="Computed DAG layers: [[nodeA, nodeB], [nodeC], ...]"
    )
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None

    class Settings:
        name = "pipeline_runs"
        indexes = [
            IndexModel([("run_id", 1)], unique=True),
            IndexModel([("template_id", 1)]),
            IndexModel([("status", 1)]),
            IndexModel([("created_at", -1)]),
        ]
```

### 6.3 Updated Pipeline Result Document

```python
# db/models.py — UPDATED

class PipelineResultDocument(Document):
    """
    Output from a single node execution within a pipeline run.
    V3: result_type now includes 'node_output' and references node_id.
    """
    run_id: str
    node_id: str = Field(..., description="Which node produced this result")
    agent_id: Optional[str] = Field(None, description="Which agent config was used (if AGENT type)")
    result_type: str = "node_output"  # node_output | error | metadata
    output: dict = Field(default_factory=dict)
    input_data: dict = Field(
        default_factory=dict,
        description="What input this node received (for debugging/replay)"
    )

    # ── Timing ──
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None

    # ── Status ──
    status: str = "completed"  # completed | failed | skipped
    error_message: Optional[str] = None

    created_at: datetime = Field(default_factory=_now)

    class Settings:
        name = "pipeline_results"
        indexes = [
            IndexModel([("run_id", 1), ("node_id", 1)]),
            IndexModel([("run_id", 1)]),
        ]
```

---

## 7. Feature 1 – Multi-Pipeline Management

### Mục tiêu

Cho phép user tạo, quản lý, clone, archive nhiều pipeline templates. Mỗi pipeline là một cấu hình riêng biệt với bộ nodes/edges riêng.

### Pipeline Template Lifecycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│  Create  │────▶│  Edit    │────▶│  Run     │────▶│ Archive  │
│  (empty  │     │  (add    │     │  (exec   │     │ (soft    │
│   or     │     │   nodes, │     │   DAG)   │     │  delete) │
│  clone)  │     │   edges) │     │          │     │          │
└──────────┘     └──────────┘     └──────────┘     └──────────┘
                      │
                      ├───▶ Clone (tạo bản copy)
                      │
                      └───▶ Export (JSON download)
```

### Pipeline List Page (`/pipelines`)

```
┌──────────────────────────────────────────────────────────────────────┐
│  🔧 Pipelines                                    [+ New Pipeline]   │
│                                                                      │
│  ┌──────────────────────┐  ┌──────────────────────┐                 │
│  │ 📋 Auto Testing      │  │ 📋 API Validation    │                 │
│  │ 6 agents · 7 edges   │  │ 4 agents · 4 edges   │                 │
│  │ Last run: 2h ago ✅  │  │ Last run: never       │                 │
│  │                      │  │                      │                 │
│  │ [Edit] [Run] [···]   │  │ [Edit] [Run] [···]   │                 │
│  └──────────────────────┘  └──────────────────────┘                 │
│                                                                      │
│  ┌──────────────────────┐  ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐                │
│  │ 📋 Security Scan     │    + Create Pipeline                      │
│  │ 3 agents · 3 edges   │  │ Start from scratch   │                │
│  │ Last run: 1d ago ❌  │    or clone existing                      │
│  │                      │  └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘                │
│  │ [Edit] [Run] [···]   │                                           │
│  └──────────────────────┘                                           │
└──────────────────────────────────────────────────────────────────────┘
```

### Pipeline CRUD Operations

| Operation | Mô tả |
|-----------|-------|
| **Create** | Tạo pipeline mới (trống hoặc từ preset) |
| **Clone** | Tạo bản copy từ pipeline hiện có (deepcopy nodes + edges, new template_id) |
| **Edit** | Mở Visual Builder → thêm/xoá/di chuyển nodes, vẽ edges |
| **Run** | Chạy pipeline template → tạo PipelineRun mới |
| **Archive** | Soft-delete (is_archived=true) — giữ lại history |
| **Delete** | Hard delete (chỉ khi chưa có runs) |
| **Export** | Download pipeline template dưới dạng JSON |
| **Import** | Upload JSON → tạo pipeline template mới |

---

## 8. Feature 2 – DAG Agent Flow (Agent-to-Agent Wiring)

### Mục tiêu

Cho phép user tùy chỉnh **chính xác** agent nào nhận input từ agent nào. Mỗi pipeline là một DAG — không cho phép cycles.

### DAG Rules

| Rule | Mô tả |
|------|-------|
| **Acyclic** | Không cho phép cycles (A→B→C→A). Backend validate trước khi save. |
| **Single INPUT** | Mỗi pipeline có đúng 1 Input node (source) |
| **Single OUTPUT** | Mỗi pipeline có đúng 1 Output node (sink) |
| **Connected** | Mọi node phải reachable từ INPUT và reach được OUTPUT (warning nếu orphan) |
| **Multi-input** | Một node có thể nhận input từ **nhiều** nodes — outputs được merge |
| **Multi-output** | Một node có thể gửi output tới **nhiều** nodes — output được broadcast |

### Input Merging Strategy

Khi một node nhận input từ nhiều parent nodes, outputs được merge:

```python
# Merge strategy cho multi-input nodes

def merge_inputs(parent_outputs: dict[str, dict]) -> dict:
    """
    Merge outputs from multiple parent nodes into a single input dict.

    Args:
        parent_outputs: { parent_node_id: output_dict }

    Returns:
        Merged input dict for the current node.
    """
    merged = {}
    for parent_id, output in parent_outputs.items():
        # Namespace by parent node_id to avoid key collisions
        merged[parent_id] = output

    # Also provide a flat merge for convenience
    merged["__flat__"] = {}
    for output in parent_outputs.values():
        if isinstance(output, dict):
            merged["__flat__"].update(output)

    return merged
```

### Edge Handles (Advanced)

Mỗi node có thể có **named handles** (ports) để phân biệt different outputs:

```
┌──────────────────┐
│   TC Analyzer    │
│                  │
│  ○ test_cases    │──→  (connects to specific input of next node)
│  ○ coverage      │──→
│  ○ gaps          │──→
└──────────────────┘
```

Default: mỗi node có 1 output handle ("default") và 1 input handle ("default").
Advanced users có thể define custom handles trong `config_overrides`.

### DAG Validation (Backend)

```python
# core/dag_resolver.py — NEW

from collections import deque
from typing import Optional


class DAGValidationError(Exception):
    """Raised when pipeline DAG is invalid."""
    pass


class DAGResolver:
    """
    Validates and resolves execution order for a pipeline DAG.
    Uses Kahn's algorithm for topological sort.
    """

    def __init__(self, nodes: list[PipelineNodeConfig], edges: list[PipelineEdgeConfig]):
        self.nodes = {n.node_id: n for n in nodes}
        self.edges = edges
        self._adj: dict[str, list[str]] = {n.node_id: [] for n in nodes}
        self._in_degree: dict[str, int] = {n.node_id: 0 for n in nodes}

        for edge in edges:
            self._adj[edge.source_node_id].append(edge.target_node_id)
            self._in_degree[edge.target_node_id] += 1

    def validate(self) -> list[str]:
        """
        Validate the DAG and return topological order.
        Raises DAGValidationError if invalid.
        """
        errors = []

        # 1. Check INPUT node exists (exactly 1)
        input_nodes = [n for n in self.nodes.values() if n.node_type == NodeType.INPUT]
        if len(input_nodes) != 1:
            errors.append(f"Pipeline must have exactly 1 INPUT node, found {len(input_nodes)}")

        # 2. Check OUTPUT node exists (exactly 1)
        output_nodes = [n for n in self.nodes.values() if n.node_type == NodeType.OUTPUT]
        if len(output_nodes) != 1:
            errors.append(f"Pipeline must have exactly 1 OUTPUT node, found {len(output_nodes)}")

        # 3. Check all edge references exist
        for edge in self.edges:
            if edge.source_node_id not in self.nodes:
                errors.append(f"Edge source '{edge.source_node_id}' not found in nodes")
            if edge.target_node_id not in self.nodes:
                errors.append(f"Edge target '{edge.target_node_id}' not found in nodes")

        # 4. Check for cycles using Kahn's algorithm
        topo_order = self._topological_sort()
        if topo_order is None:
            errors.append("Pipeline contains a cycle — DAG must be acyclic")

        # 5. Check connectivity (all nodes reachable from INPUT)
        if input_nodes and topo_order:
            reachable = self._bfs(input_nodes[0].node_id)
            unreachable = set(self.nodes.keys()) - reachable
            enabled_unreachable = [
                nid for nid in unreachable
                if self.nodes[nid].enabled
            ]
            if enabled_unreachable:
                errors.append(
                    f"Orphan nodes not reachable from INPUT: {enabled_unreachable}"
                )

        if errors:
            raise DAGValidationError("; ".join(errors))

        return topo_order

    def get_execution_layers(self) -> list[list[str]]:
        """
        Group nodes into execution layers.
        Nodes in the same layer have no dependencies on each other → can run in parallel.

        Returns:
            List of layers, each layer is a list of node_ids.
            Example: [["input"], ["agent_a", "agent_b"], ["agent_c"], ["output"]]
        """
        topo_order = self.validate()

        # Compute depth (longest path from root) for each node
        depth: dict[str, int] = {}
        for node_id in topo_order:
            if self._in_degree[node_id] == 0:
                depth[node_id] = 0
            else:
                # depth = max(depth of parents) + 1
                parents = [
                    e.source_node_id for e in self.edges
                    if e.target_node_id == node_id
                ]
                depth[node_id] = max(depth.get(p, 0) for p in parents) + 1

        # Group by depth
        max_depth = max(depth.values()) if depth else 0
        layers: list[list[str]] = [[] for _ in range(max_depth + 1)]
        for node_id, d in depth.items():
            if self.nodes[node_id].enabled:
                layers[d].append(node_id)

        # Filter out empty layers
        return [layer for layer in layers if layer]

    def get_node_parents(self, node_id: str) -> list[str]:
        """Get direct parent node_ids for a given node."""
        return [
            e.source_node_id for e in self.edges
            if e.target_node_id == node_id
        ]

    def get_node_children(self, node_id: str) -> list[str]:
        """Get direct child node_ids for a given node."""
        return self._adj.get(node_id, [])

    def _topological_sort(self) -> Optional[list[str]]:
        """Kahn's algorithm. Returns None if cycle detected."""
        in_degree = dict(self._in_degree)
        queue = deque([n for n, d in in_degree.items() if d == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)
            for child in self._adj[node]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        if len(order) != len(self.nodes):
            return None  # Cycle detected

        return order

    def _bfs(self, start: str) -> set[str]:
        """BFS from start node, return all reachable node_ids."""
        visited = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for child in self._adj.get(node, []):
                if child not in visited:
                    visited.add(child)
                    queue.append(child)
        return visited
```

---

## 9. Feature 3 – Visual Pipeline Builder (Drag-and-Drop)

### Mục tiêu

Giao diện **kéo thả trực quan** để xây dựng pipeline:
- Kéo agents từ catalog vào canvas
- Nối agents bằng edges (kéo từ output handle tới input handle)
- Di chuyển, xoá, config từng node
- Xem realtime validation (cycles, orphans)

### Technology: React Flow (`@xyflow/react`)

| Tính năng | React Flow support |
|-----------|-------------------|
| Node drag-and-drop | ✅ Built-in |
| Edge creation (drag handle) | ✅ Built-in |
| Custom node types | ✅ nodeTypes prop |
| Minimap | ✅ `<MiniMap />` |
| Controls (zoom, fit) | ✅ `<Controls />` |
| Background grid | ✅ `<Background />` |
| Undo/Redo | ✅ via state management |
| Export to image | ✅ `toObject()` |
| Validation markers | ✅ Custom via node styling |
| Responsive | ✅ |

### Builder Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Pipeline: "Auto Testing" v3                   [💾 Save] [▶ Run] [⋯ More]  │
├───────────────────┬──────────────────────────────────────────────────────────┤
│                   │                                                          │
│  📂 Agent Catalog │            Canvas (React Flow)                           │
│                   │                                                          │
│  ┌─────────────┐  │     ┌───────┐         ┌──────────┐                      │
│  │ 🔍 Search   │  │     │ INPUT │────────▶│ Ingest   │                      │
│  └─────────────┘  │     └───────┘         │ Agent    │                      │
│                   │                        └────┬─────┘                      │
│  ▼ Ingestion      │                             │                            │
│    □ Doc Parser   │               ┌─────────────┼─────────────┐              │
│                   │               │             │             │              │
│  ▼ Test Cases     │         ┌─────▼───┐   ┌────▼────┐  ┌────▼────┐         │
│    □ TC Analyzer  │         │ TC      │   │ TC      │  │ TC      │         │
│    □ TC Writer    │         │ Analyzer│   │ Writer  │  │ Reviewer│         │
│    □ TC Reviewer  │         └─────┬───┘   └────┬────┘  └────┬────┘         │
│    □ TC Optimizer │               │             │             │              │
│                   │               └─────────────┼─────────────┘              │
│  ▼ Execution      │                             │                            │
│    □ Test Runner  │                        ┌────▼────┐                       │
│    □ API Tester   │                        │ Executor│                       │
│                   │                        └────┬────┘                       │
│  ▼ Reporting      │                             │                            │
│    □ Reporter     │                        ┌────▼────┐                       │
│    □ Analyzer     │                        │ Reporter│                       │
│                   │                        └────┬────┘                       │
│  ▼ Custom         │                             │                            │
│    □ My Agent 1   │                        ┌────▼────┐                       │
│    □ My Agent 2   │                        │ OUTPUT  │                       │
│                   │                        └─────────┘                       │
│                   │                                                          │
│  [+ New Agent]    │  ┌──────────┐  ┌──────────┐  ┌─────────────────┐        │
│                   │  │ MiniMap  │  │ Controls │  │ Validation: ✅  │        │
│                   │  └──────────┘  └──────────┘  └─────────────────┘        │
├───────────────────┴──────────────────────────────────────────────────────────┤
│  Properties Panel (when node selected)                                       │
│  ┌──────────────────────────────────────────────────────────────────────────┐│
│  │ Node: TC Analyzer  │  Agent: tc_analyzer  │  Timeout: 300s  │ ☑ Enabled ││
│  │ LLM Override: [Default ▼]  │  Max Iter: [5]  │  [Delete Node]           ││
│  └──────────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────────┘
```

### Drag from Catalog to Canvas

```
User Action:
1. Từ sidebar Agent Catalog, kéo agent "TC Analyzer" vào canvas
2. Drop tại vị trí (x=400, y=200)
3. System tự tạo PipelineNodeConfig:
   {
     node_id: "tc_analyzer_1",        // auto-generated: agent_id + "_" + counter
     node_type: "agent",
     agent_id: "tc_analyzer",          // references agent_configs
     label: "TC Analyzer",
     position_x: 400,
     position_y: 200,
     timeout_seconds: 300,
     enabled: true
   }
4. Node xuất hiện trên canvas với input/output handles
5. User kéo edge từ "Ingest Agent" output handle → "TC Analyzer" input handle
6. System tạo PipelineEdgeConfig:
   {
     edge_id: "edge_ingest-tc_analyzer_1",
     source_node_id: "ingest_agent_1",
     target_node_id: "tc_analyzer_1"
   }
```

### Custom Node Component

```tsx
// components/pipeline-builder/nodes/AgentNode.tsx

import { Handle, Position, NodeProps } from '@xyflow/react';

interface AgentNodeData {
    label: string;
    agentId: string;
    nodeType: 'agent' | 'pure_python' | 'input' | 'output';
    status?: 'idle' | 'running' | 'completed' | 'failed';
    enabled: boolean;
    description?: string;
}

export function AgentNode({ data, selected }: NodeProps<AgentNodeData>) {
    const statusColors = {
        idle: 'border-zinc-600',
        running: 'border-blue-500 animate-pulse',
        completed: 'border-green-500',
        failed: 'border-red-500',
    };

    const nodeIcons = {
        input: '📥',
        output: '📤',
        agent: '🤖',
        pure_python: '🐍',
    };

    return (
        <div
            className={`
                px-4 py-3 rounded-xl border-2 bg-zinc-900 shadow-lg
                min-w-[160px] transition-all
                ${statusColors[data.status || 'idle']}
                ${selected ? 'ring-2 ring-blue-400' : ''}
                ${!data.enabled ? 'opacity-50' : ''}
            `}
        >
            {/* Input Handle */}
            {data.nodeType !== 'input' && (
                <Handle
                    type="target"
                    position={Position.Top}
                    className="w-3 h-3 bg-blue-500 border-2 border-zinc-800"
                />
            )}

            {/* Node Content */}
            <div className="flex items-center gap-2">
                <span className="text-lg">{nodeIcons[data.nodeType]}</span>
                <div>
                    <div className="font-medium text-sm text-zinc-100">
                        {data.label}
                    </div>
                    {data.description && (
                        <div className="text-xs text-zinc-400 mt-0.5 max-w-[140px] truncate">
                            {data.description}
                        </div>
                    )}
                </div>
            </div>

            {/* Status indicator */}
            {data.status === 'running' && (
                <div className="mt-2 h-1 bg-zinc-700 rounded-full overflow-hidden">
                    <div className="h-full bg-blue-500 animate-progress rounded-full" />
                </div>
            )}

            {/* Output Handle */}
            {data.nodeType !== 'output' && (
                <Handle
                    type="source"
                    position={Position.Bottom}
                    className="w-3 h-3 bg-green-500 border-2 border-zinc-800"
                />
            )}
        </div>
    );
}
```

### Builder Store (Zustand)

```typescript
// store/builderStore.ts

import { create } from 'zustand';
import {
    type Node,
    type Edge,
    type OnNodesChange,
    type OnEdgesChange,
    type OnConnect,
    applyNodeChanges,
    applyEdgeChanges,
    addEdge,
} from '@xyflow/react';

interface BuilderState {
    // ── Template metadata ──
    templateId: string | null;
    templateName: string;
    templateDescription: string;

    // ── React Flow state ──
    nodes: Node[];
    edges: Edge[];

    // ── Selection ──
    selectedNodeId: string | null;

    // ── Dirty state ──
    isDirty: boolean;
    isSaving: boolean;

    // ── Validation ──
    validationErrors: string[];
    isValid: boolean;

    // ── Undo/Redo ──
    history: { nodes: Node[]; edges: Edge[] }[];
    historyIndex: number;

    // ── Actions ──
    onNodesChange: OnNodesChange;
    onEdgesChange: OnEdgesChange;
    onConnect: OnConnect;

    setTemplate: (templateId: string, name: string, description: string, nodes: Node[], edges: Edge[]) => void;
    addNode: (node: Node) => void;
    removeNode: (nodeId: string) => void;
    updateNodeData: (nodeId: string, data: Partial<AgentNodeData>) => void;
    selectNode: (nodeId: string | null) => void;

    validate: () => string[];
    saveTemplate: () => Promise<void>;

    undo: () => void;
    redo: () => void;
    pushHistory: () => void;

    resetBuilder: () => void;
}

export const useBuilderStore = create<BuilderState>((set, get) => ({
    templateId: null,
    templateName: '',
    templateDescription: '',
    nodes: [],
    edges: [],
    selectedNodeId: null,
    isDirty: false,
    isSaving: false,
    validationErrors: [],
    isValid: true,
    history: [],
    historyIndex: -1,

    onNodesChange: (changes) => {
        set({
            nodes: applyNodeChanges(changes, get().nodes),
            isDirty: true,
        });
    },

    onEdgesChange: (changes) => {
        set({
            edges: applyEdgeChanges(changes, get().edges),
            isDirty: true,
        });
    },

    onConnect: (connection) => {
        const newEdges = addEdge(
            {
                ...connection,
                id: `edge-${connection.source}-${connection.target}`,
                animated: false,
                type: 'smoothstep',
            },
            get().edges,
        );
        set({ edges: newEdges, isDirty: true });

        // Auto-validate after connection
        get().validate();
    },

    setTemplate: (templateId, name, description, nodes, edges) => {
        set({
            templateId,
            templateName: name,
            templateDescription: description,
            nodes,
            edges,
            isDirty: false,
            history: [{ nodes, edges }],
            historyIndex: 0,
        });
        get().validate();
    },

    addNode: (node) => {
        get().pushHistory();
        set({
            nodes: [...get().nodes, node],
            isDirty: true,
        });
    },

    removeNode: (nodeId) => {
        get().pushHistory();
        set({
            nodes: get().nodes.filter((n) => n.id !== nodeId),
            edges: get().edges.filter(
                (e) => e.source !== nodeId && e.target !== nodeId,
            ),
            selectedNodeId:
                get().selectedNodeId === nodeId ? null : get().selectedNodeId,
            isDirty: true,
        });
        get().validate();
    },

    updateNodeData: (nodeId, data) => {
        set({
            nodes: get().nodes.map((n) =>
                n.id === nodeId ? { ...n, data: { ...n.data, ...data } } : n,
            ),
            isDirty: true,
        });
    },

    selectNode: (nodeId) => {
        set({ selectedNodeId: nodeId });
    },

    validate: () => {
        const { nodes, edges } = get();
        const errors: string[] = [];

        // Check INPUT node
        const inputNodes = nodes.filter((n) => n.data?.nodeType === 'input');
        if (inputNodes.length !== 1) {
            errors.push(`Pipeline must have exactly 1 INPUT node (found ${inputNodes.length})`);
        }

        // Check OUTPUT node
        const outputNodes = nodes.filter((n) => n.data?.nodeType === 'output');
        if (outputNodes.length !== 1) {
            errors.push(`Pipeline must have exactly 1 OUTPUT node (found ${outputNodes.length})`);
        }

        // Check for cycles (simplified client-side check)
        const hasCycle = detectCycle(nodes, edges);
        if (hasCycle) {
            errors.push('Pipeline contains a cycle — connections must be acyclic');
        }

        // Check orphan nodes (no edges at all)
        const connectedNodeIds = new Set<string>();
        edges.forEach((e) => {
            connectedNodeIds.add(e.source);
            connectedNodeIds.add(e.target);
        });
        const orphans = nodes.filter(
            (n) => !connectedNodeIds.has(n.id) && n.data?.nodeType === 'agent',
        );
        if (orphans.length > 0) {
            errors.push(
                `Disconnected agents: ${orphans.map((n) => n.data?.label).join(', ')}`,
            );
        }

        set({ validationErrors: errors, isValid: errors.length === 0 });
        return errors;
    },

    saveTemplate: async () => {
        // Implementation: POST/PUT to API
        // See Feature 5 — Pipeline Template CRUD API
    },

    pushHistory: () => {
        const { nodes, edges, history, historyIndex } = get();
        const newHistory = history.slice(0, historyIndex + 1);
        newHistory.push({ nodes: structuredClone(nodes), edges: structuredClone(edges) });
        set({ history: newHistory, historyIndex: newHistory.length - 1 });
    },

    undo: () => {
        const { history, historyIndex } = get();
        if (historyIndex > 0) {
            const prev = history[historyIndex - 1];
            set({
                nodes: structuredClone(prev.nodes),
                edges: structuredClone(prev.edges),
                historyIndex: historyIndex - 1,
                isDirty: true,
            });
        }
    },

    redo: () => {
        const { history, historyIndex } = get();
        if (historyIndex < history.length - 1) {
            const next = history[historyIndex + 1];
            set({
                nodes: structuredClone(next.nodes),
                edges: structuredClone(next.edges),
                historyIndex: historyIndex + 1,
                isDirty: true,
            });
        }
    },

    resetBuilder: () => {
        set({
            templateId: null,
            templateName: '',
            templateDescription: '',
            nodes: [],
            edges: [],
            selectedNodeId: null,
            isDirty: false,
            validationErrors: [],
            isValid: true,
            history: [],
            historyIndex: -1,
        });
    },
}));


// ── Utility: Cycle detection (DFS-based) ──

function detectCycle(nodes: Node[], edges: Edge[]): boolean {
    const adj: Record<string, string[]> = {};
    nodes.forEach((n) => { adj[n.id] = []; });
    edges.forEach((e) => { adj[e.source]?.push(e.target); });

    const visited = new Set<string>();
    const recStack = new Set<string>();

    function dfs(nodeId: string): boolean {
        visited.add(nodeId);
        recStack.add(nodeId);

        for (const child of (adj[nodeId] || [])) {
            if (!visited.has(child)) {
                if (dfs(child)) return true;
            } else if (recStack.has(child)) {
                return true; // cycle!
            }
        }

        recStack.delete(nodeId);
        return false;
    }

    for (const node of nodes) {
        if (!visited.has(node.id)) {
            if (dfs(node.id)) return true;
        }
    }

    return false;
}
```

---

## 10. Feature 4 – DAG Pipeline Execution Engine

### Mục tiêu

Thay thế `PipelineRunnerV2` (sequential stage loop) bằng `DAGPipelineRunner` — thực thi pipeline theo DAG topology, song song cho các nodes cùng layer.

### DAGPipelineRunner

```python
# core/dag_pipeline_runner.py — NEW

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.core.agent_factory import AgentFactory
from app.core.signal_manager import SignalManager
from app.db import crud
from app.db.models import (
    PipelineTemplateDocument,
    PipelineNodeConfig,
    NodeType,
)


class DAGPipelineRunner:
    """
    DAG-based pipeline executor.
    Reads a pipeline template, resolves execution layers,
    runs nodes in parallel per layer, checks signals between layers.
    """

    def __init__(
        self,
        run_id: str,
        template: PipelineTemplateDocument,
        llm_profile_id: Optional[str] = None,
        progress_callback=None,
        mock_mode: bool = False,
    ):
        self._run_id = run_id
        self._template = template
        self._llm_profile_id = llm_profile_id
        self._progress_callback = progress_callback
        self._mock_mode = mock_mode
        self._signal_manager = SignalManager()

        # Node outputs cache: { node_id: output_dict }
        self._node_outputs: dict[str, dict] = {}

        # DAG resolver
        self._resolver = DAGResolver(template.nodes, template.edges)

    async def run(self, initial_input: dict) -> dict:
        """
        Execute the full pipeline DAG.

        Args:
            initial_input: Input data for the INPUT source node
                           (e.g., {"file_path": "...", "document_name": "..."})

        Returns:
            Final output from the OUTPUT sink node.
        """
        start_time = time.time()

        # ── 1. Validate DAG ──
        try:
            self._resolver.validate()
        except DAGValidationError as e:
            self._emit("run.failed", {"error": str(e)})
            await crud.update_pipeline_run(self._run_id, status="failed", error_message=str(e))
            raise

        # ── 2. Compute execution layers ──
        layers = self._resolver.get_execution_layers()
        await crud.update_pipeline_run(
            self._run_id,
            status="running",
            execution_layers=layers,
            started_at=datetime.now(timezone.utc),
        )
        self._emit("run.started", {
            "total_layers": len(layers),
            "total_nodes": sum(len(l) for l in layers),
            "layers": layers,
        })

        # ── 3. Seed INPUT node output ──
        input_node = next(
            n for n in self._template.nodes if n.node_type == NodeType.INPUT
        )
        self._node_outputs[input_node.node_id] = initial_input

        # ── 4. Execute layer by layer ──
        for layer_idx, layer_node_ids in enumerate(layers):
            # Skip the INPUT layer (already seeded)
            if all(
                self._get_node(nid).node_type == NodeType.INPUT
                for nid in layer_node_ids
            ):
                continue

            # ── Check signal: pause / cancel ──
            signal = await self._signal_manager.get_signal(self._run_id)
            if signal == "cancel":
                await self._handle_cancel()
                return self._build_result()
            elif signal == "pause":
                self._emit("run.paused", {
                    "completed_layers": layer_idx,
                    "next_layer": layer_node_ids,
                })
                await crud.update_pipeline_run(
                    self._run_id,
                    status="paused",
                    paused_at=datetime.now(timezone.utc),
                )
                # Block until resume or cancel
                signal = await self._signal_manager.wait_for_resume(self._run_id)
                if signal == "cancel":
                    await self._handle_cancel()
                    return self._build_result()
                self._emit("run.resumed", {"continuing_from_layer": layer_idx})
                await crud.update_pipeline_run(
                    self._run_id,
                    status="running",
                    resumed_at=datetime.now(timezone.utc),
                )

            # ── Execute all nodes in this layer in parallel ──
            self._emit("layer.started", {
                "layer_index": layer_idx,
                "nodes": layer_node_ids,
            })

            tasks = []
            for node_id in layer_node_ids:
                node_config = self._get_node(node_id)
                if not node_config.enabled:
                    self._emit("node.skipped", {"node_id": node_id})
                    continue

                # Gather inputs from parent nodes
                parent_outputs = self._gather_inputs(node_id)
                tasks.append(self._execute_node(node_config, parent_outputs))

            # Run all tasks in this layer concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for i, result in enumerate(results):
                node_id = layer_node_ids[i]
                if isinstance(result, Exception):
                    self._emit("node.failed", {
                        "node_id": node_id,
                        "error": str(result),
                    })
                    await crud.update_pipeline_run(
                        self._run_id,
                        failed_nodes=[*self._get_current_failed(), node_id],
                    )
                    await crud.save_pipeline_result(
                        self._run_id,
                        node_id=node_id,
                        status="failed",
                        error_message=str(result),
                    )
                    # Continue executing other branches? Or fail fast?
                    # Default: fail fast — abort pipeline
                    await crud.update_pipeline_run(
                        self._run_id,
                        status="failed",
                        error_message=f"Node '{node_id}' failed: {result}",
                    )
                    self._emit("run.failed", {
                        "failed_node": node_id,
                        "error": str(result),
                    })
                    raise result
                else:
                    self._node_outputs[node_id] = result

            self._emit("layer.completed", {
                "layer_index": layer_idx,
                "nodes": layer_node_ids,
            })

        # ── 5. Collect OUTPUT node result ──
        output_node = next(
            n for n in self._template.nodes if n.node_type == NodeType.OUTPUT
        )
        final_output = self._node_outputs.get(output_node.node_id, {})

        duration = time.time() - start_time
        await crud.update_pipeline_run(
            self._run_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
            duration_seconds=round(duration, 2),
        )
        self._emit("run.completed", {
            "duration_seconds": round(duration, 2),
            "total_nodes_executed": len(self._node_outputs),
        })

        return final_output

    async def _execute_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],
    ) -> dict:
        """Execute a single node and return its output."""
        node_id = node_config.node_id
        node_start = time.time()

        self._emit("node.started", {
            "node_id": node_id,
            "node_type": node_config.node_type,
            "label": node_config.label,
        })

        await crud.update_pipeline_run(
            self._run_id,
            current_node=node_id,
            node_statuses={node_id: "running"},
        )

        try:
            if node_config.node_type == NodeType.OUTPUT:
                # OUTPUT node: merge all parent outputs as final result
                output = self._merge_inputs(parent_outputs)

            elif node_config.node_type == NodeType.PURE_PYTHON:
                # Non-LLM node: run builtin Python function
                output = await self._run_pure_python_node(node_config, parent_outputs)

            elif node_config.node_type == NodeType.AGENT:
                # CrewAI agent node
                output = await self._run_agent_node(node_config, parent_outputs)

            else:
                raise ValueError(f"Unknown node_type: {node_config.node_type}")

            # Save result
            duration = time.time() - node_start
            await crud.save_pipeline_result(
                self._run_id,
                node_id=node_id,
                agent_id=node_config.agent_id,
                output=output,
                input_data=parent_outputs,
                status="completed",
                duration_seconds=round(duration, 2),
            )
            await crud.update_pipeline_run(
                self._run_id,
                completed_nodes=[*self._get_current_completed(), node_id],
                node_statuses={node_id: "completed"},
            )

            self._emit("node.completed", {
                "node_id": node_id,
                "duration_seconds": round(duration, 2),
                "output_preview": str(output)[:500],
            })

            return output

        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Node '{node_id}' timed out after {node_config.timeout_seconds}s"
            )

    async def _run_agent_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],
    ) -> dict:
        """Run a CrewAI agent node."""
        if self._mock_mode:
            await asyncio.sleep(0.5)
            return {"mock": True, "node_id": node_config.node_id, "status": "ok"}

        # Load agent config from DB
        agent_config = await crud.get_agent_config(node_config.agent_id)
        if not agent_config:
            raise ValueError(f"Agent config not found: {node_config.agent_id}")

        # Apply config overrides from node
        if node_config.config_overrides:
            for key, value in node_config.config_overrides.items():
                if hasattr(agent_config, key):
                    setattr(agent_config, key, value)

        # Build CrewAI agent
        factory = AgentFactory(
            run_profile_id=self._llm_profile_id,
        )
        crewai_agent = await factory.build(agent_config)

        # Prepare input from merged parent outputs
        merged_input = self._merge_inputs(parent_outputs)

        # Create task
        from crewai import Task, Crew, Process
        import json

        task = Task(
            description=f"""
            You are the {agent_config.role}.
            Your goal: {agent_config.goal}

            Process the following input data and produce structured output:
            {json.dumps(merged_input, default=str)[:8000]}
            """,
            expected_output="A JSON object with your analysis results.",
            agent=crewai_agent,
        )

        crew = Crew(
            agents=[crewai_agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        # Run in thread (CrewAI is sync)
        result = await asyncio.wait_for(
            asyncio.to_thread(crew.kickoff),
            timeout=node_config.timeout_seconds,
        )

        return self._parse_crew_output(result)

    async def _run_pure_python_node(
        self,
        node_config: PipelineNodeConfig,
        parent_outputs: dict[str, dict],
    ) -> dict:
        """Run a pure Python processing node (no LLM)."""
        # Map agent_id to builtin Python functions
        builtin_functions = {
            "ingestion_agent": self._builtin_ingestion,
            # Add more builtin pure_python handlers here
        }

        func = builtin_functions.get(node_config.agent_id)
        if func:
            merged_input = self._merge_inputs(parent_outputs)
            return await asyncio.wait_for(
                func(merged_input),
                timeout=node_config.timeout_seconds,
            )
        else:
            raise ValueError(
                f"No builtin function for pure_python node: {node_config.agent_id}"
            )

    def _gather_inputs(self, node_id: str) -> dict[str, dict]:
        """
        Gather outputs from all parent nodes for a given node.
        Returns: { parent_node_id: parent_output_dict }
        """
        parents = self._resolver.get_node_parents(node_id)
        return {
            parent_id: self._node_outputs.get(parent_id, {})
            for parent_id in parents
            if parent_id in self._node_outputs
        }

    def _merge_inputs(self, parent_outputs: dict[str, dict]) -> dict:
        """Merge multiple parent outputs into a single input dict."""
        if len(parent_outputs) == 1:
            # Single parent: pass through directly
            return next(iter(parent_outputs.values()))

        # Multiple parents: namespace by parent_id + flat merge
        merged = {"__sources__": {}}
        flat = {}
        for parent_id, output in parent_outputs.items():
            merged["__sources__"][parent_id] = output
            if isinstance(output, dict):
                flat.update(output)

        merged.update(flat)
        return merged

    def _get_node(self, node_id: str) -> PipelineNodeConfig:
        """Get node config by ID."""
        for node in self._template.nodes:
            if node.node_id == node_id:
                return node
        raise ValueError(f"Node not found: {node_id}")

    def _get_current_completed(self) -> list[str]:
        """Get list of completed node IDs (from cache)."""
        return [
            nid for nid, output in self._node_outputs.items()
            if output is not None
        ]

    def _get_current_failed(self) -> list[str]:
        """Placeholder for tracking failed nodes."""
        return []

    def _emit(self, event: str, data: dict):
        """Emit WebSocket event."""
        if self._progress_callback:
            self._progress_callback(event, {
                "run_id": self._run_id,
                **data,
            })

    async def _handle_cancel(self):
        """Handle pipeline cancellation."""
        await crud.update_pipeline_run(
            self._run_id,
            status="cancelled",
            completed_at=datetime.now(timezone.utc),
        )
        self._emit("run.cancelled", {
            "completed_nodes": list(self._node_outputs.keys()),
            "partial_results_available": len(self._node_outputs) > 0,
        })

    def _build_result(self) -> dict:
        """Build final result dict."""
        return {
            "run_id": self._run_id,
            "node_outputs": self._node_outputs,
            "status": "cancelled",
        }

    def _parse_crew_output(self, result) -> dict:
        """Parse CrewAI output into a dict."""
        import json
        if hasattr(result, 'raw'):
            raw = result.raw
        else:
            raw = str(result)

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {"raw_output": raw}

    async def _builtin_ingestion(self, input_data: dict) -> dict:
        """Builtin ingestion processing (pure Python, no LLM)."""
        from app.crews.ingestion_crew import IngestionCrew
        crew = IngestionCrew(
            run_id=self._run_id,
            run_profile_id=self._llm_profile_id,
            progress_callback=self._progress_callback,
            mock_mode=self._mock_mode,
        )
        return await crew.run(input_data)
```

---

## 11. Feature 5 – Pipeline Template CRUD API

### API Endpoints

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/api/v1/pipeline-templates` | List all templates (sorted by updated_at desc, filter: archived, tags) |
| `POST` | `/api/v1/pipeline-templates` | Create new template |
| `GET` | `/api/v1/pipeline-templates/{template_id}` | Get template details (full nodes + edges) |
| `PUT` | `/api/v1/pipeline-templates/{template_id}` | Update template (nodes, edges, metadata) |
| `DELETE` | `/api/v1/pipeline-templates/{template_id}` | Delete template (hard delete if no runs, else error) |
| `POST` | `/api/v1/pipeline-templates/{template_id}/clone` | Clone template → new template_id |
| `POST` | `/api/v1/pipeline-templates/{template_id}/archive` | Archive (soft delete) |
| `POST` | `/api/v1/pipeline-templates/{template_id}/validate` | Validate DAG without saving |
| `GET` | `/api/v1/pipeline-templates/{template_id}/export` | Export as JSON |
| `POST` | `/api/v1/pipeline-templates/import` | Import from JSON |

### Schemas

```python
# schemas/pipeline_template.py — NEW

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class PipelineNodeInput(BaseModel):
    """Input schema for a node in the pipeline."""
    node_id: str = Field(..., pattern=r'^[a-z][a-z0-9_-]{2,49}$')
    node_type: str = Field(default="agent", description="input | output | agent | pure_python")
    agent_id: Optional[str] = None
    label: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    position_x: float = 0.0
    position_y: float = 0.0
    timeout_seconds: int = Field(default=300, ge=10, le=7200)
    retry_count: int = Field(default=0, ge=0, le=5)
    enabled: bool = True
    config_overrides: dict = Field(default_factory=dict)


class PipelineEdgeInput(BaseModel):
    """Input schema for an edge in the pipeline."""
    edge_id: str
    source_node_id: str
    target_node_id: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None
    label: Optional[str] = None
    animated: bool = False


class PipelineTemplateCreate(BaseModel):
    """Create a new pipeline template."""
    template_id: str = Field(
        ...,
        pattern=r'^[a-z][a-z0-9_-]{2,49}$',
        description="Unique URL-safe identifier"
    )
    name: str = Field(..., min_length=2, max_length=200)
    description: str = ""
    nodes: list[PipelineNodeInput] = Field(default_factory=list)
    edges: list[PipelineEdgeInput] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PipelineTemplateUpdate(BaseModel):
    """Update an existing pipeline template."""
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    description: Optional[str] = None
    nodes: Optional[list[PipelineNodeInput]] = None
    edges: Optional[list[PipelineEdgeInput]] = None
    tags: Optional[list[str]] = None


class PipelineTemplateResponse(BaseModel):
    """Response schema for a pipeline template."""
    id: str
    template_id: str
    name: str
    description: str
    version: int
    nodes: list[PipelineNodeInput]
    edges: list[PipelineEdgeInput]
    is_builtin: bool
    is_archived: bool
    tags: list[str]
    node_count: int
    edge_count: int
    created_at: datetime
    updated_at: datetime


class PipelineTemplateListItem(BaseModel):
    """Summary item for pipeline template list."""
    id: str
    template_id: str
    name: str
    description: str
    version: int
    is_builtin: bool
    is_archived: bool
    tags: list[str]
    node_count: int
    edge_count: int
    last_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class DAGValidationResponse(BaseModel):
    """Response from DAG validation endpoint."""
    is_valid: bool
    errors: list[str] = []
    warnings: list[str] = []
    execution_layers: list[list[str]] = []
    total_layers: int = 0
    total_nodes: int = 0
    estimated_parallel_speedup: Optional[float] = None
```

### API Handler

```python
# api/v1/pipeline_templates.py — NEW

from fastapi import APIRouter, HTTPException
from app.schemas.pipeline_template import (
    PipelineTemplateCreate,
    PipelineTemplateUpdate,
    PipelineTemplateResponse,
    PipelineTemplateListItem,
    DAGValidationResponse,
)
from app.core.dag_resolver import DAGResolver, DAGValidationError
from app.db import crud

router = APIRouter(prefix="/api/v1/pipeline-templates", tags=["Pipeline Templates"])


@router.get("", response_model=list[PipelineTemplateListItem])
async def list_templates(
    include_archived: bool = False,
    tag: str | None = None,
):
    """List all pipeline templates."""
    templates = await crud.get_all_pipeline_templates(
        include_archived=include_archived,
        tag=tag,
    )
    result = []
    for t in templates:
        # Get last run info
        last_run = await crud.get_latest_run_for_template(t.template_id)
        result.append(PipelineTemplateListItem(
            id=str(t.id),
            template_id=t.template_id,
            name=t.name,
            description=t.description,
            version=t.version,
            is_builtin=t.is_builtin,
            is_archived=t.is_archived,
            tags=t.tags,
            node_count=len(t.nodes),
            edge_count=len(t.edges),
            last_run_at=last_run.created_at if last_run else None,
            last_run_status=last_run.status if last_run else None,
            created_at=t.created_at,
            updated_at=t.updated_at,
        ))
    return result


@router.post("", status_code=201, response_model=PipelineTemplateResponse)
async def create_template(body: PipelineTemplateCreate):
    """Create a new pipeline template."""
    # Check uniqueness
    existing = await crud.get_pipeline_template(body.template_id)
    if existing:
        raise HTTPException(409, f"Template '{body.template_id}' already exists")

    # Validate DAG if nodes/edges provided
    if body.nodes and body.edges:
        try:
            from app.db.models import PipelineNodeConfig, PipelineEdgeConfig
            nodes = [PipelineNodeConfig(**n.model_dump()) for n in body.nodes]
            edges = [PipelineEdgeConfig(**e.model_dump()) for e in body.edges]
            resolver = DAGResolver(nodes, edges)
            resolver.validate()
        except DAGValidationError as e:
            raise HTTPException(422, f"Invalid DAG: {e}")

    # Validate agent_ids exist
    for node in body.nodes:
        if node.agent_id:
            agent = await crud.get_agent_config(node.agent_id)
            if not agent:
                raise HTTPException(404, f"Agent '{node.agent_id}' not found")

    template = await crud.create_pipeline_template(body.model_dump())
    return _to_response(template)


@router.get("/{template_id}", response_model=PipelineTemplateResponse)
async def get_template(template_id: str):
    """Get full pipeline template including nodes and edges."""
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")
    return _to_response(template)


@router.put("/{template_id}", response_model=PipelineTemplateResponse)
async def update_template(template_id: str, body: PipelineTemplateUpdate):
    """Update pipeline template. Auto-increments version."""
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    # Validate DAG if nodes/edges are being updated
    update_data = body.model_dump(exclude_unset=True)
    nodes = body.nodes or template.nodes
    edges = body.edges or template.edges

    if body.nodes is not None or body.edges is not None:
        try:
            from app.db.models import PipelineNodeConfig, PipelineEdgeConfig
            node_configs = [
                PipelineNodeConfig(**(n.model_dump() if hasattr(n, 'model_dump') else n))
                for n in nodes
            ]
            edge_configs = [
                PipelineEdgeConfig(**(e.model_dump() if hasattr(e, 'model_dump') else e))
                for e in edges
            ]
            resolver = DAGResolver(node_configs, edge_configs)
            resolver.validate()
        except DAGValidationError as e:
            raise HTTPException(422, f"Invalid DAG: {e}")

    updated = await crud.update_pipeline_template(template_id, update_data)
    return _to_response(updated)


@router.delete("/{template_id}")
async def delete_template(template_id: str):
    """Delete a pipeline template (only if no runs exist)."""
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")
    if template.is_builtin:
        raise HTTPException(403, "Cannot delete builtin template. Archive it instead.")

    # Check for existing runs
    run_count = await crud.count_runs_for_template(template_id)
    if run_count > 0:
        raise HTTPException(
            409,
            f"Cannot delete template with {run_count} existing runs. Archive it instead."
        )

    await crud.delete_pipeline_template(template_id)
    return {"deleted": template_id}


@router.post("/{template_id}/clone", status_code=201, response_model=PipelineTemplateResponse)
async def clone_template(template_id: str, new_template_id: str, new_name: str | None = None):
    """Clone a pipeline template into a new one."""
    original = await crud.get_pipeline_template(template_id)
    if not original:
        raise HTTPException(404, f"Template '{template_id}' not found")

    # Check new_template_id uniqueness
    existing = await crud.get_pipeline_template(new_template_id)
    if existing:
        raise HTTPException(409, f"Template '{new_template_id}' already exists")

    cloned = await crud.clone_pipeline_template(
        original,
        new_template_id=new_template_id,
        new_name=new_name or f"{original.name} (Copy)",
    )
    return _to_response(cloned)


@router.post("/{template_id}/archive")
async def archive_template(template_id: str):
    """Archive (soft-delete) a pipeline template."""
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    await crud.update_pipeline_template(template_id, {"is_archived": True})
    return {"archived": template_id}


@router.post("/{template_id}/validate", response_model=DAGValidationResponse)
async def validate_template(template_id: str):
    """Validate the DAG of a pipeline template without saving."""
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    resolver = DAGResolver(template.nodes, template.edges)

    try:
        resolver.validate()
        layers = resolver.get_execution_layers()
        total_nodes = sum(len(l) for l in layers)
        max_layer_size = max(len(l) for l in layers) if layers else 0

        return DAGValidationResponse(
            is_valid=True,
            execution_layers=layers,
            total_layers=len(layers),
            total_nodes=total_nodes,
            estimated_parallel_speedup=round(total_nodes / len(layers), 2) if layers else None,
        )
    except DAGValidationError as e:
        return DAGValidationResponse(
            is_valid=False,
            errors=str(e).split("; "),
        )


@router.get("/{template_id}/export")
async def export_template(template_id: str):
    """Export pipeline template as JSON (for sharing/backup)."""
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")

    from fastapi.responses import JSONResponse
    export_data = {
        "auto_at_version": "3.0",
        "export_type": "pipeline_template",
        "template": {
            "template_id": template.template_id,
            "name": template.name,
            "description": template.description,
            "nodes": [n.model_dump() for n in template.nodes],
            "edges": [e.model_dump() for e in template.edges],
            "tags": template.tags,
        },
    }
    return JSONResponse(
        content=export_data,
        headers={
            "Content-Disposition": f'attachment; filename="{template_id}.json"',
        },
    )


@router.post("/import", status_code=201, response_model=PipelineTemplateResponse)
async def import_template(body: dict):
    """Import a pipeline template from JSON."""
    if body.get("export_type") != "pipeline_template":
        raise HTTPException(422, "Invalid export file format")

    template_data = body.get("template", {})
    create_input = PipelineTemplateCreate(**template_data)

    # Check uniqueness — append suffix if collision
    base_id = create_input.template_id
    counter = 1
    while await crud.get_pipeline_template(create_input.template_id):
        create_input.template_id = f"{base_id}-{counter}"
        counter += 1

    template = await crud.create_pipeline_template(create_input.model_dump())
    return _to_response(template)


def _to_response(template) -> PipelineTemplateResponse:
    return PipelineTemplateResponse(
        id=str(template.id),
        template_id=template.template_id,
        name=template.name,
        description=template.description,
        version=template.version,
        nodes=[PipelineNodeInput(**n.model_dump()) for n in template.nodes] if template.nodes else [],
        edges=[PipelineEdgeInput(**e.model_dump()) for e in template.edges] if template.edges else [],
        is_builtin=template.is_builtin,
        is_archived=template.is_archived,
        tags=template.tags,
        node_count=len(template.nodes),
        edge_count=len(template.edges),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )
```

### Updated Pipeline Run Endpoint

```python
# api/v1/pipeline.py — UPDATED

@router.post("/api/v1/pipeline/runs", status_code=201)
async def create_pipeline_run(
    template_id: str = Form(...),
    file: UploadFile = File(None),
    llm_profile_id: str = Form(None),
    run_params: str = Form("{}"),
):
    """
    Create and start a new pipeline run.
    V3: Must specify which pipeline template to run.
    """
    # Load template
    template = await crud.get_pipeline_template(template_id)
    if not template:
        raise HTTPException(404, f"Template '{template_id}' not found")
    if template.is_archived:
        raise HTTPException(400, "Cannot run an archived template")

    # Validate DAG
    resolver = DAGResolver(template.nodes, template.edges)
    try:
        resolver.validate()
    except DAGValidationError as e:
        raise HTTPException(422, f"Pipeline DAG is invalid: {e}")

    # Create run
    import json
    run = await crud.create_pipeline_run(
        template_id=template_id,
        template_snapshot={
            "nodes": [n.model_dump() for n in template.nodes],
            "edges": [e.model_dump() for e in template.edges],
        },
        file_path=str(saved_path) if file else None,
        document_name=file.filename if file else "",
        llm_profile_id=llm_profile_id,
        run_params=json.loads(run_params),
    )

    # Start DAG runner in background
    runner = DAGPipelineRunner(
        run_id=run.run_id,
        template=template,
        llm_profile_id=llm_profile_id,
        progress_callback=ws_manager.emit,
        mock_mode=settings.MOCK_PIPELINE,
    )

    import asyncio
    initial_input = {
        "file_path": str(saved_path) if file else None,
        "document_name": file.filename if file else "",
    }
    asyncio.create_task(runner.run(initial_input))

    return PipelineRunResponse.model_validate(run)
```

---

## 12. Feature 6 – Pipeline Builder Frontend

### React Flow Integration

```tsx
// components/pipeline-builder/PipelineBuilder.tsx

'use client';

import { useCallback, useRef, useMemo } from 'react';
import {
    ReactFlow,
    MiniMap,
    Controls,
    Background,
    BackgroundVariant,
    Panel,
    useReactFlow,
    type Node,
    type Edge,
    type NodeTypes,
    type OnDragOver,
    type OnDrop,
    ReactFlowProvider,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { useBuilderStore } from '@/store/builderStore';
import { AgentNode } from './nodes/AgentNode';
import { InputNode } from './nodes/InputNode';
import { OutputNode } from './nodes/OutputNode';
import { AgentCatalogSidebar } from './AgentCatalogSidebar';
import { NodePropertiesPanel } from './NodePropertiesPanel';
import { BuilderToolbar } from './BuilderToolbar';
import { ValidationPanel } from './ValidationPanel';

const nodeTypes: NodeTypes = {
    agentNode: AgentNode,
    inputNode: InputNode,
    outputNode: OutputNode,
};

export function PipelineBuilder({ templateId }: { templateId: string }) {
    const reactFlowWrapper = useRef<HTMLDivElement>(null);
    const { screenToFlowPosition } = useReactFlow();

    const {
        nodes,
        edges,
        onNodesChange,
        onEdgesChange,
        onConnect,
        addNode,
        selectNode,
        selectedNodeId,
        validationErrors,
        isValid,
        isDirty,
    } = useBuilderStore();

    // ── Handle drop from Agent Catalog ──
    const onDragOver: OnDragOver = useCallback((event) => {
        event.preventDefault();
        event.dataTransfer.dropEffect = 'move';
    }, []);

    const onDrop: OnDrop = useCallback(
        (event) => {
            event.preventDefault();

            const agentData = event.dataTransfer.getData('application/reactflow');
            if (!agentData) return;

            const { agentId, label, nodeType, description } = JSON.parse(agentData);

            const position = screenToFlowPosition({
                x: event.clientX,
                y: event.clientY,
            });

            const newNodeId = `${agentId}_${Date.now()}`;

            const newNode: Node = {
                id: newNodeId,
                type: nodeType === 'input' ? 'inputNode'
                    : nodeType === 'output' ? 'outputNode'
                    : 'agentNode',
                position,
                data: {
                    label,
                    agentId,
                    nodeType,
                    description,
                    enabled: true,
                    status: 'idle',
                },
            };

            addNode(newNode);
        },
        [screenToFlowPosition, addNode],
    );

    const onNodeClick = useCallback(
        (_: React.MouseEvent, node: Node) => {
            selectNode(node.id);
        },
        [selectNode],
    );

    const onPaneClick = useCallback(() => {
        selectNode(null);
    }, [selectNode]);

    return (
        <div className="flex h-full">
            {/* Left: Agent Catalog Sidebar */}
            <AgentCatalogSidebar />

            {/* Center: React Flow Canvas */}
            <div
                ref={reactFlowWrapper}
                className="flex-1 h-full relative"
            >
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    onNodesChange={onNodesChange}
                    onEdgesChange={onEdgesChange}
                    onConnect={onConnect}
                    onDragOver={onDragOver}
                    onDrop={onDrop}
                    onNodeClick={onNodeClick}
                    onPaneClick={onPaneClick}
                    nodeTypes={nodeTypes}
                    fitView
                    snapToGrid
                    snapGrid={[20, 20]}
                    connectionLineType="smoothstep"
                    defaultEdgeOptions={{
                        type: 'smoothstep',
                        animated: false,
                    }}
                >
                    <Background
                        variant={BackgroundVariant.Dots}
                        gap={20}
                        size={1}
                        color="#333"
                    />
                    <MiniMap
                        nodeColor={(n) => {
                            if (n.data?.nodeType === 'input') return '#3b82f6';
                            if (n.data?.nodeType === 'output') return '#22c55e';
                            return '#6366f1';
                        }}
                        className="bg-zinc-900/80 rounded-lg"
                    />
                    <Controls className="bg-zinc-800 rounded-lg" />

                    {/* Toolbar (Save, Run, Undo, Redo) */}
                    <Panel position="top-right">
                        <BuilderToolbar />
                    </Panel>

                    {/* Validation Status */}
                    <Panel position="bottom-left">
                        <ValidationPanel
                            errors={validationErrors}
                            isValid={isValid}
                            isDirty={isDirty}
                        />
                    </Panel>
                </ReactFlow>
            </div>

            {/* Right: Properties Panel (when node selected) */}
            {selectedNodeId && <NodePropertiesPanel nodeId={selectedNodeId} />}
        </div>
    );
}

// Wrap with ReactFlowProvider at the page level
export function PipelineBuilderPage({ templateId }: { templateId: string }) {
    return (
        <ReactFlowProvider>
            <PipelineBuilder templateId={templateId} />
        </ReactFlowProvider>
    );
}
```

### Agent Catalog Sidebar

```tsx
// components/pipeline-builder/AgentCatalogSidebar.tsx

'use client';

import { useState } from 'react';
import { Search, Plus, GripVertical, ChevronDown, ChevronRight } from 'lucide-react';
import { useAgentConfigs } from '@/hooks/useAgentConfigs';

interface CatalogItem {
    agentId: string;
    label: string;
    nodeType: string;
    description: string;
    stage: string;
}

export function AgentCatalogSidebar() {
    const [search, setSearch] = useState('');
    const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
        new Set(['special', 'ingestion', 'testcase', 'execution', 'reporting', 'custom']),
    );
    const { data: agents } = useAgentConfigs();

    // Special nodes (always available)
    const specialItems: CatalogItem[] = [
        {
            agentId: '__input__',
            label: '📥 Input',
            nodeType: 'input',
            description: 'Pipeline entry point',
            stage: 'special',
        },
        {
            agentId: '__output__',
            label: '📤 Output',
            nodeType: 'output',
            description: 'Pipeline final output',
            stage: 'special',
        },
    ];

    // Agent items grouped by stage
    const agentItems: CatalogItem[] = (agents || []).map((a) => ({
        agentId: a.agent_id,
        label: a.display_name,
        nodeType: a.stage === 'ingestion' ? 'pure_python' : 'agent',
        description: a.role,
        stage: a.stage,
    }));

    // Group by stage
    const groups: Record<string, CatalogItem[]> = { special: specialItems };
    agentItems.forEach((item) => {
        if (!groups[item.stage]) groups[item.stage] = [];
        groups[item.stage].push(item);
    });

    // Filter by search
    const filteredGroups = Object.entries(groups).reduce(
        (acc, [stage, items]) => {
            const filtered = items.filter(
                (item) =>
                    item.label.toLowerCase().includes(search.toLowerCase()) ||
                    item.description.toLowerCase().includes(search.toLowerCase()),
            );
            if (filtered.length > 0) acc[stage] = filtered;
            return acc;
        },
        {} as Record<string, CatalogItem[]>,
    );

    const toggleGroup = (group: string) => {
        setExpandedGroups((prev) => {
            const next = new Set(prev);
            if (next.has(group)) next.delete(group);
            else next.add(group);
            return next;
        });
    };

    const onDragStart = (event: React.DragEvent, item: CatalogItem) => {
        event.dataTransfer.setData(
            'application/reactflow',
            JSON.stringify(item),
        );
        event.dataTransfer.effectAllowed = 'move';
    };

    return (
        <div className="w-64 border-r border-zinc-700 bg-zinc-900 flex flex-col overflow-hidden">
            {/* Header */}
            <div className="p-3 border-b border-zinc-700">
                <h3 className="font-semibold text-sm text-zinc-300 mb-2">
                    Agent Catalog
                </h3>
                <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-zinc-500" />
                    <input
                        type="text"
                        placeholder="Search agents..."
                        value={search}
                        onChange={(e) => setSearch(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 text-xs bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 placeholder-zinc-500"
                    />
                </div>
            </div>

            {/* Agent Groups */}
            <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {Object.entries(filteredGroups).map(([stage, items]) => (
                    <div key={stage}>
                        <button
                            onClick={() => toggleGroup(stage)}
                            className="w-full flex items-center gap-1 px-2 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-200 transition-colors"
                        >
                            {expandedGroups.has(stage) ? (
                                <ChevronDown className="h-3 w-3" />
                            ) : (
                                <ChevronRight className="h-3 w-3" />
                            )}
                            {stage.charAt(0).toUpperCase() + stage.slice(1)}
                            <span className="ml-auto text-zinc-600">{items.length}</span>
                        </button>

                        {expandedGroups.has(stage) && (
                            <div className="space-y-0.5 ml-2">
                                {items.map((item) => (
                                    <div
                                        key={item.agentId}
                                        draggable
                                        onDragStart={(e) => onDragStart(e, item)}
                                        className="flex items-center gap-2 px-2 py-1.5 rounded-md
                                                   cursor-grab active:cursor-grabbing
                                                   hover:bg-zinc-800 transition-colors
                                                   border border-transparent hover:border-zinc-600"
                                    >
                                        <GripVertical className="h-3 w-3 text-zinc-600" />
                                        <div className="min-w-0">
                                            <div className="text-xs font-medium text-zinc-200 truncate">
                                                {item.label}
                                            </div>
                                            <div className="text-[10px] text-zinc-500 truncate">
                                                {item.description}
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                ))}
            </div>

            {/* Footer */}
            <div className="p-2 border-t border-zinc-700">
                <button className="w-full flex items-center justify-center gap-1 px-3 py-1.5 text-xs bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-md transition-colors">
                    <Plus className="h-3 w-3" />
                    New Agent
                </button>
            </div>
        </div>
    );
}
```

### Node Properties Panel

```tsx
// components/pipeline-builder/NodePropertiesPanel.tsx

'use client';

import { useBuilderStore } from '@/store/builderStore';
import { useLLMProfiles } from '@/hooks/useLLMProfiles';
import { Trash2, Settings, Zap } from 'lucide-react';

export function NodePropertiesPanel({ nodeId }: { nodeId: string }) {
    const nodes = useBuilderStore((s) => s.nodes);
    const updateNodeData = useBuilderStore((s) => s.updateNodeData);
    const removeNode = useBuilderStore((s) => s.removeNode);
    const edges = useBuilderStore((s) => s.edges);

    const node = nodes.find((n) => n.id === nodeId);
    if (!node) return null;

    const { data: llmProfiles } = useLLMProfiles();

    const incomingEdges = edges.filter((e) => e.target === nodeId);
    const outgoingEdges = edges.filter((e) => e.source === nodeId);
    const inputSources = incomingEdges.map((e) => {
        const sourceNode = nodes.find((n) => n.id === e.source);
        return sourceNode?.data?.label || e.source;
    });

    const isSpecial = node.data?.nodeType === 'input' || node.data?.nodeType === 'output';

    return (
        <div className="w-80 border-l border-zinc-700 bg-zinc-900 overflow-y-auto">
            {/* Header */}
            <div className="p-4 border-b border-zinc-700 flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Settings className="h-4 w-4 text-zinc-400" />
                    <h3 className="font-semibold text-sm text-zinc-200">Properties</h3>
                </div>
                {!isSpecial && (
                    <button
                        onClick={() => removeNode(nodeId)}
                        className="p-1.5 text-red-400 hover:bg-red-400/10 rounded"
                    >
                        <Trash2 className="h-4 w-4" />
                    </button>
                )}
            </div>

            <div className="p-4 space-y-4">
                {/* Basic Info */}
                <section className="space-y-2">
                    <label className="text-xs font-medium text-zinc-400">Label</label>
                    <input
                        type="text"
                        value={node.data?.label || ''}
                        onChange={(e) => updateNodeData(nodeId, { label: e.target.value })}
                        className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200"
                    />
                </section>

                <section className="space-y-2">
                    <label className="text-xs font-medium text-zinc-400">Description</label>
                    <textarea
                        value={node.data?.description || ''}
                        onChange={(e) => updateNodeData(nodeId, { description: e.target.value })}
                        rows={2}
                        className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200 resize-none"
                    />
                </section>

                {/* Input Sources (read-only, informational) */}
                <section className="space-y-2">
                    <label className="text-xs font-medium text-zinc-400 flex items-center gap-1">
                        <Zap className="h-3 w-3" />
                        Input From
                    </label>
                    {inputSources.length > 0 ? (
                        <div className="space-y-1">
                            {inputSources.map((src, i) => (
                                <div
                                    key={i}
                                    className="px-2 py-1 text-xs bg-zinc-800 rounded border border-zinc-700 text-zinc-300"
                                >
                                    ← {src}
                                </div>
                            ))}
                        </div>
                    ) : (
                        <p className="text-xs text-zinc-500 italic">No inputs connected</p>
                    )}
                </section>

                {/* Agent-specific config */}
                {node.data?.nodeType === 'agent' && (
                    <>
                        <section className="space-y-2">
                            <label className="text-xs font-medium text-zinc-400">Agent ID</label>
                            <div className="px-3 py-1.5 text-sm bg-zinc-800/50 border border-zinc-700 rounded-md text-zinc-400">
                                {node.data.agentId}
                            </div>
                        </section>

                        <section className="space-y-2">
                            <label className="text-xs font-medium text-zinc-400">LLM Override</label>
                            <select
                                value={node.data?.configOverrides?.llm_profile_id || ''}
                                onChange={(e) =>
                                    updateNodeData(nodeId, {
                                        configOverrides: {
                                            ...(node.data?.configOverrides || {}),
                                            llm_profile_id: e.target.value || undefined,
                                        },
                                    })
                                }
                                className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200"
                            >
                                <option value="">Use default</option>
                                {llmProfiles?.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.name} ({p.provider}/{p.model_name})
                                    </option>
                                ))}
                            </select>
                        </section>

                        <section className="space-y-2">
                            <label className="text-xs font-medium text-zinc-400">Timeout (seconds)</label>
                            <input
                                type="number"
                                value={node.data?.timeout_seconds || 300}
                                onChange={(e) =>
                                    updateNodeData(nodeId, {
                                        timeout_seconds: parseInt(e.target.value) || 300,
                                    })
                                }
                                min={10}
                                max={7200}
                                className="w-full px-3 py-1.5 text-sm bg-zinc-800 border border-zinc-600 rounded-md text-zinc-200"
                            />
                        </section>

                        <section className="flex items-center justify-between">
                            <label className="text-xs font-medium text-zinc-400">Enabled</label>
                            <input
                                type="checkbox"
                                checked={node.data?.enabled ?? true}
                                onChange={(e) =>
                                    updateNodeData(nodeId, { enabled: e.target.checked })
                                }
                                className="rounded"
                            />
                        </section>
                    </>
                )}

                {/* Connection summary */}
                <section className="pt-2 border-t border-zinc-700 space-y-1">
                    <div className="text-xs text-zinc-500">
                        {incomingEdges.length} incoming · {outgoingEdges.length} outgoing
                    </div>
                    <div className="text-xs text-zinc-500">
                        Node ID: {node.id}
                    </div>
                </section>
            </div>
        </div>
    );
}
```

### Pipeline Run View (Live DAG Visualization)

Khi pipeline đang chạy, giao diện builder hiển thị ở chế độ **read-only** với node statuses cập nhật realtime:

```tsx
// components/pipeline/PipelineRunView.tsx

'use client';

import { useEffect, useMemo } from 'react';
import {
    ReactFlow,
    MiniMap,
    Controls,
    Background,
    BackgroundVariant,
    ReactFlowProvider,
    type Node,
    type Edge,
    type NodeTypes,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

import { usePipelineStore } from '@/store/pipelineStore';
import { AgentNode } from '../pipeline-builder/nodes/AgentNode';
import { InputNode } from '../pipeline-builder/nodes/InputNode';
import { OutputNode } from '../pipeline-builder/nodes/OutputNode';

const nodeTypes: NodeTypes = {
    agentNode: AgentNode,
    inputNode: InputNode,
    outputNode: OutputNode,
};

interface PipelineRunViewProps {
    runId: string;
    templateNodes: any[];
    templateEdges: any[];
}

export function PipelineRunView({ runId, templateNodes, templateEdges }: PipelineRunViewProps) {
    const nodeStatuses = usePipelineStore((s) => s.nodeStatuses);
    const currentNode = usePipelineStore((s) => s.currentNode);

    // Convert template nodes to React Flow nodes with live status
    const nodes: Node[] = useMemo(() => {
        return templateNodes.map((n) => ({
            id: n.node_id,
            type: n.node_type === 'input' ? 'inputNode'
                : n.node_type === 'output' ? 'outputNode'
                : 'agentNode',
            position: { x: n.position_x, y: n.position_y },
            data: {
                label: n.label,
                agentId: n.agent_id,
                nodeType: n.node_type,
                description: n.description,
                enabled: n.enabled,
                status: nodeStatuses[n.node_id] || 'idle',
            },
            // Disable dragging during run
            draggable: false,
        }));
    }, [templateNodes, nodeStatuses]);

    // Convert template edges with animation for active connections
    const edges: Edge[] = useMemo(() => {
        return templateEdges.map((e) => ({
            id: e.edge_id,
            source: e.source_node_id,
            target: e.target_node_id,
            type: 'smoothstep',
            animated: nodeStatuses[e.source_node_id] === 'completed'
                && nodeStatuses[e.target_node_id] === 'running',
            style: {
                stroke: nodeStatuses[e.source_node_id] === 'completed'
                    ? '#22c55e'
                    : nodeStatuses[e.source_node_id] === 'failed'
                    ? '#ef4444'
                    : '#555',
            },
        }));
    }, [templateEdges, nodeStatuses]);

    return (
        <div className="w-full h-[500px] rounded-xl border border-zinc-700 overflow-hidden">
            <ReactFlowProvider>
                <ReactFlow
                    nodes={nodes}
                    edges={edges}
                    nodeTypes={nodeTypes}
                    fitView
                    nodesDraggable={false}
                    nodesConnectable={false}
                    elementsSelectable={false}
                    panOnDrag
                    zoomOnScroll
                >
                    <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#222" />
                    <MiniMap
                        nodeColor={(n) => {
                            const status = n.data?.status;
                            if (status === 'running') return '#3b82f6';
                            if (status === 'completed') return '#22c55e';
                            if (status === 'failed') return '#ef4444';
                            return '#555';
                        }}
                        className="bg-zinc-900/80 rounded-lg"
                    />
                    <Controls className="bg-zinc-800 rounded-lg" />
                </ReactFlow>
            </ReactFlowProvider>
        </div>
    );
}
```

---

## 13. Updated Data Models

### Model Changes Summary (V2 → V3)

| Model | V2 | V3 Changes |
|-------|-----|------------|
| `PipelineTemplate` | _(không có)_ | **NEW** — DAG definition with nodes + edges embedded |
| `PipelineNodeConfig` | _(không có)_ | **NEW** — embedded in PipelineTemplate |
| `PipelineEdgeConfig` | _(không có)_ | **NEW** — embedded in PipelineTemplate |
| `StageConfig` | `stage_configs` collection | **DEPRECATED** — replaced by pipeline template nodes |
| `PipelineRun` | References global pipeline | → References `template_id` + stores `template_snapshot`, `node_statuses`, `execution_layers` |
| `PipelineResult` | Per-stage results | → Per-**node** results with `node_id` replacing `stage` |
| `AgentConfig` | No change | **Agent Catalog** — agents exist independently, referenced by nodes via `agent_id` |
| `LLMProfile` | No change | No change |

### Pydantic Schemas — New/Updated

```python
# schemas/pipeline.py — updated

class PipelineStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    PAUSED    = "paused"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"

class WSEventType(str, Enum):
    # V2 events (kept)
    RUN_STARTED    = "run.started"
    RUN_COMPLETED  = "run.completed"
    RUN_FAILED     = "run.failed"
    RUN_PAUSED     = "run.paused"
    RUN_RESUMED    = "run.resumed"
    RUN_CANCELLED  = "run.cancelled"

    # V3 new events
    LAYER_STARTED   = "layer.started"     # NEW: execution layer started
    LAYER_COMPLETED = "layer.completed"   # NEW: execution layer completed
    NODE_STARTED    = "node.started"      # NEW: replaces agent.started
    NODE_COMPLETED  = "node.completed"    # NEW: replaces agent.completed
    NODE_FAILED     = "node.failed"       # NEW: replaces agent.failed
    NODE_SKIPPED    = "node.skipped"      # NEW: disabled node skipped
    NODE_PROGRESS   = "node.progress"     # NEW: replaces agent.progress

    # Kept
    LOG = "log"

class PipelineRunCreate(BaseModel):
    template_id: str = Field(..., description="Which pipeline template to run")
    llm_profile_id: Optional[str] = None
    run_params: dict = Field(default_factory=dict)

class PipelineRunResponse(BaseModel):
    id: str
    run_id: str
    template_id: str
    document_name: str
    status: str
    current_node: Optional[str] = None
    completed_nodes: list[str] = []
    failed_nodes: list[str] = []
    node_statuses: dict[str, str] = {}
    execution_layers: list[list[str]] = []
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
```

---

## 14. Updated API Endpoints

### Complete Endpoint Map V3

#### Health

| Method | Path | V2? | V3 Changes |
|--------|------|-----|------------|
| `GET` | `/health` | ✅ | +version "3.0" |
| `GET` | `/` | ✅ | No change |

#### Pipeline Templates (NEW)

| Method | Path | Mô tả |
|--------|------|-------|
| `GET` | `/api/v1/pipeline-templates` | List all templates |
| `POST` | `/api/v1/pipeline-templates` | Create template |
| `GET` | `/api/v1/pipeline-templates/{template_id}` | Get template (full DAG) |
| `PUT` | `/api/v1/pipeline-templates/{template_id}` | Update template (nodes/edges/metadata) |
| `DELETE` | `/api/v1/pipeline-templates/{template_id}` | Delete template |
| `POST` | `/api/v1/pipeline-templates/{template_id}/clone` | Clone template |
| `POST` | `/api/v1/pipeline-templates/{template_id}/archive` | Archive template |
| `POST` | `/api/v1/pipeline-templates/{template_id}/validate` | Validate DAG |
| `GET` | `/api/v1/pipeline-templates/{template_id}/export` | Export as JSON |
| `POST` | `/api/v1/pipeline-templates/import` | Import from JSON |

#### Pipeline Runs (UPDATED)

| Method | Path | V2? | V3 Changes |
|--------|------|-----|------------|
| `POST` | `/api/v1/pipeline/runs` | ✅ | Now requires `template_id` in body |
| `GET` | `/api/v1/pipeline/runs` | ✅ | Filter by `template_id` |
| `GET` | `/api/v1/pipeline/runs/{run_id}` | ✅ | Returns `node_statuses`, `execution_layers`, `template_snapshot` |
| `DELETE` | `/api/v1/pipeline/runs/{run_id}` | ✅ | No change |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results` | ✅ | Results keyed by `node_id` instead of `stage` |
| `GET` | `/api/v1/pipeline/runs/{run_id}/results/{node_id}` | **NEW** | Get result for specific node |
| `POST` | `/api/v1/pipeline/runs/{run_id}/pause` | ✅ | No change |
| `POST` | `/api/v1/pipeline/runs/{run_id}/resume` | ✅ | No change |
| `POST` | `/api/v1/pipeline/runs/{run_id}/cancel` | ✅ | No change |
| `GET` | `/api/v1/pipeline/runs/{run_id}/export/html` | ✅ | No change |
| `GET` | `/api/v1/pipeline/runs/{run_id}/export/docx` | ✅ | No change |

#### WebSocket (UPDATED)

| Path | V3 Changes |
|------|------------|
| `WS /ws/pipeline/{run_id}` | New events: `layer.started`, `layer.completed`, `node.started`, `node.completed`, `node.failed`, `node.skipped`, `node.progress` |

#### Admin — LLM Profiles (No Change)

| Method | Path | V3 Changes |
|--------|------|------------|
| `GET` | `/api/v1/admin/llm-profiles` | No change |
| `POST` | `/api/v1/admin/llm-profiles` | No change |
| `GET` | `/api/v1/admin/llm-profiles/{id}` | No change |
| `PUT` | `/api/v1/admin/llm-profiles/{id}` | No change |
| `DELETE` | `/api/v1/admin/llm-profiles/{id}` | No change |
| `POST` | `/api/v1/admin/llm-profiles/{id}/set-default` | No change |
| `POST` | `/api/v1/admin/llm-profiles/{id}/test` | No change |

#### Admin — Agent Configs (Agent Catalog)

| Method | Path | V2? | V3 Changes |
|--------|------|-----|------------|
| `GET` | `/api/v1/admin/agent-configs` | ✅ | Now serves as **Agent Catalog** — agents not tied to stages |
| `POST` | `/api/v1/admin/agent-configs` | ✅ | `stage` field becomes optional (agents in catalog, placed in pipelines via nodes) |
| `GET` | `/api/v1/admin/agent-configs/{agent_id}` | ✅ | No change |
| `PUT` | `/api/v1/admin/agent-configs/{agent_id}` | ✅ | No change |
| `DELETE` | `/api/v1/admin/agent-configs/{agent_id}` | ✅ | No change |
| `POST` | `/api/v1/admin/agent-configs/{agent_id}/reset` | ✅ | No change |
| `POST` | `/api/v1/admin/agent-configs/reset-all` | ✅ | No change |

#### Admin — Stage Configs (DEPRECATED)

| Method | Path | V3 Status |
|--------|------|-----------|
| `GET` | `/api/v1/admin/stage-configs` | **DEPRECATED** — returns 410 Gone with migration message |
| All others | `/api/v1/admin/stage-configs/*` | **DEPRECATED** — returns 410 Gone |

#### Chat (No Change)

| Method | Path | V3 Changes |
|--------|------|------------|
| `GET` | `/api/v1/chat/profiles` | No change |
| `POST` | `/api/v1/chat/send` | No change |

---

## 15. Updated WebSocket Events

### Full Event List V3

```typescript
type WSEventType =
    // Run lifecycle
    | "run.started"
    | "run.completed"
    | "run.failed"
    | "run.paused"
    | "run.resumed"
    | "run.cancelled"

    // Layer events (NEW in V3)
    | "layer.started"
    | "layer.completed"

    // Node events (NEW in V3 — replaces stage.* and agent.*)
    | "node.started"
    | "node.completed"
    | "node.failed"
    | "node.skipped"
    | "node.progress"

    // Generic
    | "log"
```

### New Event Payloads

```json
// run.started (UPDATED — includes DAG info)
{
    "event": "run.started",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:00:00Z",
    "data": {
        "template_id": "auto-testing",
        "total_layers": 5,
        "total_nodes": 8,
        "layers": [
            ["__input__"],
            ["ingestion_agent_1"],
            ["tc_analyzer_1", "tc_writer_1", "tc_reviewer_1"],
            ["executor_1"],
            ["reporter_1"],
            ["__output__"]
        ]
    }
}

// layer.started (NEW)
{
    "event": "layer.started",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:01:00Z",
    "data": {
        "layer_index": 2,
        "nodes": ["tc_analyzer_1", "tc_writer_1", "tc_reviewer_1"],
        "parallel": true
    }
}

// node.started (NEW — replaces agent.started)
{
    "event": "node.started",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:01:01Z",
    "data": {
        "node_id": "tc_analyzer_1",
        "node_type": "agent",
        "label": "TC Analyzer",
        "agent_id": "tc_analyzer",
        "layer_index": 2
    }
}

// node.completed (NEW — replaces agent.completed)
{
    "event": "node.completed",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:02:30Z",
    "data": {
        "node_id": "tc_analyzer_1",
        "duration_seconds": 89.5,
        "output_preview": "{\"test_cases\": [...], \"coverage\": 95.0}",
        "has_full_results": true
    }
}

// node.failed (NEW — replaces agent.failed)
{
    "event": "node.failed",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:02:30Z",
    "data": {
        "node_id": "tc_writer_1",
        "error": "Timeout after 300s",
        "will_retry": true,
        "retry_attempt": 1
    }
}

// layer.completed (NEW)
{
    "event": "layer.completed",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:03:00Z",
    "data": {
        "layer_index": 2,
        "nodes": ["tc_analyzer_1", "tc_writer_1", "tc_reviewer_1"],
        "duration_seconds": 120.0,
        "all_succeeded": true
    }
}

// node.skipped (NEW)
{
    "event": "node.skipped",
    "run_id": "abc-123",
    "timestamp": "2025-01-20T10:01:00Z",
    "data": {
        "node_id": "tc_optimizer_1",
        "reason": "Node is disabled"
    }
}
```

---

## 16. Updated Frontend Pages & Components

### Route Map V3

| URL | Component | V2? | V3 Changes |
|-----|-----------|-----|------------|
| `/` | Redirect → `/pipelines` | ✅ (was `/pipeline`) | **Changed**: now redirects to pipeline list |
| `/pipelines` | `PipelineListPage` | **NEW** | Pipeline template list with create/clone/archive |
| `/pipelines/new` | `PipelineBuilderPage` | **NEW** | Visual builder for new pipeline |
| `/pipelines/{template_id}` | `PipelineBuilderPage` | **NEW** | Visual builder for existing pipeline |
| `/pipelines/{template_id}/run` | `PipelineRunPage` | **UPDATED** | Run pipeline with live DAG visualization |
| `/pipelines/{template_id}/runs` | `PipelineRunHistoryPage` | **NEW** | Run history for this template |
| `/pipeline` | _(redirect to `/pipelines`)_ | ✅ (V2) | **DEPRECATED** — redirect |
| `/chat` | `ChatPage` | ✅ | No change |
| `/admin/llm` | `LLMProfileList` | ✅ | No change |
| `/admin/agents` | `AgentList` | ✅ | Updated: now "Agent Catalog" — no stage filter |
| `/admin/stages` | _(removed)_ | ✅ (V2) | **REMOVED** — replaced by pipeline builder |

### New Components

| Component | File | Mô tả |
|-----------|------|-------|
| `PipelineListPage` | `app/pipelines/page.tsx` | Grid of pipeline template cards |
| `PipelineTemplateCard` | `components/pipelines/PipelineTemplateCard.tsx` | Card for a single template |
| `CreatePipelineDialog` | `components/pipelines/CreatePipelineDialog.tsx` | Modal to create new template |
| `PipelineBuilder` | `components/pipeline-builder/PipelineBuilder.tsx` | React Flow canvas + sidebar + panels |
| `AgentCatalogSidebar` | `components/pipeline-builder/AgentCatalogSidebar.tsx` | Draggable agent list |
| `AgentNode` | `components/pipeline-builder/nodes/AgentNode.tsx` | Custom React Flow node |
| `InputNode` | `components/pipeline-builder/nodes/InputNode.tsx` | Input source node |
| `OutputNode` | `components/pipeline-builder/nodes/OutputNode.tsx` | Output sink node |
| `NodePropertiesPanel` | `components/pipeline-builder/NodePropertiesPanel.tsx` | Right panel: node config |
| `BuilderToolbar` | `components/pipeline-builder/BuilderToolbar.tsx` | Save, Run, Undo, Redo, Validate buttons |
| `ValidationPanel` | `components/pipeline-builder/ValidationPanel.tsx` | DAG validation status display |
| `PipelineRunView` | `components/pipeline/PipelineRunView.tsx` | Live DAG visualization during run |

### Updated Components

| Component | File | V3 Changes |
|-----------|------|------------|
| `PipelinePage` | `components/pipeline/PipelinePage.tsx` | Now shows `PipelineRunView` (DAG) instead of stage-based progress |
| `PipelineProgress` | `components/pipeline/PipelineProgress.tsx` | Updated: shows node-based progress instead of stage-based |
| `ResultsViewer` | `components/pipeline/ResultsViewer.tsx` | Results per-node instead of per-stage |
| `Sidebar` | `components/layout/Sidebar.tsx` | Updated: "Pipelines" replaces "Pipeline", remove "Stages" |
| `AgentList` | `components/admin/agents/AgentList.tsx` | Now "Agent Catalog" — no stage grouping |

### New Hooks

| Hook | File | Mô tả |
|------|------|-------|
| `usePipelineTemplates` | `hooks/usePipelineTemplates.ts` | TanStack Query hooks for template CRUD |
| `usePipelineTemplate` | `hooks/usePipelineTemplates.ts` | Get single template |
| `useCreateTemplate` | `hooks/usePipelineTemplates.ts` | Create mutation |
| `useUpdateTemplate` | `hooks/usePipelineTemplates.ts` | Update mutation (save from builder) |
| `useCloneTemplate` | `hooks/usePipelineTemplates.ts` | Clone mutation |
| `useDeleteTemplate` | `hooks/usePipelineTemplates.ts` | Delete mutation |
| `useValidateTemplate` | `hooks/usePipelineTemplates.ts` | Validate DAG |
| `useExportTemplate` | `hooks/usePipelineTemplates.ts` | Export as JSON |
| `useImportTemplate` | `hooks/usePipelineTemplates.ts` | Import from JSON |

### New Zustand Stores

| Store | File | Mô tả |
|-------|------|-------|
| `useBuilderStore` | `store/builderStore.ts` | Pipeline builder state (nodes, edges, undo/redo, validation) |

### Updated Zustand Stores

| Store | File | V3 Changes |
|-------|------|------------|
| `usePipelineStore` | `store/pipelineStore.ts` | `nodeStatuses` replaces `agentStatuses`; `currentNode` replaces `currentStage`; add `executionLayers` |

### Updated Types

```typescript
// types/index.ts — V3 additions/changes

// ── Pipeline Template types ──

interface PipelineNodeConfig {
    node_id: string;
    node_type: 'input' | 'output' | 'agent' | 'pure_python';
    agent_id?: string;
    label: string;
    description: string;
    position_x: number;
    position_y: number;
    timeout_seconds: number;
    retry_count: number;
    enabled: boolean;
    config_overrides: Record<string, any>;
}

interface PipelineEdgeConfig {
    edge_id: string;
    source_node_id: string;
    target_node_id: string;
    source_handle?: string;
    target_handle?: string;
    label?: string;
    animated: boolean;
}

interface PipelineTemplate {
    id: string;
    template_id: string;
    name: string;
    description: string;
    version: number;
    nodes: PipelineNodeConfig[];
    edges: PipelineEdgeConfig[];
    is_builtin: boolean;
    is_archived: boolean;
    tags: string[];
    node_count: number;
    edge_count: number;
    created_at: string;
    updated_at: string;
}

interface PipelineTemplateListItem {
    id: string;
    template_id: string;
    name: string;
    description: string;
    version: number;
    is_builtin: boolean;
    is_archived: boolean;
    tags: string[];
    node_count: number;
    edge_count: number;
    last_run_at?: string;
    last_run_status?: string;
    created_at: string;
    updated_at: string;
}

interface PipelineTemplateCreate {
    template_id: string;
    name: string;
    description?: string;
    nodes?: PipelineNodeConfig[];
    edges?: PipelineEdgeConfig[];
    tags?: string[];
}

interface PipelineTemplateUpdate {
    name?: string;
    description?: string;
    nodes?: PipelineNodeConfig[];
    edges?: PipelineEdgeConfig[];
    tags?: string[];
}

interface DAGValidationResult {
    is_valid: boolean;
    errors: string[];
    warnings: string[];
    execution_layers: string[][];
    total_layers: number;
    total_nodes: number;
    estimated_parallel_speedup?: number;
}

// ── Updated Pipeline Run types ──

interface PipelineRun {
    id: string;
    run_id: string;
    template_id: string;            // NEW in V3
    document_name: string;
    status: PipelineStatus;
    current_node?: string;           // Changed: was current_stage
    completed_nodes: string[];       // Changed: was completed_stages
    failed_nodes: string[];          // NEW in V3
    node_statuses: Record<string, string>;  // NEW in V3
    execution_layers: string[][];    // NEW in V3
    duration_seconds?: number;
    error_message?: string;
    created_at: string;
    started_at?: string;
    completed_at?: string;
    paused_at?: string;
    resumed_at?: string;
}

// ── Updated WS event types ──

type WSEventType =
    | 'run.started' | 'run.completed' | 'run.failed'
    | 'run.paused' | 'run.resumed' | 'run.cancelled'
    | 'layer.started' | 'layer.completed'       // NEW in V3
    | 'node.started' | 'node.completed'          // NEW in V3 (replaces agent.*)
    | 'node.failed' | 'node.skipped'             // NEW in V3
    | 'node.progress'                             // NEW in V3
    | 'log';

// ── Updated Agent Config (stage now optional) ──

interface AgentConfig {
    id: string;
    agent_id: string;
    display_name: string;
    stage?: string;                 // Changed: now optional (catalog item)
    role: string;
    goal: string;
    backstory: string;
    llm_profile_id?: string;
    enabled: boolean;
    verbose: boolean;
    max_iter: number;
    is_custom: boolean;
    created_at: string;
    updated_at: string;
}

// ── Deprecated ──
// StageConfig, StageConfigCreate, StageConfigUpdate, StageReorderRequest
// → Removed (replaced by pipeline template nodes/edges)
```

---

## 17. Updated Database Schema (MongoDB)

### Collections

```
auto_at (database)
├── llm_profiles            — LLM provider configurations (no change)
├── agent_configs           — Agent catalog (stage field now optional)
├── pipeline_templates      — NEW: DAG definitions with embedded nodes + edges
├── pipeline_runs           — UPDATED: references template_id, tracks node_statuses
├── pipeline_results        — UPDATED: per-node results (node_id replaces stage)
└── stage_configs           — DEPRECATED (kept for migration, will be removed)
```

### Indexes

```javascript
// llm_profiles (no change)
db.llm_profiles.createIndex({ "name": 1 }, { unique: true })
db.llm_profiles.createIndex({ "is_default": 1 })

// agent_configs (minor change: stage index now sparse)
db.agent_configs.createIndex({ "agent_id": 1 }, { unique: true })
db.agent_configs.createIndex({ "stage": 1 }, { sparse: true })  // sparse: stage now optional

// pipeline_templates (NEW)
db.pipeline_templates.createIndex({ "template_id": 1 }, { unique: true })
db.pipeline_templates.createIndex({ "is_archived": 1 })
db.pipeline_templates.createIndex({ "tags": 1 })
db.pipeline_templates.createIndex({ "created_at": -1 })

// pipeline_runs (UPDATED)
db.pipeline_runs.createIndex({ "run_id": 1 }, { unique: true })
db.pipeline_runs.createIndex({ "template_id": 1 })  // NEW: filter by template
db.pipeline_runs.createIndex({ "status": 1 })
db.pipeline_runs.createIndex({ "created_at": -1 })

// pipeline_results (UPDATED)
db.pipeline_results.createIndex({ "run_id": 1, "node_id": 1 })  // Changed: node_id replaces stage
db.pipeline_results.createIndex({ "run_id": 1 })
```

---

## 18. Updated Environment Variables

### Backend — `.env.example` (V3)

```bash
# ── App ──
APP_ENV=development
APP_VERSION=3.0.0
DEBUG=true
MOCK_PIPELINE=false

# ── Server ──
HOST=0.0.0.0
PORT=8000
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# ── MongoDB ──
MONGODB_URI=mongodb://admin:changeme@localhost:27017
MONGODB_DB_NAME=auto_at

# ── LLM Providers ──
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434

# ── File Upload ──
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=50

# ── Pipeline ──
PIPELINE_TIMEOUT_SECONDS=3600
PAUSE_TIMEOUT_SECONDS=1800
MAX_CONCURRENT_RUNS=3          # NEW: limit concurrent pipeline runs
NODE_DEFAULT_TIMEOUT=300       # NEW: default timeout per node
MAX_PARALLEL_NODES=10          # NEW: max nodes running in parallel per layer

# ── Export ──
REPORT_TEMPLATE_DIR=./app/templates

# ── Logging ──
LOG_LEVEL=INFO
```

### Frontend — `.env.local.example` (V3)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_APP_VERSION=3.0.0
```

---

## 19. Updated Folder Structure

```
auto-at/
├── backend/
│   ├── app/
│   │   ├── main.py                        # FastAPI app entry + lifespan
│   │   ├── config.py                      # +MAX_CONCURRENT_RUNS, +NODE_DEFAULT_TIMEOUT, +MAX_PARALLEL_NODES
│   │   │
│   │   ├── api/v1/
│   │   │   ├── __init__.py
│   │   │   ├── deps.py
│   │   │   ├── pipeline.py               # UPDATED: requires template_id, returns node-based results
│   │   │   ├── pipeline_templates.py     # NEW: template CRUD, clone, archive, validate, export/import
│   │   │   ├── llm_profiles.py           # No change
│   │   │   ├── agent_configs.py          # Updated: stage field optional
│   │   │   ├── stage_configs.py          # DEPRECATED: returns 410 Gone
│   │   │   ├── chat.py                   # No change
│   │   │   └── websocket.py              # +layer.*, +node.* events
│   │   │
│   │   ├── core/
│   │   │   ├── llm_factory.py            # No change
│   │   │   ├── agent_factory.py          # No change
│   │   │   ├── pipeline_runner.py        # DEPRECATED: kept for reference, replaced by dag_pipeline_runner
│   │   │   ├── dag_pipeline_runner.py    # NEW: DAG-based execution engine
│   │   │   ├── dag_resolver.py           # NEW: DAG validation + topological sort + layer computation
│   │   │   └── signal_manager.py         # No change
│   │   │
│   │   ├── crews/
│   │   │   ├── __init__.py
│   │   │   ├── base_crew.py              # No change
│   │   │   ├── dynamic_crew.py           # No change (used by agent nodes)
│   │   │   ├── ingestion_crew.py         # No change (used by pure_python nodes)
│   │   │   ├── testcase_crew.py          # Kept for reference/builtin templates
│   │   │   ├── execution_crew.py         # Kept for reference/builtin templates
│   │   │   └── reporting_crew.py         # Kept for reference/builtin templates
│   │   │
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── export_service.py         # Updated: per-node results instead of per-stage
│   │   │   └── docx_builder.py           # Minor updates for node-based data
│   │   │
│   │   ├── templates/
│   │   │   └── report.html.j2            # Updated: node-based results
│   │   │
│   │   ├── agents/                       # Same as V2
│   │   │   ├── ingestion/
│   │   │   ├── testcase/
│   │   │   ├── execution/
│   │   │   └── reporting/
│   │   │
│   │   ├── tasks/                        # Same as V2
│   │   │   ├── testcase_tasks.py
│   │   │   ├── execution_tasks.py
│   │   │   └── reporting_tasks.py
│   │   │
│   │   ├── tools/                        # Same as V2
│   │   │   ├── document_parser.py
│   │   │   ├── text_chunker.py
│   │   │   ├── api_runner.py
│   │   │   └── config_loader.py
│   │   │
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── database.py              # No change
│   │   │   ├── models.py                # +PipelineTemplateDocument, +PipelineNodeConfig, +PipelineEdgeConfig
│   │   │   │                            #  Updated: PipelineRunDocument, PipelineResultDocument
│   │   │   ├── crud.py                  # +template CRUD functions, updated run/result functions
│   │   │   └── seed.py                  # +seed default pipeline template (migrated from stages)
│   │   │
│   │   └── schemas/
│   │       ├── __init__.py
│   │       ├── llm_profile.py           # No change
│   │       ├── agent_config.py          # stage field optional
│   │       ├── stage_config.py          # DEPRECATED
│   │       ├── pipeline.py              # +new WSEventType values, updated PipelineRunResponse
│   │       ├── pipeline_template.py     # NEW: template schemas
│   │       └── pipeline_io.py           # No change
│   │
│   ├── scripts/
│   │   └── migrate_v2_to_v3.py          # NEW: migration script
│   │
│   ├── tests/
│   ├── uploads/
│   ├── pyproject.toml                   # No new backend deps needed (using existing)
│   ├── uv.lock
│   ├── Dockerfile
│   └── README.md
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── globals.css
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx                 # Redirect → /pipelines
│   │   │   ├── providers.tsx
│   │   │   ├── pipelines/               # NEW
│   │   │   │   ├── page.tsx             # Pipeline template list
│   │   │   │   ├── new/
│   │   │   │   │   └── page.tsx         # New pipeline builder (blank)
│   │   │   │   └── [templateId]/
│   │   │   │       ├── page.tsx         # Pipeline builder (edit existing)
│   │   │   │       ├── run/
│   │   │   │       │   └── page.tsx     # Run pipeline + live DAG view
│   │   │   │       └── runs/
│   │   │   │           └── page.tsx     # Run history for template
│   │   │   ├── pipeline/
│   │   │   │   ├── layout.tsx           # DEPRECATED: redirect to /pipelines
│   │   │   │   └── page.tsx             # DEPRECATED: redirect to /pipelines
│   │   │   ├── admin/
│   │   │   │   ├── layout.tsx           # Remove "Stages" tab
│   │   │   │   ├── agents/page.tsx      # Now "Agent Catalog"
│   │   │   │   ├── llm/page.tsx         # No change
│   │   │   │   └── stages/page.tsx      # DEPRECATED: shows migration message
│   │   │   ├── chat/
│   │   │   │   ├── layout.tsx
│   │   │   │   └── page.tsx
│   │   │
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   └── Sidebar.tsx          # Updated: "Pipelines" link, remove "Stages"
│   │   │   ├── chat/
│   │   │   │   └── ChatPage.tsx
│   │   │   ├── pipelines/                # NEW
│   │   │   │   ├── PipelineListPage.tsx
│   │   │   │   ├── PipelineTemplateCard.tsx
│   │   │   │   └── CreatePipelineDialog.tsx
│   │   │   ├── pipeline-builder/          # NEW
│   │   │   │   ├── PipelineBuilder.tsx    # Main builder with React Flow
│   │   │   │   ├── AgentCatalogSidebar.tsx
│   │   │   │   ├── NodePropertiesPanel.tsx
│   │   │   │   ├── BuilderToolbar.tsx
│   │   │   │   ├── ValidationPanel.tsx
│   │   │   │   └── nodes/
│   │   │   │       ├── AgentNode.tsx
│   │   │   │       ├── InputNode.tsx
│   │   │   │       └── OutputNode.tsx
│   │   │   ├── pipeline/
│   │   │   │   ├── PipelinePage.tsx     # UPDATED: uses PipelineRunView
│   │   │   │   ├── PipelineRunView.tsx  # NEW: live DAG visualization
│   │   │   │   ├── PipelineControls.tsx # No change
│   │   │   │   ├── ExportButtons.tsx    # No change
│   │   │   │   ├── DocumentUpload.tsx   # No change
│   │   │   │   ├── LLMProfileSelector.tsx # No change
│   │   │   │   ├── PipelineProgress.tsx # UPDATED: node-based progress
│   │   │   │   ├── ResultsViewer.tsx    # UPDATED: per-node results
│   │   │   │   └── RunHistory.tsx       # UPDATED: grouped by template
│   │   │   ├── admin/
│   │   │   │   ├── agents/
│   │   │   │   │   ├── AgentList.tsx    # Updated: "Agent Catalog" mode
│   │   │   │   │   ├── AgentGroupSection.tsx  # Updated: group by category (not stage)
│   │   │   │   │   ├── AgentCard.tsx
│   │   │   │   │   ├── AgentDialog.tsx
│   │   │   │   │   └── AddAgentDialog.tsx
│   │   │   │   ├── llm/
│   │   │   │   │   ├── LLMProfileList.tsx
│   │   │   │   │   ├── LLMProfileCard.tsx
│   │   │   │   │   └── LLMProfileDialog.tsx
│   │   │   │   └── stages/              # DEPRECATED
│   │   │   │       └── DeprecatedNotice.tsx
│   │   │   └── ui/                      # No change
│   │   │
│   │   ├── hooks/
│   │   │   ├── useAgentConfigs.ts       # Minor: stage filter now optional
│   │   │   ├── useLLMProfiles.ts        # No change
│   │   │   ├── usePipeline.ts           # Updated: template_id in run creation
│   │   │   ├── usePipelineTemplates.ts  # NEW: template CRUD hooks
│   │   │   ├── useStageConfigs.ts       # DEPRECATED
│   │   │   └── usePipelineWebSocket.ts  # No change (still deprecated from V2)
│   │   │
│   │   ├── store/
│   │   │   ├── pipelineStore.ts         # Updated: nodeStatuses, currentNode, executionLayers
│   │   │   └── builderStore.ts          # NEW: pipeline builder state
│   │   │
│   │   ├── lib/
│   │   │   ├── api.ts                   # +pipelineTemplatesApi namespace
│   │   │   ├── wsManager.ts             # Updated: handle node.* events
│   │   │   ├── queryClient.ts
│   │   │   └── utils.ts
│   │   │
│   │   └── types/
│   │       └── index.ts                 # +PipelineTemplate types, updated PipelineRun, updated WSEventType
│   │
│   ├── public/
│   ├── package.json                     # +@xyflow/react (remove @dnd-kit/*)
│   ├── next.config.ts
│   ├── tsconfig.json
│   ├── Dockerfile
│   └── README.md
│
├── Flow/
│   ├── PLAN_V1.md
│   ├── PLAN_V2.md
│   ├── PLAN_V3.md                       # ← file này
│   └── FlowChart.md
│
└── docker-compose.yml
```

---

## 20. Migration Guide (V2 → V3)

### Backend Migration Steps

#### Step 1: New Files

```bash
# Create new core files
touch backend/app/core/dag_resolver.py
touch backend/app/core/dag_pipeline_runner.py
touch backend/app/api/v1/pipeline_templates.py
touch backend/app/schemas/pipeline_template.py
touch backend/scripts/migrate_v2_to_v3.py
```

#### Step 2: Data Migration Script

```python
# scripts/migrate_v2_to_v3.py

"""
Migrate V2 stage_configs + agent_configs into a V3 pipeline template.
Creates a default "Auto Testing" pipeline template from existing stages.
"""

import asyncio
from datetime import datetime, timezone
from app.db.database import init_db, close_db
from app.db.models import (
    PipelineTemplateDocument,
    PipelineNodeConfig,
    PipelineEdgeConfig,
    StageConfigDocument,
    AgentConfigDocument,
    NodeType,
)


async def migrate():
    await init_db()

    print("=== V2 → V3 Migration ===")

    # 1. Load existing stages
    stages = await StageConfigDocument.find(
        StageConfigDocument.enabled == True
    ).sort("+order").to_list()

    if not stages:
        print("No stages found. Skipping migration.")
        return

    print(f"Found {len(stages)} stages to migrate")

    # 2. Build nodes and edges
    nodes = []
    edges = []
    y_offset = 0
    y_spacing = 200
    x_center = 400

    # INPUT node
    input_node = PipelineNodeConfig(
        node_id="__input__",
        node_type=NodeType.INPUT,
        label="📥 Input",
        description="Pipeline entry point",
        position_x=x_center,
        position_y=y_offset,
    )
    nodes.append(input_node)
    y_offset += y_spacing

    prev_stage_node_ids = ["__input__"]

    for stage in stages:
        # Load agents for this stage
        agents = await AgentConfigDocument.find(
            AgentConfigDocument.stage == stage.stage_id,
            AgentConfigDocument.enabled == True,
        ).to_list()

        if not agents:
            # Stage with no agents: create a single node for the stage
            node_id = f"{stage.stage_id}_node"
            crew_type = stage.crew_type
            node_type = NodeType.PURE_PYTHON if crew_type == "pure_python" else NodeType.AGENT
            node = PipelineNodeConfig(
                node_id=node_id,
                node_type=node_type,
                agent_id=stage.stage_id if node_type == NodeType.PURE_PYTHON else None,
                label=stage.display_name,
                description=stage.description,
                position_x=x_center,
                position_y=y_offset,
                timeout_seconds=stage.timeout_seconds,
            )
            nodes.append(node)

            # Edge from previous stage nodes
            for prev_id in prev_stage_node_ids:
                edges.append(PipelineEdgeConfig(
                    edge_id=f"edge-{prev_id}-{node_id}",
                    source_node_id=prev_id,
                    target_node_id=node_id,
                ))

            prev_stage_node_ids = [node_id]
        else:
            # Stage with agents: create a node per agent
            stage_node_ids = []
            x_start = x_center - (len(agents) - 1) * 100
            for i, agent in enumerate(agents):
                node_id = f"{agent.agent_id}_1"
                node_type = NodeType.PURE_PYTHON if stage.crew_type == "pure_python" else NodeType.AGENT
                node = PipelineNodeConfig(
                    node_id=node_id,
                    node_type=node_type,
                    agent_id=agent.agent_id,
                    label=agent.display_name,
                    description=agent.role[:100] if agent.role else "",
                    position_x=x_start + i * 200,
                    position_y=y_offset,
                    timeout_seconds=stage.timeout_seconds,
                )
                nodes.append(node)
                stage_node_ids.append(node_id)

                # Edges from all previous stage nodes to this agent
                for prev_id in prev_stage_node_ids:
                    edges.append(PipelineEdgeConfig(
                        edge_id=f"edge-{prev_id}-{node_id}",
                        source_node_id=prev_id,
                        target_node_id=node_id,
                    ))

            prev_stage_node_ids = stage_node_ids

        y_offset += y_spacing

    # OUTPUT node
    output_node = PipelineNodeConfig(
        node_id="__output__",
        node_type=NodeType.OUTPUT,
        label="📤 Output",
        description="Pipeline final output",
        position_x=x_center,
        position_y=y_offset,
    )
    nodes.append(output_node)

    # Edges from last stage nodes to OUTPUT
    for prev_id in prev_stage_node_ids:
        edges.append(PipelineEdgeConfig(
            edge_id=f"edge-{prev_id}-__output__",
            source_node_id=prev_id,
            target_node_id="__output__",
        ))

    # 3. Create default pipeline template
    template = PipelineTemplateDocument(
        template_id="auto-testing",
        name="Auto Testing (Migrated from V2)",
        description="Default pipeline migrated from V2 stage-based configuration",
        version=1,
        nodes=nodes,
        edges=edges,
        is_builtin=True,
        tags=["migrated", "default"],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Check if already exists
    existing = await PipelineTemplateDocument.find_one(
        PipelineTemplateDocument.template_id == "auto-testing"
    )
    if existing:
        print("Template 'auto-testing' already exists. Updating...")
        existing.nodes = nodes
        existing.edges = edges
        existing.updated_at = datetime.now(timezone.utc)
        existing.version += 1
        await existing.save()
    else:
        await template.save()

    print(f"Created pipeline template 'auto-testing' with {len(nodes)} nodes and {len(edges)} edges")

    # 4. Make agent_configs.stage optional (update existing agents)
    print("Updating agent_configs: stage field now optional...")
    # No actual data change needed — just the schema allows None now

    # 5. Mark stage_configs as deprecated
    print("Note: stage_configs collection is now deprecated. It will be ignored by V3.")
    print("You can drop it manually after confirming migration: db.stage_configs.drop()")

    await close_db()
    print("=== Migration Complete ===")


if __name__ == "__main__":
    asyncio.run(migrate())
```

#### Step 3: Update Seed Script

```python
# db/seed.py — V3 additions

DEFAULT_PIPELINE_TEMPLATE = {
    "template_id": "auto-testing",
    "name": "Auto Testing",
    "description": "Default automated testing pipeline: Ingestion → Test Cases → Execution → Reporting",
    "version": 1,
    "is_builtin": True,
    "tags": ["default", "testing"],
    "nodes": [
        {
            "node_id": "__input__",
            "node_type": "input",
            "label": "📥 Input",
            "description": "Upload document for testing",
            "position_x": 400,
            "position_y": 0,
        },
        {
            "node_id": "ingestion_1",
            "node_type": "pure_python",
            "agent_id": "ingestion_agent",
            "label": "Document Ingestion",
            "description": "Parse and extract requirements",
            "position_x": 400,
            "position_y": 150,
            "timeout_seconds": 120,
        },
        # ... (testcase agents, execution agents, reporting agents)
        {
            "node_id": "__output__",
            "node_type": "output",
            "label": "📤 Output",
            "description": "Final test report",
            "position_x": 400,
            "position_y": 900,
        },
    ],
    "edges": [
        {"edge_id": "e-input-ingest", "source_node_id": "__input__", "target_node_id": "ingestion_1"},
        # ... (edges connecting all nodes)
    ],
}
```

### Frontend Migration Steps

#### Step 1: Install Dependencies

```bash
cd frontend
npm install @xyflow/react
npm uninstall @dnd-kit/core @dnd-kit/sortable @dnd-kit/utilities  # no longer needed
```

#### Step 2: Create New Directories

```bash
mkdir -p src/app/pipelines/new
mkdir -p src/app/pipelines/\[templateId\]/run
mkdir -p src/app/pipelines/\[templateId\]/runs
mkdir -p src/components/pipelines
mkdir -p src/components/pipeline-builder/nodes
```

#### Step 3: Update Routing

- `page.tsx` (root): redirect to `/pipelines` instead of `/pipeline`
- `Sidebar.tsx`: update nav links
- Deprecate `/pipeline` route → redirect to `/pipelines`
- Deprecate `/admin/stages` route → show migration notice

---

## 21. Implementation Phases

### Phase 15 – DAG Resolver & Pipeline Template Model `~2 ngày` ✅

- [x] Create `core/dag_resolver.py` — DAGResolver class (validate, topo sort, layer computation)
- [x] Create `db/models.py` additions — PipelineTemplateDocument, PipelineNodeConfig, PipelineEdgeConfig, NodeType
- [x] Update `db/models.py` — PipelineRunDocument (add template_id, node_statuses, execution_layers)
- [x] Update `db/models.py` — PipelineResultDocument (node_id replaces stage)
- [x] Create `schemas/pipeline_template.py` — all template schemas
- [x] Update `schemas/pipeline.py` — new WSEventType values, updated PipelineRunResponse
- [x] Create `db/crud.py` additions — template CRUD functions
- [x] Update `db/seed.py` — seed default "auto-testing" pipeline template
- [x] Tests: DAG validation (cycles, orphans, missing INPUT/OUTPUT), topological sort, layer computation

### Phase 16 – DAG Pipeline Runner `~2.5 ngày` ✅

- [x] Create `core/dag_pipeline_runner.py` — DAGPipelineRunner class
- [x] Implement layer-by-layer parallel execution (`asyncio.gather`)
- [x] Implement input merging strategy (single parent pass-through, multi-parent namespace merge)
- [x] Integrate signal checking (pause/resume/cancel) between layers
- [x] Implement node retry logic (exponential back-off, retry_count per node)
- [x] Update `api/v1/pipeline.py` — add `POST /pipeline/runs` V3 endpoint using DAGPipelineRunner
- [x] Update WebSocket handler — emit node.* and layer.* events via progress_callback
- [x] Deprecate `core/pipeline_runner.py` (kept for reference, deprecation comment added)
- [x] Update `db/crud.py` — add `update_pipeline_run`, `save_node_result`, `create_dag_run` V3 helpers
- [x] Tests: simple DAG execution, parallel execution, failure handling, cancel signal, pause/resume, retry logic (70 tests, all passing)

### Phase 17 – Pipeline Template CRUD API `~1.5 ngày` ✅

- [x] Create `api/v1/pipeline_templates.py` — full CRUD router
- [x] Implement clone, archive, validate endpoints
- [x] Implement export/import (JSON) endpoints
- [x] Deprecate `api/v1/stage_configs.py` — return 410 Gone
- [x] Update `agent_configs.py` — stage field optional
- [x] Register new router in `main.py`
- [x] Tests: template CRUD, clone, validate, export/import (31 tests, all passing)

### Phase 18 – Frontend: Pipeline List & Builder Setup `~2 ngày` ✅

- [x] Install `@xyflow/react`, uninstall `@dnd-kit/*`
- [x] Create `/pipelines` route + `PipelineListPage` component
- [x] Create `PipelineTemplateCard` component
- [x] Create `CreatePipelineDialog` component
- [x] Create `hooks/usePipelineTemplates.ts`
- [x] Update `lib/api.ts` — add `pipelineTemplatesApi` namespace
- [x] Update `Sidebar.tsx` — "Pipelines" link, remove "Stages"
- [x] Update root redirect to `/pipelines`
- [x] Update `types/index.ts` — new types

### Phase 19 – Frontend: Visual Pipeline Builder `~3 ngày` ✅

- [x] Create `store/builderStore.ts` — Zustand store for builder state
- [x] Create `PipelineBuilder.tsx` — main React Flow component
- [x] Create `AgentCatalogSidebar.tsx` — draggable agent list
- [x] Create `nodes/AgentNode.tsx` — custom agent node with handles
- [x] Create `nodes/InputNode.tsx` — input source node
- [x] Create `nodes/OutputNode.tsx` — output sink node
- [x] Create `NodePropertiesPanel.tsx` — right panel for node config
- [x] Create `BuilderToolbar.tsx` — save, run, undo, redo, validate
- [x] Create `ValidationPanel.tsx` — DAG validation status
- [x] Implement drag-from-catalog-to-canvas functionality
- [x] Implement edge drawing (drag from output handle to input handle)
- [x] Implement undo/redo
- [x] Implement client-side cycle detection
- [x] Create `/pipelines/new/page.tsx` and `/pipelines/[templateId]/page.tsx`
- [x] Create `components/pipeline/PipelineRunView.tsx` — live read-only DAG visualization
- [x] Update `store/pipelineStore.ts` — add `nodeStatuses` + WS node event handlers

### Phase 20 – Frontend: Pipeline Run with DAG Visualization `~2 ngày` ✅

- [x] Create `PipelineRunView.tsx` — live DAG visualization during run
- [x] Update `pipelineStore.ts` — nodeStatuses, currentNode, executionLayers, activeTemplateId; handle layer.started/layer.completed events
- [x] Update `wsManager.ts` — handle node.* and layer.* events; mark run.cancelled as terminal
- [x] Update `PipelinePage.tsx` — show PipelineRunView when V3 DAG run is active (isV3Run flag); load activeTemplate via usePipelineTemplate
- [x] Update `PipelineProgress.tsx` — added NodeLayerProgress component for node-based progress with execution layers; V3 props optional (backward compat)
- [x] Update `ResultsViewer.tsx` — per-node results display via new "Nodes" tab (V3 only); NodeResultCard component; visibleTabs logic
- [x] Create `/pipelines/[templateId]/run/page.tsx` — PipelineRunPage with DAG view, node progress, log panel, WS rehydration
- [x] Create `/pipelines/[templateId]/runs/page.tsx` — PipelineRunHistoryPage with paginated run list, status badges
- [x] Add `useStartDagPipeline` hook in `usePipeline.ts` — V3 template-based run mutation
- [x] Add `pipelineApi.createRun` in `api.ts` — POST /pipeline/runs (V3)
- [x] Add `pipelineApi.getNodeResult` in `api.ts` — GET /pipeline/runs/:id/results/:nodeId
- [x] Extend `PipelineRunResponse` type with V3 DAG fields (node_statuses, execution_layers, current_node, etc.)
- [x] Add `PipelineNodeResult` interface to `types/index.ts`
- [x] Create `components/pipeline/PipelineRunPage.tsx` — full V3 run page component
- [x] Create `components/pipeline/PipelineRunHistoryPage.tsx` — run history component

### Phase 21 – Migration & Polish `~1.5 ngày` ✅

- [x] Create `scripts/migrate_v2_to_v3.py`
- [x] Run migration on dev data
- [x] Deprecate `/admin/stages` page → show migration notice
- [x] Deprecate `/pipeline` route → redirect to `/pipelines`
- [x] Update `backend/README.md` and `frontend/README.md` for V3
- [x] Update Docker files if needed
- [x] Smoke test: create template → build DAG → run → view live progress → export report
- [x] Error handling: invalid DAG save, orphan nodes warning, concurrent runs limit
- [x] Loading states and toast notifications for new actions

---

### Phase Timeline Summary

| Phase | Feature | Estimated | Depends On |
|-------|---------|-----------|------------|
| Phase 15 | DAG Resolver + Models | ~2 ngày | V2 complete |
| Phase 16 | DAG Pipeline Runner | ~2.5 ngày | Phase 15 |
| Phase 17 | Template CRUD API | ~1.5 ngày | Phase 15 |
| Phase 18 | FE: Pipeline List + Setup | ~2 ngày | Phase 17 |
| Phase 19 | FE: Visual Pipeline Builder | ~3 ngày | Phase 18 |
| Phase 20 | FE: Run with DAG Viz | ~2 ngày | Phase 16 + 19 |
| Phase 21 | Migration & Polish | ~1.5 ngày | All above |
| **Total** | | **~14.5 ngày** | |

> **Thứ tự ưu tiên:**
>
> ```
> Phase 15 ──→ Phase 16 ──→ Phase 20 ──→ Phase 21
>     │                         ↑
>     └──→ Phase 17 ──→ Phase 18 ──→ Phase 19 ──┘
> ```
>
> Phase 15 (Models) phải xong trước.
> Phase 16 (Runner) và Phase 17 (API) có thể **chạy song song** nếu 2 devs.
> Phase 18-19 (Frontend) phụ thuộc Phase 17 API.
> Phase 20 phụ thuộc cả Phase 16 (runner) và Phase 19 (builder).

---

## 22. Updated Dependencies

### Backend `pyproject.toml` (V3)

```toml
[project]
name = "auto-at-backend"
version = "0.3.0"
requires-python = ">=3.11"
dependencies = [
    # ── Web framework ──
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "python-multipart>=0.0.9",

    # ── Database (MongoDB) ──
    "motor>=3.6.0",
    "beanie>=1.27.0",

    # ── Schema validation ──
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",

    # ── Multi-agent ──
    "crewai>=1.0.0",
    "lancedb==0.30.0",

    # ── LLM ──
    "litellm>=1.50.0",

    # ── Document parsing ──
    "pdfplumber>=0.11.0",
    "python-docx>=1.1.0",
    "openpyxl>=3.1.0",

    # ── Report export ──
    "jinja2>=3.1.0",

    # ── HTTP client ──
    "httpx>=0.27.0",

    # ── Security & utils ──
    "cryptography>=42.0.0",
    "python-dotenv>=1.0.0",
    "aiofiles>=23.0.0",
]

[dependency-groups]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]
```

> **Note:** No new backend dependencies needed for V3.
> DAG resolution uses Python stdlib (`collections.deque`).
> Parallel execution uses `asyncio.gather`.

### Frontend `package.json` (V3)

```json
{
    "dependencies": {
        "next": "^15.3.3",
        "react": "^19.0.0",
        "react-dom": "^19.0.0",
        "@tanstack/react-query": "^5.80.0",
        "zustand": "^5.0.0",
        "react-hook-form": "^7.54.0",
        "zod": "^3.24.0",
        "@hookform/resolvers": "^4.1.0",
        "axios": "^1.9.0",
        "lucide-react": "^0.513.0",
        "tailwindcss": "^4.1.8",
        "tailwind-merge": "^3.0.0",
        "clsx": "^2.1.0",
        "@xyflow/react": "^12.6.0"
    }
}
```

### Dependency Diff (V2 → V3)

| Package | V2 | V3 | Notes |
|---------|----|----|-------|
| `@dnd-kit/core` | ✅ | ❌ Removed | No longer needed — React Flow handles all DnD |
| `@dnd-kit/sortable` | ✅ | ❌ Removed | Replaced by React Flow |
| `@dnd-kit/utilities` | ✅ | ❌ Removed | Replaced by React Flow |
| `@xyflow/react` | — | ✅ Added | Visual DAG builder + live pipeline visualization |

---

> **Tổng thời gian ước tính V3:** ~14.5 ngày làm việc (1 dev)
>
> **Tổng thời gian V1 + V2 + V3:** ~12 + ~13 + ~14.5 = **~39.5 ngày**
>
> Bắt đầu từ Phase nào? → Gõ `/start phase-15` 🚀