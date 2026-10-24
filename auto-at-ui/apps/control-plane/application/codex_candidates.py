"""DOM-first orchestration, one image escalation and shared session call reservations."""

import asyncio
import hashlib
import struct
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from time import monotonic
from typing import Protocol
from uuid import UUID
from zlib import crc32

from agents.shared.runtime import AgentStepGuard, VisionPolicy
from agents.vision.codex_service import task_context, validate_candidates
from agents.vision.executor import VisualCandidateBatchOutcome
from auto_at.contracts.codex_bridge import (
    CodexBoundObservation,
    CodexBridgeResponse,
    CodexTaskContext,
    canonical_bytes,
)

from application.vision_model_batch import VisionModelSession


class CodexUnavailable(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def require_dom_policy(policy: VisionPolicy):
    if (not policy.enabled or policy.provider != "codex_cli" or policy.model != "gpt-6-luna"
            or policy.codex is None or not policy.codex.dom_transfer_accepted
            or policy.codex.dom_transfer_provider != "codex_cli"):
        raise CodexUnavailable("policy_changed")


@dataclass(frozen=True)
class CodexImage:
    data: bytes
    snapshot_id: UUID
    state_fingerprint: str
    sha256: str

    def validate(self, bound: CodexBoundObservation, max_bytes: int):
        obs = bound.observation
        if (self.snapshot_id != obs.snapshot_id or self.state_fingerprint != obs.state_fingerprint
                or hashlib.sha256(self.data).hexdigest() != self.sha256
                or not 45 <= len(self.data) <= max_bytes
                or self.data[:8] != b"\x89PNG\r\n\x1a\n"
                or self.data[8:16] != b"\x00\x00\x00\rIHDR"
                or crc32(self.data[12:29]) != int.from_bytes(self.data[29:33], "big")
                or not self.data.endswith(b"\x00\x00\x00\x00IEND\xaeB`\x82")):
            raise CodexUnavailable("bridge_stale_result")
        width, height = struct.unpack(">II", self.data[16:24])
        if (width, height) != (obs.viewport.width, obs.viewport.height):
            raise CodexUnavailable("bridge_stale_result")


class CodexExchange(Protocol):
    async def __call__(
        self, *, session: VisionModelSession, bound: CodexBoundObservation,
        context: CodexTaskContext, policy: VisionPolicy, sequence: int, deadline: datetime,
        max_candidates: int, image: CodexImage | None, check_policy: Callable[[], VisionPolicy],
    ) -> CodexBridgeResponse: ...


class CodexCallBudget:
    def __init__(
        self, *, guard: AgentStepGuard, max_calls: int, max_rate: int, deadline: datetime,
        check_policy: Callable[[], VisionPolicy], clock=monotonic, sleep=asyncio.sleep,
    ):
        self.guard, self.max_calls, self.max_rate = guard, max_calls, max_rate
        self.deadline, self.check_policy = deadline, check_policy
        self.calls, self.last_call = 0, None
        self.clock, self.sleep = clock, sleep

    async def reserve(self, evidence_bytes: int) -> int:
        policy = self.check_policy()
        require_dom_policy(policy)
        if self.calls >= min(self.max_calls, policy.max_steps):
            raise CodexUnavailable("step_limit")
        while self.last_call is not None:
            policy = self.check_policy()
            require_dom_policy(policy)
            interval = 60 / min(self.max_rate, policy.max_requests_per_minute)
            delay = interval - (self.clock() - self.last_call)
            if delay <= 0:
                break
            if delay >= (self.deadline - datetime.now(UTC)).total_seconds():
                raise CodexUnavailable("provider_timeout")
            await self.sleep(delay)
        policy = self.check_policy()
        require_dom_policy(policy)
        if datetime.now(UTC) >= self.deadline:
            raise CodexUnavailable("provider_timeout")
        if (self.calls >= min(self.max_calls, policy.max_steps)
                or not self.guard.reserve_external_call(evidence_bytes=evidence_bytes)):
            raise CodexUnavailable("step_limit")
        self.calls += 1
        self.last_call = self.clock()
        return self.calls


class CodexCandidateService:
    def __init__(self, exchange: CodexExchange):
        self.exchange = exchange

    async def propose(self, **kwargs) -> VisualCandidateBatchOutcome:
        budget = kwargs["budget"]
        initial_calls, started = budget.calls, monotonic()
        try:
            async with asyncio.timeout((budget.deadline - datetime.now(UTC)).total_seconds()):
                return await self._propose(**kwargs)
        except TimeoutError:
            return VisualCandidateBatchOutcome(
                status="unavailable", failure_reason="provider_timeout",
                calls_used=budget.calls - initial_calls, latency_seconds=monotonic() - started,
            )

    async def _propose(
        self, *, session: VisionModelSession, bound: CodexBoundObservation, task_intent: str,
        observed_actions: tuple[str, ...], max_candidates: int, budget: CodexCallBudget,
        check_state: Callable[[], Awaitable[bool]],
        capture_image: Callable[[], Awaitable[CodexImage]],
    ) -> VisualCandidateBatchOutcome:
        started = monotonic()
        initial_calls = budget.calls
        try:
            obs = bound.observation
            if (session.tenant_id != obs.tenant_id or session.id != obs.session_id
                    or session.project_id != obs.project_id
                    or session.fencing_token != obs.fencing_token or not session.correlation_id):
                raise CodexUnavailable("bridge_stale_result")
            context = task_context(task_intent, observed_actions)
            if not 1 <= max_candidates <= 10:
                raise CodexUnavailable("model_output_invalid")
            for stage in ("dom", "image"):
                policy = budget.check_policy()
                require_dom_policy(policy)
                if (session.provider, session.model) != (policy.provider, policy.model):
                    raise CodexUnavailable("policy_changed")
                if not await check_state():
                    raise CodexUnavailable("bridge_stale_result")
                image = None
                if stage == "image":
                    if (not policy.raw_screenshot_transfer_accepted
                            or policy.raw_screenshot_transfer_provider != "codex_cli"):
                        raise CodexUnavailable("image_consent_required")
                    # Reserve before capturing pixels, so exhaustion cannot leak an image.
                    sequence = await budget.reserve(len(canonical_bytes(bound.observation)))
                    image = await capture_image()
                    image.validate(bound, policy.max_screenshot_bytes)
                    if not await check_state():
                        raise CodexUnavailable("bridge_stale_result")
                else:
                    sequence = await budget.reserve(len(canonical_bytes(bound.observation)))
                if not await check_state():
                    raise CodexUnavailable("bridge_stale_result")
                policy = budget.check_policy()
                require_dom_policy(policy)
                if image and (not policy.raw_screenshot_transfer_accepted
                              or policy.raw_screenshot_transfer_provider != "codex_cli"):
                    raise CodexUnavailable("policy_changed")
                remaining = (budget.deadline - datetime.now(UTC)).total_seconds()
                if remaining <= 0:
                    raise CodexUnavailable("provider_timeout")
                async with asyncio.timeout(remaining):
                    response = await self.exchange(
                        session=session, bound=bound, context=context, policy=policy,
                        sequence=sequence, deadline=budget.deadline, max_candidates=max_candidates,
                        image=image, check_policy=budget.check_policy,
                    )
                require_dom_policy(budget.check_policy())
                if not await check_state():
                    raise CodexUnavailable("bridge_stale_result")
                if response.failure_code:
                    raise CodexUnavailable(response.failure_code)
                if response.output.outcome == "need_screenshot":
                    if stage != "dom":
                        raise CodexUnavailable("model_output_invalid")
                    continue
                outcome = validate_candidates(
                    response.output, bound, stage=stage, max_candidates=max_candidates,
                )
                outcome = VisualCandidateBatchOutcome(
                    **(outcome.__dict__ | {"calls_used": budget.calls - initial_calls,
                                         "latency_seconds": monotonic() - started}),
                )
                return outcome
            raise CodexUnavailable("model_output_invalid")
        except CodexUnavailable as exc:
            reason = exc.reason
        except TimeoutError:
            reason = "provider_timeout"
        except ValueError:
            reason = "model_output_invalid"
        return VisualCandidateBatchOutcome(
            status="unavailable", failure_reason=reason, detail="Codex proposal unavailable",
            calls_used=budget.calls - initial_calls, latency_seconds=monotonic() - started,
        )
