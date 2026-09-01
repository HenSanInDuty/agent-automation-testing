"""At-least-once-safe orchestration for advisory visual exploration."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from agents.shared.openrouter import create_vision_language_model
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, resolve_agent_runtime
from agents.vision.executor import execute_visual_action
from agents.vision.intent import decrypt_visual_intent
from agents.vision.temporary_images import GoogleDriveTemporaryVisionImageStore
from config import Settings
from domain.activity import ActivityEvent
from domain.runs import AuditEvent, OutboxEvent
from infrastructure.persistence.models import VisualActionProposalModel

from application.generation import SubmitGeneration


class VisionEventProcessor:
    """Consumes one queued session; duplicate or terminal sessions never call a model."""

    def __init__(
        self, sessions, configs, generation, audits, activities, outbox, settings: Settings
    ) -> None:
        self._sessions, self._configs, self._generation = sessions, configs, generation
        self._audits, self._activities, self._outbox, self._settings = (
            audits,
            activities,
            outbox,
            settings,
        )

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
        try:
            intent = decrypt_visual_intent(
                session.encrypted_task_intent,
                self._settings.vision_intent_encryption_key,
                session.intent_retention_until,
            )
            policy = self._generation.get_policy(event.tenant_id, session.project_id)
            if policy is None or not self._settings.vision_worker_secret:
                raise ValueError("visual worker is unavailable")
            async with httpx.AsyncClient(timeout=runtime.vision.max_session_seconds) as client:
                response = await client.post(
                    f"{self._settings.playwright_worker_url.rstrip('/')}/visual-explorations",
                    headers={"X-Auto-At-Vision-Worker-Secret": self._settings.vision_worker_secret},
                    json={
                        "contract_version": "v1",
                        "id": str(session.id),
                        "target_url": session.target_url,
                        "allowed_origins": policy.allowed_origins,
                        "max_steps": runtime.vision.max_steps,
                        "max_screenshot_bytes": runtime.vision.max_screenshot_bytes,
                        "max_session_seconds": runtime.vision.max_session_seconds,
                    },
                )
                response.raise_for_status()
            root = Path(self._settings.artifact_root, "vision", str(session.id)).resolve()
            session.state = "running"
            for sequence in range(1, runtime.vision.max_steps + 1):
                path = (root / f"{sequence}.png").resolve()
                if root not in path.parents or not path.is_file():
                    raise ValueError("visual screenshot is unavailable")
                image = path.read_bytes()
                if len(image) > runtime.vision.max_screenshot_bytes or not image.startswith(
                    b"\x89PNG\r\n\x1a\n"
                ):
                    raise ValueError("visual screenshot failed verification")
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
                    sequence=sequence,
                    image=image,
                ) as image_url:
                    outcome = await execute_visual_action(
                        screenshot=image, content_type="image/png", image_url=image_url,
                        task_intent=intent, policy=runtime.vision,
                        model=create_vision_language_model(self._settings, runtime.vision),
                    )
                if outcome.action is None:
                    return self._unavailable(session, "vision model is unavailable")
                async with httpx.AsyncClient(timeout=runtime.vision.max_session_seconds) as client:
                    response = await client.post(
                        f"{self._settings.playwright_worker_url.rstrip('/')}/visual-explorations/{session.id}/actions",
                        headers={
                            "X-Auto-At-Vision-Worker-Secret": self._settings.vision_worker_secret
                        },
                        json={"action": outcome.action.model_dump(mode="json")},
                    )
                    response.raise_for_status()
                safe_action = {"kind": outcome.action.kind, "confidence": outcome.action.confidence}
                for field in ("x", "y", "delta_y", "duration_ms"):
                    value = getattr(outcome.action, field, None)
                    if isinstance(value, (int, float)):
                        safe_action[field] = value
                self._sessions.add_action(
                    VisualActionProposalModel(
                        id=uuid4(),
                        tenant_id=session.tenant_id,
                        session_id=session.id,
                        correlation_id=session.correlation_id,
                        sequence=sequence,
                        action=safe_action,
                        evidence_checksum=hashlib.sha256(image).hexdigest(),
                        policy_version=session.policy_version,
                        provider=session.provider,
                        model=session.model,
                        prompt_version=session.prompt_version,
                    )
                )
                if outcome.action.kind == "stop":
                    session.state = "completed"
                    break
            else:
                session.state = "completed"
            if session.state == "completed":
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
            async with httpx.AsyncClient(timeout=10) as client:
                await client.delete(
                    f"{self._settings.playwright_worker_url.rstrip('/')}/visual-explorations/{session.id}",
                    headers={"X-Auto-At-Vision-Worker-Secret": self._settings.vision_worker_secret},
                )
            self._activities.append(
                ActivityEvent.create(
                    tenant_id=session.tenant_id,
                    correlation_id=session.correlation_id,
                    source="vision",
                    stage="action.proposed",
                    status=session.state,
                    safe_summary="Visual action candidate was recorded.",
                    occurred_at=datetime.now(UTC),
                    metadata={
                        "session_id": str(session.id),
                        "evidence_checksum": hashlib.sha256(image).hexdigest(),
                        "action_kind": outcome.action.kind,
                        "draft_handoff": session.state == "completed",
                    },
                )
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

    def _unavailable(self, session, reason: str) -> str:
        session.state, session.safe_failure_reason = "unavailable", reason
        self._activities.append(
            ActivityEvent.create(
                tenant_id=session.tenant_id,
                correlation_id=session.correlation_id,
                source="vision",
                stage="unavailable",
                status="unavailable",
                safe_summary="Visual exploration is unavailable.",
                occurred_at=datetime.now(UTC),
                metadata={"session_id": str(session.id)},
            )
        )
        return "unavailable"
