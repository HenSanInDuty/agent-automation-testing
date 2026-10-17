"""Internal model-call boundary shared by legacy and v4 orchestration."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from agents.shared.runtime import AgentStepGuard, VisionPolicy
from agents.vision.executor import VisualCandidateBatchOutcome


@dataclass(frozen=True)
class VisionModelSession:
    """Immutable identity and provider snapshot, independent of persistence models."""

    tenant_id: str
    id: UUID
    provider: str
    model: str


class VisionModelBatch(Protocol):
    async def __call__(
        self, *, session: VisionModelSession, screenshot: bytes, task_intent: str,
        policy: VisionPolicy, max_candidates: int, guard: AgentStepGuard, sequence: int,
        check_policy: Callable[[], object], remaining_seconds: float,
    ) -> VisualCandidateBatchOutcome:
        """Check live policy by raising before transfer and before returning proposals."""
        ...
