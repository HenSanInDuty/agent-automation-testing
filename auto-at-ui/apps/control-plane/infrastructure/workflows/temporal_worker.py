"""Run the local outbox publisher and Temporal worker in one development process."""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from application.runs import PublishOutbox
from config import Settings
from temporalio.client import Client
from temporalio.worker import Worker

from infrastructure.persistence.repositories import SqlAlchemyOutboxEventRepository
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.workflows.temporal import (
    TemporalWorkflowStarter,
    TestRunWorkflow,
    dispatch_test_run,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def publish_forever(client: Client, settings: Settings) -> None:
    starter = TemporalWorkflowStarter(client, settings)
    session_factory = create_session_factory(settings)
    while True:
        try:
            with transactional_session(session_factory) as session:
                published = await PublishOutbox(
                    SqlAlchemyOutboxEventRepository(session), starter
                ).execute()
            if published:
                logger.info("published %s run event(s) to Temporal", published)
        except Exception:
            logger.exception("outbox publication failed; events remain unpublished")
        await asyncio.sleep(settings.temporal_outbox_poll_interval_seconds)


async def main() -> None:
    settings = Settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    publisher = asyncio.create_task(publish_forever(client, settings))
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
        await asyncio.gather(publisher, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
