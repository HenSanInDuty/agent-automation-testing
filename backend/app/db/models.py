from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from app.db.database import Base
from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ─────────────────────────────────────────────────────────────────────────────
# LLMProfile
# ─────────────────────────────────────────────────────────────────────────────


class LLMProfile(Base):
    """
    Lưu thông tin một LLM provider/model profile.
    Được dùng để build CrewAI LLM object tại runtime.
    """

    __tablename__ = "llm_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Định danh & display
    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Provider: openai | anthropic | ollama | huggingface | azure_openai | groq
    provider: Mapped[str] = mapped_column(String(50), nullable=False)

    # Model name (vd: gpt-4o, claude-3-5-sonnet-20241022, llama3)
    model: Mapped[str] = mapped_column(String(150), nullable=False)

    # Credentials — api_key có thể được encrypt tuỳ ENCRYPT_API_KEYS
    api_key: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Base URL — dùng cho Ollama, LM Studio, Azure, vLLM, ...
    base_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # LLM params
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.1)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=2048)

    # Chỉ một profile được is_default=True tại một thời điểm
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=_now, onupdate=_now
    )

    # Relations
    agent_configs: Mapped[list[AgentConfig]] = relationship(
        "AgentConfig",
        back_populates="llm_profile",
        lazy="select",
    )
    pipeline_runs: Mapped[list[PipelineRun]] = relationship(
        "PipelineRun",
        back_populates="llm_profile",
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<LLMProfile id={self.id} name={self.name!r} "
            f"provider={self.provider!r} model={self.model!r} "
            f"is_default={self.is_default}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# AgentConfig
# ─────────────────────────────────────────────────────────────────────────────


class AgentConfig(Base):
    """
    Cấu hình cho từng CrewAI Agent.
    Mỗi agent có một bản ghi duy nhất, được seed mặc định khi khởi động.
    Admin có thể cập nhật role/goal/backstory và override LLM qua UI.
    """

    __tablename__ = "agent_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Unique key dùng để lookup trong code (vd: "requirement_analyzer")
    agent_id: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )

    # Tên hiển thị trên UI
    display_name: Mapped[str] = mapped_column(String(150), nullable=False)

    # Stage: ingestion | testcase | execution | reporting
    stage: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # CrewAI Agent prompts
    role: Mapped[str] = mapped_column(Text, nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    backstory: Mapped[str] = mapped_column(Text, nullable=False)

    # LLM override — None nghĩa là dùng global default profile
    llm_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("llm_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Agent behaviour
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    verbose: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_iter: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, default=_now, onupdate=_now
    )

    # Relations
    llm_profile: Mapped[Optional[LLMProfile]] = relationship(
        "LLMProfile",
        back_populates="agent_configs",
        lazy="joined",  # load profile cùng lúc với agent
    )

    def __repr__(self) -> str:
        return (
            f"<AgentConfig id={self.id} agent_id={self.agent_id!r} "
            f"stage={self.stage!r} enabled={self.enabled}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PipelineRun
# ─────────────────────────────────────────────────────────────────────────────


class PipelineRun(Base):
    """
    Mỗi lần user upload tài liệu và bấm Run là tạo ra 1 PipelineRun.
    Lưu trạng thái tổng quan và trạng thái từng agent.
    """

    __tablename__ = "pipeline_runs"

    # UUID dạng string
    id: Mapped[str] = mapped_column(String(36), primary_key=True)

    # Thông tin tài liệu
    document_name: Mapped[str] = mapped_column(String(500), nullable=False)
    document_path: Mapped[str] = mapped_column(String(1000), nullable=False)

    # LLM profile được dùng cho run này (override global nếu có)
    llm_profile_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("llm_profiles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Trạng thái tổng: pending | running | completed | failed
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )

    # JSON blob: { "requirement_analyzer": "done", "rule_parser": "waiting", ... }
    agent_statuses: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    # Thông tin lỗi nếu pipeline thất bại
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=_now, index=True
    )
    finished_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)

    # Relations
    llm_profile: Mapped[Optional[LLMProfile]] = relationship(
        "LLMProfile",
        back_populates="pipeline_runs",
        lazy="select",
    )
    results: Mapped[list[PipelineResult]] = relationship(
        "PipelineResult",
        back_populates="run",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="PipelineResult.created_at",
    )

    # ── Helpers ───────────────────────────────────────────────────

    def get_agent_statuses(self) -> dict[str, str]:
        try:
            return json.loads(self.agent_statuses)
        except (json.JSONDecodeError, TypeError):
            return {}

    def set_agent_status(self, agent_id: str, status: str) -> None:
        statuses = self.get_agent_statuses()
        statuses[agent_id] = status
        self.agent_statuses = json.dumps(statuses)

    def __repr__(self) -> str:
        return (
            f"<PipelineRun id={self.id!r} status={self.status!r} "
            f"document={self.document_name!r}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# PipelineResult
# ─────────────────────────────────────────────────────────────────────────────


class PipelineResult(Base):
    """
    Lưu output của từng agent trong một pipeline run.
    Cho phép xem lại kết quả từng bước sau khi chạy xong.
    """

    __tablename__ = "pipeline_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Foreign key về PipelineRun
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Stage của agent đã tạo ra kết quả này
    stage: Mapped[str] = mapped_column(String(50), nullable=False)

    # Agent ID (vd: "requirement_analyzer")
    agent_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Output dạng JSON string
    output: Mapped[str] = mapped_column(Text, nullable=False)

    # Timestamp
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=_now)

    # Relations
    run: Mapped[PipelineRun] = relationship(
        "PipelineRun",
        back_populates="results",
        lazy="select",
    )

    # ── Helpers ───────────────────────────────────────────────────

    def get_output(self) -> dict | list | str:
        try:
            return json.loads(self.output)
        except (json.JSONDecodeError, TypeError):
            return self.output

    def __repr__(self) -> str:
        return (
            f"<PipelineResult id={self.id} run_id={self.run_id!r} "
            f"agent_id={self.agent_id!r}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# SQLAlchemy event: enforce is_default uniqueness at Python level
# (SQLite không có partial unique index đơn giản)
# ─────────────────────────────────────────────────────────────────────────────


@event.listens_for(LLMProfile, "before_insert")
@event.listens_for(LLMProfile, "before_update")
def _ensure_single_default(mapper, connection, target: LLMProfile) -> None:
    """
    Khi set is_default=True cho một profile,
    unset tất cả các profile khác đang là default.
    Chạy ở tầng Python để tránh phụ thuộc vào DB trigger.
    """
    if target.is_default:
        connection.execute(
            LLMProfile.__table__.update()
            .where(LLMProfile.__table__.c.id != (target.id or -1))
            .values(is_default=False)
        )
