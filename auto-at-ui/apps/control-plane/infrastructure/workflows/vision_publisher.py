"""Vision owns short transactions; legacy and other event handlers retain their adapters."""

from datetime import UTC, datetime

import httpx
from agents.shared.openrouter import create_vision_language_model
from agents.vision.executor import execute_visual_candidate_batch
from agents.vision.temporary_images import GoogleDriveTemporaryVisionImageStore
from application.vision_trace_events import VisionTraceEventProcessor

from infrastructure.artifacts.rustfs import RustFSArtifactStore
from infrastructure.persistence.repositories import SqlAlchemyOutboxEventRepository
from infrastructure.persistence.session import transactional_session
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisualTraceUnitOfWork
from infrastructure.vision_worker import HttpVisualWorker


class VisionModelBatch:
    def __init__(self, settings):
        self.settings = settings

    async def __call__(
        self,
        *,
        session,
        screenshot,
        task_intent,
        policy,
        max_candidates,
        guard,
        sequence,
        check_policy,
    ):
        settings = self.settings
        store = GoogleDriveTemporaryVisionImageStore(
            service_account_file=settings.google_drive_service_account_file,
            oauth_client_id=settings.google_drive_oauth_client_id,
            oauth_client_secret=settings.google_drive_oauth_client_secret,
            oauth_refresh_token=settings.google_drive_oauth_refresh_token,
            folder_id=settings.google_drive_vision_folder_id,
            ttl=settings.vision_temporary_url_ttl_seconds,
            delete_after_delivery=settings.google_drive_vision_delete_after_delivery,
        )
        async with store.deliver(
            tenant_id=session.tenant_id, session_id=session.id, sequence=sequence, image=screenshot
        ) as image_url:
            check_policy()
            return await execute_visual_candidate_batch(
                screenshot=screenshot,
                content_type="image/png",
                task_intent=task_intent,
                policy=policy,
                model=create_vision_language_model(settings, policy),
                image_url=image_url,
                max_candidates=max_candidates,
                guard=guard,
            )


async def publish_vision_once(factory, settings, *, handler=None):
    uow = SqlAlchemyVisualTraceUnitOfWork(factory, RustFSArtifactStore(settings))
    with transactional_session(factory) as session:
        events = SqlAlchemyOutboxEventRepository(session).list_unpublished(100)
    published = 0
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        processor = handler or VisionTraceEventProcessor(
            uow,
            HttpVisualWorker(client, settings.playwright_worker_url, settings.vision_worker_secret),
            settings,
            VisionModelBatch(settings),
        )
        for event in events:
            if event.event_type != "agent.visual_exploration.requested.v1":
                continue
            from uuid import UUID

            record = uow.get_session(event.tenant_id, UUID(event.payload["session_id"]))
            if record is None or record.trace_version != "v4":
                continue
            # This await is deliberately outside the outbox read/write transactions.
            outcome = await processor.execute(event)
            if outcome == "busy":
                continue
            with transactional_session(factory) as session:
                SqlAlchemyOutboxEventRepository(session).mark_published(event.id, datetime.now(UTC))
            published += 1
    return published
