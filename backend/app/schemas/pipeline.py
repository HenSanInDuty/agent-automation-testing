from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"  # NEW: paused between stages
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"  # NEW: explicitly cancelled by user


class AgentRunStatus(str, Enum):
    WAITING = "waiting"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"


AGENT_STATUS_TO_FRONTEND: dict[str, str] = {
    "waiting": "pending",
    "running": "running",
    "done": "completed",
    "skipped": "skipped",
    "error": "failed",
}


class WSEventType(str, Enum):
    RUN_STARTED = "run.started"
    STAGE_STARTED = "stage.started"
    STAGE_COMPLETED = "stage.completed"
    STAGE_FAILED = "stage.failed"  # NEW
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_PAUSED = "run.paused"  # NEW
    RUN_RESUMED = "run.resumed"  # NEW
    RUN_CANCELLED = "run.cancelled"  # NEW
    LOG = "log"

    # V3 DAG execution events
    LAYER_STARTED = "layer.started"  # Execution layer started
    LAYER_COMPLETED = "layer.completed"  # Execution layer completed
    NODE_STARTED = "node.started"  # Replaces agent.started for DAG nodes
    NODE_COMPLETED = "node.completed"  # Replaces agent.completed for DAG nodes
    NODE_FAILED = "node.failed"  # Replaces agent.failed for DAG nodes
    NODE_SKIPPED = "node.skipped"  # A disabled node was skipped
    NODE_PROGRESS = "node.progress"  # Intermediate progress update


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Run
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunCreate(BaseModel):
    """Payload for creating a pipeline run (V3: template-based)."""

    template_id: Optional[str] = Field(
        default=None,
        description="Which pipeline template to run. None = use legacy stage-based runner.",
    )
    llm_profile_id: Optional[str] = Field(
        default=None,
        description="Override LLM profile for this run. None = use global default.",
    )
    run_params: dict = Field(
        default_factory=dict,
        description="Extra parameters passed to the pipeline runner at run time.",
    )


class AgentRunResult(BaseModel):
    agent_id: str
    display_name: str
    stage: str
    status: str  # frontend values: pending, running, completed, failed, skipped
    output_preview: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PipelineRunResponse(BaseModel):
    """Returned when creating or GET-ing a pipeline run."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID of the run (run_id field in MongoDB)")
    run_id: str = Field(description="Same as id — explicit alias for V3 consumers")
    status: PipelineStatus
    template_id: Optional[str] = None  # V3: which template was used
    llm_profile_id: Optional[str] = None

    document_filename: str

    # V3 node-level tracking
    current_node: Optional[str] = None
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    node_statuses: dict[str, str] = Field(default_factory=dict)
    execution_layers: list[list[str]] = Field(default_factory=list)
    duration_seconds: Optional[float] = None

    # V2 compat fields (kept)
    current_stage: Optional[str] = None
    completed_stages: list[str] = Field(default_factory=list)

    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    resumed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    agent_runs: list[AgentRunResult] = Field(default_factory=list)


class PipelineRunListItem(BaseModel):
    """Lightweight version for list endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    template_id: Optional[str] = None
    document_filename: str
    status: PipelineStatus
    llm_profile_id: Optional[str] = None  # MongoDB ObjectId string
    current_stage: Optional[str] = None  # NEW
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class PipelineRunListResponse(BaseModel):
    items: list[PipelineRunListItem]
    total: int
    page: int
    page_size: int


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Result (output of each agent)
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str  # MongoDB ObjectId string
    run_id: str
    stage: str
    agent_id: str
    output: Any = Field(description="JSON output from the agent")
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Events
# ─────────────────────────────────────────────────────────────────────────────


class WSEventBase(BaseModel):
    """Base structure for all WebSocket events."""

    event: WSEventType
    run_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    data: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> str:
        return self.model_dump_json()


class RunStartedEvent(WSEventBase):
    event: WSEventType = WSEventType.RUN_STARTED

    @classmethod
    def build(
        cls, run_id: str, document_name: str, total_agents: int
    ) -> "RunStartedEvent":
        return cls(
            run_id=run_id,
            data={
                "document_name": document_name,
                "total_agents": total_agents,
            },
        )


class StageStartedEvent(WSEventBase):
    event: WSEventType = WSEventType.STAGE_STARTED

    @classmethod
    def build(cls, run_id: str, stage: str, agent_count: int) -> "StageStartedEvent":
        return cls(
            run_id=run_id,
            data={"stage": stage, "agent_count": agent_count},
        )


class StageCompletedEvent(WSEventBase):
    event: WSEventType = WSEventType.STAGE_COMPLETED

    @classmethod
    def build(
        cls, run_id: str, stage: str, summary: Optional[dict] = None
    ) -> "StageCompletedEvent":
        data: dict[str, Any] = {"stage": stage}
        if summary:
            data["summary"] = summary
        return cls(run_id=run_id, data=data)


class AgentStartedEvent(WSEventBase):
    event: WSEventType = WSEventType.AGENT_STARTED

    @classmethod
    def build(
        cls, run_id: str, agent_id: str, display_name: str, stage: str
    ) -> "AgentStartedEvent":
        return cls(
            run_id=run_id,
            data={
                "agent_id": agent_id,
                "display_name": display_name,
                "stage": stage,
            },
        )


class AgentCompletedEvent(WSEventBase):
    event: WSEventType = WSEventType.AGENT_COMPLETED

    @classmethod
    def build(
        cls,
        run_id: str,
        agent_id: str,
        output_preview: str = "",
    ) -> "AgentCompletedEvent":
        return cls(
            run_id=run_id,
            data={
                "agent_id": agent_id,
                "output_preview": output_preview[:200],  # truncate preview
            },
        )


class AgentFailedEvent(WSEventBase):
    event: WSEventType = WSEventType.AGENT_FAILED

    @classmethod
    def build(cls, run_id: str, agent_id: str, error: str) -> "AgentFailedEvent":
        return cls(
            run_id=run_id,
            data={"agent_id": agent_id, "error": error},
        )


class RunCompletedEvent(WSEventBase):
    event: WSEventType = WSEventType.RUN_COMPLETED

    @classmethod
    def build(
        cls,
        run_id: str,
        total_stages: int,
        duration_seconds: float,
    ) -> "RunCompletedEvent":
        return cls(
            run_id=run_id,
            data={
                "total_stages": total_stages,
                "duration_seconds": duration_seconds,
                "result_url": f"/api/v1/pipeline/runs/{run_id}",
            },
        )


class RunFailedEvent(WSEventBase):
    event: WSEventType = WSEventType.RUN_FAILED

    @classmethod
    def build(cls, run_id: str, error: str) -> "RunFailedEvent":
        return cls(run_id=run_id, data={"error": error})


class RunPausedEvent(WSEventBase):
    """NEW: Emitted when pipeline is paused between stages."""

    event: WSEventType = WSEventType.RUN_PAUSED

    @classmethod
    def build(
        cls,
        run_id: str,
        completed_stages: list[str],
        next_stage: Optional[str] = None,
    ) -> "RunPausedEvent":
        return cls(
            run_id=run_id,
            data={
                "message": "Pipeline paused by user",
                "completed_stages": completed_stages,
                "next_stage": next_stage,
            },
        )


class RunResumedEvent(WSEventBase):
    """NEW: Emitted when a paused pipeline is resumed."""

    event: WSEventType = WSEventType.RUN_RESUMED

    @classmethod
    def build(
        cls,
        run_id: str,
        continuing_from: Optional[str] = None,
    ) -> "RunResumedEvent":
        return cls(
            run_id=run_id,
            data={
                "message": "Pipeline resumed by user",
                "continuing_from": continuing_from,
            },
        )


class RunCancelledEvent(WSEventBase):
    """NEW: Emitted when pipeline is cancelled."""

    event: WSEventType = WSEventType.RUN_CANCELLED

    @classmethod
    def build(
        cls,
        run_id: str,
        completed_stages: list[str],
    ) -> "RunCancelledEvent":
        return cls(
            run_id=run_id,
            data={
                "message": "Pipeline cancelled by user",
                "completed_stages": completed_stages,
                "partial_results_available": len(completed_stages) > 0,
            },
        )


class LogEvent(WSEventBase):
    event: WSEventType = WSEventType.LOG

    @classmethod
    def build(cls, run_id: str, message: str, level: str = "info") -> "LogEvent":
        return cls(
            run_id=run_id,
            data={"message": message, "level": level},
        )


class LayerStartedEvent(WSEventBase):
    """V3: Emitted when a DAG execution layer begins."""

    event: WSEventType = WSEventType.LAYER_STARTED

    @classmethod
    def build(
        cls,
        run_id: str,
        layer_index: int,
        nodes: list[str],
        parallel: bool = True,
    ) -> "LayerStartedEvent":
        return cls(
            run_id=run_id,
            data={
                "layer_index": layer_index,
                "nodes": nodes,
                "parallel": parallel,
            },
        )


class LayerCompletedEvent(WSEventBase):
    """V3: Emitted when a DAG execution layer completes."""

    event: WSEventType = WSEventType.LAYER_COMPLETED

    @classmethod
    def build(
        cls,
        run_id: str,
        layer_index: int,
        nodes: list[str],
        duration_seconds: float,
        all_succeeded: bool,
    ) -> "LayerCompletedEvent":
        return cls(
            run_id=run_id,
            data={
                "layer_index": layer_index,
                "nodes": nodes,
                "duration_seconds": duration_seconds,
                "all_succeeded": all_succeeded,
            },
        )


class NodeStartedEvent(WSEventBase):
    """V3: Emitted when a DAG node begins execution."""

    event: WSEventType = WSEventType.NODE_STARTED

    @classmethod
    def build(
        cls,
        run_id: str,
        node_id: str,
        node_type: str,
        label: str,
        agent_id: Optional[str] = None,
        layer_index: int = 0,
    ) -> "NodeStartedEvent":
        return cls(
            run_id=run_id,
            data={
                "node_id": node_id,
                "node_type": node_type,
                "label": label,
                "agent_id": agent_id,
                "layer_index": layer_index,
            },
        )


class NodeCompletedEvent(WSEventBase):
    """V3: Emitted when a DAG node completes successfully."""

    event: WSEventType = WSEventType.NODE_COMPLETED

    @classmethod
    def build(
        cls,
        run_id: str,
        node_id: str,
        duration_seconds: float,
        output_preview: str = "",
        has_full_results: bool = True,
    ) -> "NodeCompletedEvent":
        return cls(
            run_id=run_id,
            data={
                "node_id": node_id,
                "duration_seconds": duration_seconds,
                "output_preview": output_preview[:200],
                "has_full_results": has_full_results,
            },
        )


class NodeFailedEvent(WSEventBase):
    """V3: Emitted when a DAG node fails."""

    event: WSEventType = WSEventType.NODE_FAILED

    @classmethod
    def build(
        cls,
        run_id: str,
        node_id: str,
        error: str,
        will_retry: bool = False,
        retry_attempt: int = 0,
    ) -> "NodeFailedEvent":
        return cls(
            run_id=run_id,
            data={
                "node_id": node_id,
                "error": error,
                "will_retry": will_retry,
                "retry_attempt": retry_attempt,
            },
        )


class NodeSkippedEvent(WSEventBase):
    """V3: Emitted when a DAG node is skipped (disabled or dependency failed)."""

    event: WSEventType = WSEventType.NODE_SKIPPED

    @classmethod
    def build(
        cls,
        run_id: str,
        node_id: str,
        reason: str,
    ) -> "NodeSkippedEvent":
        return cls(
            run_id=run_id,
            data={
                "node_id": node_id,
                "reason": reason,
            },
        )
