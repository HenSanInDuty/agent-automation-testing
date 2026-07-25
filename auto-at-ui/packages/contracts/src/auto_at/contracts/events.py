"""Versioned event envelopes shared by the control and workflow planes."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class EventType(StrEnum):
    TEST_RUN_REQUESTED = "test.run.requested.v1"
    TEST_RUN_STARTED = "test.run.started.v1"
    TEST_RUN_COMPLETED = "test.run.completed.v1"
    TEST_RUN_CANCELLED = "test.run.cancelled.v1"
    AGENT_TRIAGE_REQUESTED = "agent.triage.requested.v1"
    AGENT_PROPOSAL_CREATED = "agent.proposal.created.v1"
    PROPOSAL_APPROVAL_RECORDED = "proposal.approval.recorded.v1"
    MEMORY_EPISODE_VALIDATED = "memory.episode.validated.v1"


class EventEnvelope(BaseModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_type: EventType
    schema_version: str = "v1"
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    correlation_id: UUID
    causation_id: UUID | None = None
    idempotency_key: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
