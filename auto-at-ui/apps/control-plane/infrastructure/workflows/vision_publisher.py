"""Vision owns short transactions; legacy and other event handlers retain their adapters."""

from datetime import UTC, datetime

import httpx
from application.vision_trace_events import VisionTraceEventProcessor

from infrastructure.artifacts.rustfs import RustFSArtifactStore
from infrastructure.persistence.repositories import SqlAlchemyOutboxEventRepository
from infrastructure.persistence.session import transactional_session
from infrastructure.persistence.vision_unit_of_work import SqlAlchemyVisualTraceUnitOfWork
from infrastructure.vision.model_batch import VisionModelBatch
from infrastructure.vision_worker import HttpVisualWorker


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
