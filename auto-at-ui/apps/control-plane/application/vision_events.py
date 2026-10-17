"""At-least-once-safe orchestration for advisory visual exploration."""

import asyncio
import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, AgentStepGuard, resolve_agent_runtime
from agents.vision.debug_evidence import DebugEvidenceUnavailableError, encrypt_debug_evidence
from agents.vision.executor import policy_to_step_guard
from agents.vision.intent import decrypt_visual_intent
from auto_at.contracts.generation import ProjectExecutionPolicy
from config import Settings
from domain.activity import ActivityEvent
from domain.entities import VisualReplayFrameRecord, VisualTrajectoryEdgeRecord
from domain.ports import VerifiedVisualReplayStore
from domain.runs import AuditEvent, OutboxEvent
from domain.vision import (
    VISION_MODEL_FAILURE_REASONS,
    VisionImageAuthorizationRequired,
    vision_model_failure_reason,
)
from infrastructure.persistence.models import (
    VisionDebugEvidenceModel,
    VisualActionProposalModel,
    VisualExplorationStateModel,
)

from application.generation import SubmitGeneration
from application.vision_model_batch import VisionModelBatch, VisionModelSession
from application.vision_operations import VisualOperationStopped


class VisionEventProcessor:
    """Consumes one queued session; duplicate or terminal sessions never call a model."""

    def __init__(
        self, sessions, configs, generation, audits, activities, outbox, settings: Settings,
        replay_store: VerifiedVisualReplayStore | None = None,
        *, model_batch: VisionModelBatch | None = None, read_policy=None,
    ) -> None:
        self._sessions, self._configs, self._generation = sessions, configs, generation
        self._audits, self._activities, self._outbox, self._settings = (
            audits,
            activities,
            outbox,
            settings,
        )
        self._replay_store = replay_store
        self._model_batch = model_batch
        self._read_policy = read_policy or (lambda tenant_id, project_id: (
            self._configs.get(tenant_id, AGENT_RUNTIME_CONFIG_KEY),
            self._generation.get_policy(tenant_id, project_id),
        ))

    async def execute(self, event: OutboxEvent) -> str:
        if event.event_type != "agent.visual_exploration.requested.v1":
            raise ValueError("unexpected visual exploration event")
        raw_id = event.payload.get("session_id")
        if not isinstance(raw_id, str):
            raise ValueError("visual exploration event is missing session_id")
        session = self._sessions.get(event.tenant_id, UUID(raw_id))
        if session is not None and getattr(session, "trace_version", "legacy") == "v4":
            # The infrastructure publisher invokes v4 outside its legacy transaction.
            return "deferred"
        if session is None or session.state in {"completed", "unavailable", "cancelled"}:
            return "already_processed"
        if session.state == "running":
            # Legacy replay has no durable operation handle to reconcile uncertain actions.
            return self._unavailable(session, "visual_exploration_unavailable")
        worker_session_open = False
        try:
            config, policy = self._read_policy(session.tenant_id, session.project_id)
            try:
                runtime = resolve_agent_runtime(self._settings, config).vision
            except ValueError:
                raise VisualOperationStopped("policy_disabled") from None
            started_at = datetime.now(UTC)
            deadline = started_at + timedelta(
                seconds=min(session.max_session_seconds, runtime.max_session_seconds)
            )

            def check_policy():
                config, latest = self._read_policy(session.tenant_id, session.project_id)
                try:
                    live = resolve_agent_runtime(self._settings, config).vision
                except ValueError:
                    raise VisualOperationStopped("policy_disabled") from None
                if (
                    not live.enabled or not live.raw_screenshot_transfer_accepted
                    or live.raw_screenshot_transfer_provider != session.provider
                    or (live.provider, live.model) != (session.provider, session.model)
                    or latest is None or policy is None
                    or latest.allowed_origins != policy.allowed_origins
                    or not ProjectExecutionPolicy(
                        project_id=session.project_id, allowed_origins=latest.allowed_origins
                    ).allows(session.target_url)
                ):
                    raise VisualOperationStopped("policy_disabled")
                if remaining_seconds(live) <= 0:
                    raise VisualOperationStopped("session_timeout")
                return live, latest

            def remaining_seconds(live):
                return (min(deadline, started_at + timedelta(
                    seconds=live.max_session_seconds
                )) - datetime.now(UTC)).total_seconds()

            check_policy()
            effective = runtime.model_copy(update={
                "max_steps": min(session.max_steps, runtime.max_steps),
                "max_screenshot_bytes": min(
                    session.max_screenshot_bytes, runtime.max_screenshot_bytes
                ),
            })
            guard = AgentStepGuard(policy_to_step_guard(effective))
            model_calls = 0
            intent = decrypt_visual_intent(
                session.encrypted_task_intent,
                self._settings.vision_intent_encryption_key,
                session.intent_retention_until,
            )
            if policy is None or not self._settings.vision_worker_secret:
                raise ValueError("visual worker is unavailable")
            root = Path(self._settings.artifact_root, "vision", str(session.id)).resolve()
            session.state = "running"
            self._progress(session, "started", "started")
            # A checkpoint is an in-memory ancestor action path.  The worker replays it
            # in a new context, so siblings are isolated and BFS can backtrack safely.
            queue: list[
                tuple[
                    UUID, UUID | None, int, list[dict[str, object]],
                    VisualTrajectoryEdgeRecord | None, str | None, int | None,
                ]
            ] = [
                (uuid4(), None, 0, [], None, None, None)
            ]
            visited, sequence, last_model_call = 0, 0, None
            max_hops = min(session.max_hops, policy.vision_max_hops)
            max_states = min(session.max_states, policy.vision_max_states)
            worker_session_open = True
            async with httpx.AsyncClient(timeout=runtime.max_session_seconds) as client:
                while queue and visited < max_states:
                    live, latest = check_policy()
                    max_hops = min(max_hops, latest.vision_max_hops)
                    max_states = min(max_states, latest.vision_max_states)
                    if visited >= max_states:
                        break
                    (
                        state_id, parent_id, hop, replay_path, originating_edge,
                        parent_url_fingerprint, originating_sequence,
                    ) = queue.pop(0)
                    if hop > max_hops:
                        continue
                    try:
                        async with asyncio.timeout(remaining_seconds(live)):
                            response = await client.post(
                                f"{self._settings.playwright_worker_url.rstrip('/')}/visual-explorations/tree-states",
                                headers={
                                    "X-Auto-At-Vision-Worker-Secret": (
                                        self._settings.vision_worker_secret
                                    )
                                },
                                json={
                                    "contract_version": "v3",
                                    "id": str(session.id),
                                    "node_id": str(state_id),
                                    "target_url": session.target_url,
                                    "allowed_origins": policy.allowed_origins,
                                    "max_hops": max_hops,
                                    "max_states": max_states,
                                    "max_screenshot_bytes": min(
                                        session.max_screenshot_bytes, live.max_screenshot_bytes
                                    ),
                                    "max_session_seconds": min(
                                        session.max_session_seconds, live.max_session_seconds
                                    ),
                                    "replay_path": replay_path,
                                    **(
                                        {"parent_url_fingerprint": parent_url_fingerprint}
                                        if parent_url_fingerprint is not None
                                        else {}
                                    ),
                                },
                                timeout=remaining_seconds(live),
                            )
                        response.raise_for_status()
                        observation = response.json()
                        url_fingerprint = observation.get("url_fingerprint")
                        url_change = observation.get("url_change")
                        duration_ms = observation.get("duration_ms")
                        if (
                            not isinstance(url_fingerprint, str)
                            or not isinstance(duration_ms, int)
                            or duration_ms < 0
                            or duration_ms > 3_600_000
                            or url_change not in {"unchanged", "changed", "unavailable"}
                        ):
                            raise ValueError("worker observation metadata is invalid")
                    except Exception:
                        if originating_edge is not None and originating_sequence is not None:
                            self._finalize_edge(
                                session, originating_edge, originating_sequence,
                                status="failed", outcome_code="capture_failed",
                            )
                        raise
                    path = (root / f"tree-{state_id}.png").resolve()
                    if root not in path.parents or not path.is_file():
                        raise ValueError("visual screenshot is unavailable")
                    image = path.read_bytes()
                    if len(image) > min(
                        session.max_screenshot_bytes, live.max_screenshot_bytes
                    ) or not image.startswith(
                        b"\x89PNG\r\n\x1a\n"
                    ):
                        raise ValueError("visual screenshot failed verification")
                    checksum = hashlib.sha256(image).hexdigest()
                    state_sequence = visited + 1
                    frame = VisualReplayFrameRecord(
                        id=uuid4(), tenant_id=session.tenant_id, session_id=session.id,
                        state_id=state_id, sequence=state_sequence,
                        storage_key=(
                            f"tenants/{session.tenant_id}/vision-explorations/{session.id}"
                            f"/states/{state_id}.png"
                        ),
                        checksum=checksum, size=len(image), content_type="image/png",
                        captured_at=datetime.now(UTC),
                    )
                    if self._replay_store is None:
                        raise ValueError("visual replay storage is unavailable")
                    self._replay_store.write_replay_frame(frame, image)
                    self._sessions.add_state(
                        VisualExplorationStateModel(
                            id=state_id,
                            tenant_id=session.tenant_id,
                            session_id=session.id,
                            parent_id=parent_id,
                            hop=hop,
                            screenshot_checksum=checksum,
                        )
                    )
                    self._sessions.add_replay_frame(frame)
                    check_policy()
                    visited += 1
                    if originating_edge is not None and originating_sequence is not None:
                        status = "terminal" if hop >= max_hops else (
                            "no_meaningful_change" if url_change == "unchanged" else "observed"
                        )
                        self._finalize_edge(
                            session,
                            originating_edge,
                            originating_sequence,
                            status=status,
                            outcome_code="hop_limit" if hop >= max_hops else None,
                            child_state_id=state_id,
                            observed_at=frame.captured_at,
                            duration_ms=duration_ms,
                            url_fingerprint=url_fingerprint,
                            url_change=url_change,
                            child_screenshot_checksum=checksum,
                        )
                    self._progress(
                        session,
                        "state.captured",
                        f"state.captured:{state_id}",
                        {"state_sequence": visited, "hop": hop},
                    )
                    if hop >= max_hops:
                        self._progress(
                            session,
                            "limit.reached",
                            f"limit.hop:{state_id}",
                            {"hop": hop},
                        )
                        continue
                    remaining_states = max_states - visited - len(queue)
                    if remaining_states < 1:
                        self._progress(
                            session,
                            "limit.reached",
                            f"limit.states:{state_id}",
                            {"state_count": visited},
                        )
                        continue
                    if last_model_call is not None:
                        remaining = (
                            60 / min(
                                session.max_requests_per_minute, live.max_requests_per_minute
                            )
                            - (datetime.now(UTC) - last_model_call).total_seconds()
                        )
                        if remaining > 0:
                            async with asyncio.timeout(remaining_seconds(live)):
                                await asyncio.sleep(remaining)
                    live, latest = check_policy()
                    if model_calls >= min(session.max_steps, live.max_steps):
                        raise VisualOperationStopped("step_limit")
                    if hop >= min(max_hops, latest.vision_max_hops):
                        continue
                    remaining_states = (
                        min(max_states, latest.vision_max_states) - visited - len(queue)
                    )
                    if remaining_states < 1:
                        continue
                    self._progress(
                        session, "candidate.requested", f"candidate.requested:{state_id}",
                        {"state_sequence": visited, "hop": hop},
                    )
                    if self._model_batch is None:
                        raise VisualOperationStopped("model_unavailable")
                    model_calls += 1
                    outcome = await self._model_batch(
                        session=VisionModelSession(
                            session.tenant_id, session.id, session.provider, session.model,
                        ),
                        screenshot=image, task_intent=intent, policy=live,
                        max_candidates=min(20, remaining_states), guard=guard,
                        sequence=model_calls, check_policy=check_policy,
                        remaining_seconds=remaining_seconds(live),
                    )
                    check_policy()
                    last_model_call = datetime.now(UTC)
                    if outcome.actions is None:
                        self._capture_rejected_batch(
                            session=session,
                            state_id=state_id,
                            attempt_key=f"{state_id}:{visited}:{session.model}",
                            outcome=outcome,
                        )
                        return self._unavailable(
                            session, vision_model_failure_reason(outcome.failure_reason)
                        )
                    self._progress(
                        session,
                        "candidate.received",
                        f"candidate.received:{state_id}",
                        {
                            "state_sequence": visited,
                            "candidate_count": len(outcome.actions),
                        },
                    )
                    for action in outcome.actions:
                        sequence += 1
                        safe_action = {"kind": action.kind, "confidence": action.confidence}
                        for field in ("x", "y", "delta_y", "duration_ms"):
                            value = getattr(action, field, None)
                            if isinstance(value, (int, float)):
                                safe_action[field] = value
                        proposal = VisualActionProposalModel(
                                id=uuid4(),
                                tenant_id=session.tenant_id,
                                session_id=session.id,
                                originating_state_id=state_id,
                                correlation_id=session.correlation_id,
                                sequence=sequence,
                                action=safe_action,
                                evidence_checksum=checksum,
                                policy_version=session.policy_version,
                                provider=session.provider,
                                model=session.model,
                                prompt_version=session.prompt_version,
                            )
                        self._sessions.add_action(proposal)
                        edge = VisualTrajectoryEdgeRecord(
                            id=uuid4(), tenant_id=session.tenant_id, session_id=session.id,
                            parent_state_id=state_id, proposal_id=proposal.id, attempt=1,
                            action=safe_action, confidence=action.confidence, status="proposed",
                            outcome_code=None, child_state_id=None, observed_at=None,
                            duration_ms=0, url_fingerprint=None, url_change="unavailable",
                            child_screenshot_checksum=None, created_at=datetime.now(UTC),
                        )
                        self._sessions.add_trajectory_edge(edge)
                        self._progress(
                            session,
                            "edge.proposed",
                            f"edge.proposed:{edge.id}",
                            {
                                "state_sequence": visited,
                                "action_sequence": sequence,
                                "action_kind": action.kind,
                                "confidence": action.confidence,
                                "coordinate_available": action.kind in {"click", "type"},
                            },
                        )
                        if action.kind != "stop" and visited + len(queue) < max_states:
                            queue.append(
                                (
                                    uuid4(),
                                    state_id,
                                    hop + 1,
                                    replay_path + [action.model_dump(mode="json")],
                                    edge,
                                    url_fingerprint,
                                    sequence,
                                )
                            )
                        elif action.kind == "stop":
                            self._finalize_edge(
                                session,
                                edge,
                                sequence,
                                status="terminal",
                                outcome_code="model_stop",
                            )
                        else:
                            self._finalize_edge(
                                session,
                                edge,
                                sequence,
                                status="terminal",
                                outcome_code="state_limit",
                            )
            session.state = "completed"
            draft_handoff = False
            if session.state == "completed":
                try:
                    SubmitGeneration(self._generation, self._audits, self._outbox).execute(
                        tenant_id=session.tenant_id,
                        project_id=session.project_id,
                        correlation_id=session.correlation_id,
                        target_url=session.target_url,
                        natural_language_request=(
                            "Create a reviewable Playwright draft for this approved visual intent: "
                            f"{intent}"
                        ),
                        idempotency_key=f"vision-draft:{session.id}",
                    )
                    draft_handoff = True
                except Exception:
                    # Exploration is complete even if the independent draft handoff retries later.
                    draft_handoff = False
            self._progress(
                session,
                "draft.handoff",
                "draft.handoff",
                {"outcome": "accepted" if draft_handoff else "unavailable"},
            )
            self._progress(
                session,
                "completed",
                "completed",
                {"state_count": visited, "action_count": sequence},
            )
            self._audits.append(
                AuditEvent(
                    id=uuid4(),
                    tenant_id=session.tenant_id,
                    actor="vision-worker",
                    action="vision.action_proposed",
                    entity_type="visual_exploration_session",
                    entity_id=session.id,
                    correlation_id=session.correlation_id,
                )
            )
            return session.state
        except Exception as error:
            reason = (
                "image_delivery_auth_required"
                if isinstance(error, VisionImageAuthorizationRequired)
                else str(error) if isinstance(error, VisualOperationStopped)
                else "session_timeout" if isinstance(error, TimeoutError)
                else "visual_exploration_unavailable"
            )
            return self._unavailable(session, reason)
        finally:
            if worker_session_open:
                try:
                    async with httpx.AsyncClient(timeout=10) as client:
                        await client.delete(
                            f"{self._settings.playwright_worker_url.rstrip('/')}/visual-explorations/{session.id}",
                            headers={
                                "X-Auto-At-Vision-Worker-Secret": (
                                    self._settings.vision_worker_secret
                                )
                            },
                        )
                except Exception:
                    # Worker cleanup cannot change the fail-closed exploration result.
                    pass

    def _unavailable(self, session, reason: str) -> str:
        if reason not in VISION_MODEL_FAILURE_REASONS | {
            "policy_disabled", "session_timeout", "image_delivery_auth_required", "step_limit",
        }:
            reason = "visual_exploration_unavailable"
        session.state, session.safe_failure_reason = "unavailable", reason
        self._progress(session, "unavailable", "unavailable", {"reason_code": reason})
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=session.tenant_id,
                actor="vision-worker",
                action="vision.exploration_unavailable",
                entity_type="visual_exploration_session",
                entity_id=session.id,
                correlation_id=session.correlation_id,
            )
        )
        return "unavailable"

    def _progress(
        self, session, stage: str, progress_key: str, metadata: dict[str, object] | None = None
    ) -> None:
        self._activities.append(
            ActivityEvent.create_vision_progress(
                tenant_id=session.tenant_id,
                correlation_id=session.correlation_id,
                visual_exploration_session_id=session.id,
                stage=stage,
                progress_key=progress_key,
                occurred_at=datetime.now(UTC),
                metadata=metadata,
            )
        )

    def _finalize_edge(
        self,
        session,
        edge: VisualTrajectoryEdgeRecord,
        action_sequence: int,
        *,
        status: str,
        outcome_code: str | None,
        child_state_id: UUID | None = None,
        observed_at: datetime | None = None,
        duration_ms: int = 0,
        url_fingerprint: str | None = None,
        url_change: str = "unavailable",
        child_screenshot_checksum: str | None = None,
    ) -> None:
        finalized = replace(
            edge, status=status, outcome_code=outcome_code, child_state_id=child_state_id,
            observed_at=observed_at, duration_ms=duration_ms, url_fingerprint=url_fingerprint,
            url_change=url_change, child_screenshot_checksum=child_screenshot_checksum,
        )
        self._sessions.add_trajectory_edge(finalized)
        if status in {"observed", "no_meaningful_change"}:
            self._progress(
                session, "edge.observed", f"edge.observed:{edge.id}",
                {
                    "state_sequence": action_sequence,
                    "action_sequence": action_sequence,
                    "outcome": status,
                    "duration_ms": duration_ms,
                    "url_change": url_change,
                },
            )
        else:
            self._progress(
                session, "edge.terminal" if status == "terminal" else "edge.failed",
                f"edge.{status}:{edge.id}",
                {"state_sequence": action_sequence, "action_sequence": action_sequence,
                 "outcome_code": outcome_code or "capture_failed"},
            )

    def _capture_rejected_batch(
        self, *, session, state_id: UUID, attempt_key: str, outcome
    ) -> None:
        """Persist one encrypted diagnostic without changing the advisory outcome."""
        if outcome.diagnostic_code is None or outcome.diagnostic_capture is None:
            return
        captured_at = datetime.now(UTC)
        try:
            encrypted = encrypt_debug_evidence(
                outcome.diagnostic_capture,
                key=self._settings.vision_debug_evidence_encryption_key,
                key_id=self._settings.vision_debug_evidence_key_id,
            )
            evidence = self._sessions.add_debug_evidence(
                VisionDebugEvidenceModel(
                    id=uuid4(),
                    tenant_id=session.tenant_id,
                    session_id=session.id,
                    correlation_id=session.correlation_id,
                    state_id=state_id,
                    attempt_key=attempt_key,
                    diagnostic_code=outcome.diagnostic_code.value,
                    provider=session.provider,
                    model=session.model,
                    prompt_version=session.prompt_version,
                    encrypted_payload=encrypted.ciphertext,
                    key_id=encrypted.key_id,
                    payload_checksum=encrypted.checksum,
                    payload_byte_count=encrypted.byte_count,
                    redaction_version=encrypted.redaction_version,
                    captured_at=captured_at,
                    retention_until=captured_at
                    + timedelta(days=self._settings.vision_debug_evidence_retention_days),
                    deleted_at=None,
                )
            )
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=session.tenant_id,
                    correlation_id=session.correlation_id,
                    source="vision",
                    visual_exploration_session_id=session.id,
                    stage="debug_evidence.captured",
                    status="unavailable",
                    safe_summary="Vision diagnostic evidence was captured.",
                    occurred_at=captured_at,
                    metadata={
                        "diagnostic_code": outcome.diagnostic_code.value,
                        "capture_available": True,
                    },
                )
            )
            self._audits.append(
                AuditEvent(
                    id=uuid4(),
                    tenant_id=session.tenant_id,
                    actor="vision-worker",
                    action="vision.debug_evidence_captured",
                    entity_type="vision_debug_evidence",
                    entity_id=evidence.id,
                    correlation_id=session.correlation_id,
                )
            )
        except (DebugEvidenceUnavailableError, Exception):
            # No provider/model text may cross this boundary, including on key failure.
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=session.tenant_id,
                    correlation_id=session.correlation_id,
                    source="vision",
                    visual_exploration_session_id=session.id,
                    stage="debug_evidence.capture_failed",
                    status="unavailable",
                    safe_summary="Vision diagnostic evidence capture was unavailable.",
                    occurred_at=captured_at,
                    metadata={
                        "diagnostic_code": outcome.diagnostic_code.value,
                        "capture_available": False,
                    },
                )
            )
            self._audits.append(
                AuditEvent(
                    id=uuid4(),
                    tenant_id=session.tenant_id,
                    actor="vision-worker",
                    action="vision.debug_evidence_capture_failed",
                    entity_type="visual_exploration_session",
                    entity_id=session.id,
                    correlation_id=session.correlation_id,
                )
            )
