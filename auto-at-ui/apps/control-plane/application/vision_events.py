"""At-least-once-safe orchestration for advisory visual exploration."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from agents.shared.openrouter import create_vision_language_model
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, resolve_agent_runtime
from agents.vision.debug_evidence import DebugEvidenceUnavailableError, encrypt_debug_evidence
from agents.vision.executor import execute_visual_candidate_batch
from agents.vision.intent import decrypt_visual_intent
from agents.vision.temporary_images import GoogleDriveTemporaryVisionImageStore
from config import Settings
from domain.activity import ActivityEvent
from domain.entities import VisualReplayFrameRecord
from domain.ports import VerifiedVisualReplayStore
from domain.runs import AuditEvent, OutboxEvent
from infrastructure.persistence.models import (
    VisionDebugEvidenceModel,
    VisualActionProposalModel,
    VisualExplorationStateModel,
)

from application.generation import SubmitGeneration


class VisionEventProcessor:
    """Consumes one queued session; duplicate or terminal sessions never call a model."""

    def __init__(
        self, sessions, configs, generation, audits, activities, outbox, settings: Settings,
        replay_store: VerifiedVisualReplayStore | None = None,
    ) -> None:
        self._sessions, self._configs, self._generation = sessions, configs, generation
        self._audits, self._activities, self._outbox, self._settings = (
            audits,
            activities,
            outbox,
            settings,
        )
        self._replay_store = replay_store

    async def execute(self, event: OutboxEvent) -> str:
        if event.event_type != "agent.visual_exploration.requested.v1":
            raise ValueError("unexpected visual exploration event")
        raw_id = event.payload.get("session_id")
        if not isinstance(raw_id, str):
            raise ValueError("visual exploration event is missing session_id")
        session = self._sessions.get(event.tenant_id, UUID(raw_id))
        if session is None or session.state in {"completed", "unavailable", "cancelled"}:
            return "already_processed"
        runtime = resolve_agent_runtime(
            self._settings, self._configs.get(event.tenant_id, AGENT_RUNTIME_CONFIG_KEY)
        )
        if not runtime.vision.enabled or not runtime.vision.raw_screenshot_transfer_accepted:
            return self._unavailable(session, "vision policy is disabled")
        worker_session_open = False
        try:
            intent = decrypt_visual_intent(
                session.encrypted_task_intent,
                self._settings.vision_intent_encryption_key,
                session.intent_retention_until,
            )
            policy = self._generation.get_policy(event.tenant_id, session.project_id)
            if policy is None or not self._settings.vision_worker_secret:
                raise ValueError("visual worker is unavailable")
            root = Path(self._settings.artifact_root, "vision", str(session.id)).resolve()
            session.state = "running"
            self._progress(session, "started", "started")
            # A checkpoint is an in-memory ancestor action path.  The worker replays it
            # in a new context, so siblings are isolated and BFS can backtrack safely.
            queue: list[tuple[UUID, UUID | None, int, list[dict[str, object]]]] = [
                (uuid4(), None, 0, [])
            ]
            visited, sequence, last_model_call = 0, 0, None
            max_hops = min(session.max_hops, policy.vision_max_hops)
            max_states = min(session.max_states, policy.vision_max_states)
            worker_session_open = True
            async with httpx.AsyncClient(timeout=runtime.vision.max_session_seconds) as client:
                while queue and visited < max_states:
                    state_id, parent_id, hop, replay_path = queue.pop(0)
                    response = await client.post(
                        f"{self._settings.playwright_worker_url.rstrip('/')}/visual-explorations/tree-states",
                        headers={
                            "X-Auto-At-Vision-Worker-Secret": self._settings.vision_worker_secret
                        },
                        json={
                            "contract_version": "v2",
                            "id": str(session.id),
                            "node_id": str(state_id),
                            "target_url": session.target_url,
                            "allowed_origins": policy.allowed_origins,
                            "max_hops": max_hops,
                            "max_states": max_states,
                            "max_screenshot_bytes": runtime.vision.max_screenshot_bytes,
                            "max_session_seconds": runtime.vision.max_session_seconds,
                            "replay_path": replay_path,
                        },
                    )
                    response.raise_for_status()
                    path = (root / f"tree-{state_id}.png").resolve()
                    if root not in path.parents or not path.is_file():
                        raise ValueError("visual screenshot is unavailable")
                    image = path.read_bytes()
                    if len(image) > runtime.vision.max_screenshot_bytes or not image.startswith(
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
                    visited += 1
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
                            60 / runtime.vision.max_requests_per_minute
                            - (datetime.now(UTC) - last_model_call).total_seconds()
                        )
                        if remaining > 0:
                            await asyncio.sleep(remaining)
                    store = GoogleDriveTemporaryVisionImageStore(
                        service_account_file=self._settings.google_drive_service_account_file,
                        oauth_client_id=self._settings.google_drive_oauth_client_id,
                        oauth_client_secret=self._settings.google_drive_oauth_client_secret,
                        oauth_refresh_token=self._settings.google_drive_oauth_refresh_token,
                        folder_id=self._settings.google_drive_vision_folder_id,
                        ttl=self._settings.vision_temporary_url_ttl_seconds,
                        delete_after_delivery=self._settings.google_drive_vision_delete_after_delivery,
                    )
                    async with store.deliver(
                        tenant_id=session.tenant_id,
                        session_id=session.id,
                        sequence=visited,
                        image=image,
                    ) as image_url:
                        self._progress(
                            session,
                            "candidate.requested",
                            f"candidate.requested:{state_id}",
                            {"state_sequence": visited, "hop": hop},
                        )
                        outcome = await execute_visual_candidate_batch(
                            screenshot=image,
                            content_type="image/png",
                            image_url=image_url,
                            task_intent=intent,
                            policy=runtime.vision,
                            model=create_vision_language_model(self._settings, runtime.vision),
                            max_candidates=min(20, remaining_states),
                        )
                    last_model_call = datetime.now(UTC)
                    if outcome.actions is None:
                        self._capture_rejected_batch(
                            session=session,
                            state_id=state_id,
                            attempt_key=f"{state_id}:{visited}:{session.model}",
                            outcome=outcome,
                        )
                        return self._unavailable(
                            session, outcome.detail or "vision model request failed"
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
                        self._sessions.add_action(
                            VisualActionProposalModel(
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
                        )
                        progress_metadata = {
                            "state_sequence": visited,
                            "action_sequence": sequence,
                            "action_kind": action.kind,
                            "confidence": action.confidence,
                        }
                        for field in ("x", "y", "delta_y", "duration_ms"):
                            value = getattr(action, field, None)
                            if isinstance(value, (int, float)):
                                progress_metadata[field] = value
                        self._progress(
                            session,
                            "action.recorded",
                            f"action.recorded:{sequence}",
                            progress_metadata,
                        )
                        if action.kind != "stop" and visited + len(queue) < max_states:
                            queue.append(
                                (
                                    uuid4(),
                                    state_id,
                                    hop + 1,
                                    replay_path + [action.model_dump(mode="json")],
                                )
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
        except Exception:
            return self._unavailable(session, "visual exploration is unavailable")
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
        session.state, session.safe_failure_reason = "unavailable", reason
        self._progress(session, "unavailable", "unavailable")
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
