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


class PipelineRunResponse(BaseModel):
    """Trả về khi tạo run mới hoặc GET run detail."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(description="UUID của run")
    document_name: str
    status: PipelineStatus
    agent_statuses: dict[str, AgentRunStatus] = Field(
        default_factory=dict,
        description="Trạng thái từng agent: { agent_id: status }",
    )
    error: Optional[str] = None
    llm_profile_id: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None

    # Computed
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Thời gian chạy (giây). None nếu chưa hoàn thành.",
    )

    def model_post_init(self, __context: Any) -> None:
        """Tính duration nếu đã hoàn thành."""
        if self.finished_at and self.created_at:
            delta = self.finished_at - self.created_at
            object.__setattr__(
                self, "duration_seconds", round(delta.total_seconds(), 2)
            )


class PipelineRunListItem(BaseModel):
    """Rút gọn dùng trong danh sách runs."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    document_name: str
    status: PipelineStatus
    llm_profile_id: Optional[int] = None
    created_at: datetime
    finished_at: Optional[datetime] = None


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
