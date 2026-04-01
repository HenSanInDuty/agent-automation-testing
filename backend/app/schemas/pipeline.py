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
    COMPLETED = "completed"
    FAILED = "failed"


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
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    LOG = "log"


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Run
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRunCreate(BaseModel):
    """
    Payload gửi lên khi tạo một pipeline run mới.
    File được upload qua multipart/form-data nên không có ở đây.
    """

    llm_profile_id: Optional[int] = Field(
        default=None,
        description="Override LLM profile cho run này. None = dùng global default.",
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
    """Trả về khi tạo run mới hoặc GET run detail."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID của run")
    status: PipelineStatus
    llm_profile_id: Optional[int] = None
    document_filename: str
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    agent_runs: list[AgentRunResult] = Field(default_factory=list)


class PipelineRunListItem(BaseModel):
    """Rút gọn dùng trong danh sách runs."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_filename: str
    status: PipelineStatus
    llm_profile_id: Optional[int] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    agent_runs: list[AgentRunResult] = Field(default_factory=list)


class PipelineRunListResponse(BaseModel):
    items: list[PipelineRunListItem]
    total: int
    page: int
    page_size: int


# ─────────────────────────────────────────────────────────────────────────────
# Pipeline Result (output của từng agent)
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    stage: str
    agent_id: str
    output: Any = Field(description="JSON output của agent")
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket Events
# ─────────────────────────────────────────────────────────────────────────────


class WSEventBase(BaseModel):
    """Base structure của mọi WebSocket event."""

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
    def build(cls, run_id: str, stage: str) -> "StageCompletedEvent":
        return cls(run_id=run_id, data={"stage": stage})


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
        total_agents: int,
        duration_seconds: float,
    ) -> "RunCompletedEvent":
        return cls(
            run_id=run_id,
            data={
                "total_agents": total_agents,
                "duration_seconds": duration_seconds,
                "result_url": f"/api/v1/pipeline/runs/{run_id}",
            },
        )


class RunFailedEvent(WSEventBase):
    event: WSEventType = WSEventType.RUN_FAILED

    @classmethod
    def build(cls, run_id: str, error: str) -> "RunFailedEvent":
        return cls(run_id=run_id, data={"error": error})


class LogEvent(WSEventBase):
    event: WSEventType = WSEventType.LOG

    @classmethod
    def build(cls, run_id: str, message: str, level: str = "info") -> "LogEvent":
        return cls(
            run_id=run_id,
            data={"message": message, "level": level},
        )
