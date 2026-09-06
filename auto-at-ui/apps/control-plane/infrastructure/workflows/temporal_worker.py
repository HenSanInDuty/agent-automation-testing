"""Run the local outbox publisher and Temporal worker in one development process."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from application.artifact_retention import ExpireArtifacts
from application.generation_events import GenerationEventProcessor
from application.reporting_events import ReportingEventProcessor
from application.runs import PublishOutbox
from application.triage_events import TriageEventProcessor
from application.vision_debug_retention import ExpireVisionDebugEvidence
from application.vision_events import VisionEventProcessor
from config import Settings
from temporalio.client import Client
from temporalio.worker import Worker

from infrastructure.artifacts.rustfs import RustFSArtifactStore
from infrastructure.observability import configure_logging, log_event
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyArtifactRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyProposalRepository,
    SqlAlchemyRunReportRepository,
    SqlAlchemyRunRepository,
    SqlAlchemyVisionRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.workflows.temporal import (
    TemporalWorkflowStarter,
    TestRunWorkflow,
    dispatch_test_run,
)

logger = logging.getLogger(__name__)


async def publish_forever(client: Client, settings: Settings) -> None:
    starter = TemporalWorkflowStarter(client, settings)
    session_factory = create_session_factory(settings)
    while True:
        try:
            with transactional_session(session_factory) as session:
                published = await PublishOutbox(
                    SqlAlchemyOutboxEventRepository(session),
                    starter,
                    TriageEventProcessor(
                        SqlAlchemyRunRepository(session),
                        SqlAlchemyConfigurationRepository(session),
                        SqlAlchemyProposalRepository(session),
                        settings,
                        SqlAlchemyActivityEventRepository(session),
                    ),
                    GenerationEventProcessor(
                        SqlAlchemyGenerationRepository(session),
                        SqlAlchemyConfigurationRepository(session),
                        SqlAlchemyAuditEventRepository(session),
                        settings,
                        SqlAlchemyActivityEventRepository(session),
                    ),
                    ReportingEventProcessor(
                        SqlAlchemyRunRepository(session),
                        SqlAlchemyConfigurationRepository(session),
                        SqlAlchemyArtifactRepository(session),
                        SqlAlchemyRunReportRepository(session),
                        RustFSArtifactStore(settings),
                        settings,
                        SqlAlchemyActivityEventRepository(session),
                    ),
                    VisionEventProcessor(
                        SqlAlchemyVisionRepository(session),
                        SqlAlchemyConfigurationRepository(session),
                        SqlAlchemyGenerationRepository(session),
                        SqlAlchemyAuditEventRepository(session),
                        SqlAlchemyActivityEventRepository(session),
                        SqlAlchemyOutboxEventRepository(session),
                        settings,
                    ),
                ).execute()
            if published:
                log_event(
                    logger,
                    logging.INFO,
                    "workflow.outbox.published",
                    "Outbox events published to Temporal.",
                    published_count=published,
                )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "workflow.outbox.publish_failed",
                "Outbox publication failed; events remain unpublished.",
            )
        await asyncio.sleep(settings.temporal_outbox_poll_interval_seconds)


async def expire_artifacts_forever(settings: Settings) -> None:
    session_factory = create_session_factory(settings)
    while True:
        try:
            with transactional_session(session_factory) as session:
                result = ExpireArtifacts(
                    SqlAlchemyArtifactRepository(session), RustFSArtifactStore(settings)
                ).execute()
            if result.deleted or result.failed:
                log_event(
                    logger,
                    logging.INFO,
                    "artifact.retention.completed",
                    "Artifact expiry batch completed.",
                    deleted_count=result.deleted,
                    failed_count=result.failed,
                )
        except Exception:
            log_event(
                logger, logging.ERROR, "artifact.retention.failed", "Artifact expiry batch failed."
            )
        await asyncio.sleep(settings.artifact_retention_cleanup_interval_seconds)


async def expire_vision_debug_evidence_forever(settings: Settings) -> None:
    """Deletion needs no decryption key, so key loss cannot extend retention."""
    session_factory = create_session_factory(settings)
    while True:
        try:
            with transactional_session(session_factory) as session:
                result = ExpireVisionDebugEvidence(
                    SqlAlchemyVisionRepository(session), SqlAlchemyAuditEventRepository(session)
                ).execute(
                    limit=settings.vision_debug_evidence_cleanup_batch_size
                )
            if result.overdue:
                log_event(
                    logger,
                    logging.INFO,
                    "vision.debug_evidence.expiry_completed",
                    "Vision debug-evidence expiry batch completed.",
                    deleted_count=result.deleted,
                    failed_count=result.failed,
                    overdue_count=result.overdue,
                )
        except Exception:
            log_event(
                logger,
                logging.ERROR,
                "vision.debug_evidence.expiry_failed",
                "Vision debug-evidence expiry batch failed.",
            )
        await asyncio.sleep(settings.vision_debug_evidence_cleanup_interval_seconds)


async def main() -> None:
    settings = Settings()
    configure_logging(settings, service="auto-at-temporal-worker")
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    publisher = asyncio.create_task(publish_forever(client, settings))
    retention = asyncio.create_task(expire_artifacts_forever(settings))
    vision_debug_retention = asyncio.create_task(expire_vision_debug_evidence_forever(settings))
    try:
        worker = Worker(
            client,
            task_queue=settings.temporal_task_queue,
            workflows=[TestRunWorkflow],
            activities=[dispatch_test_run],
            activity_executor=ThreadPoolExecutor(max_workers=2),
        )
        await worker.run()
    finally:
        publisher.cancel()
        retention.cancel()
        vision_debug_retention.cancel()
        await asyncio.gather(publisher, retention, vision_debug_retention, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
