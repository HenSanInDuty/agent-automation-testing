"""Vision policy composition and transaction ownership."""

from collections.abc import AsyncIterator, Iterator
from typing import Annotated
from uuid import UUID, uuid4

from application.vision import SubmitVisualExploration
from application.vision_policy import VisionPolicies
from application.vision_reload import ReloadVisualExploration
from application.vision_screen import VisionScreen
from config import Settings, get_settings
from fastapi import Depends
from httpx import AsyncClient
from infrastructure.observability.telemetry import current_trace_context
from infrastructure.persistence.repositories import (
    SqlAlchemyActivityEventRepository,
    SqlAlchemyAuditEventRepository,
    SqlAlchemyCatalogRepository,
    SqlAlchemyConfigurationRepository,
    SqlAlchemyGenerationRepository,
    SqlAlchemyOutboxEventRepository,
    SqlAlchemyVisionRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session
from infrastructure.vision_worker import HttpVisualWorker

from api.v1.dependencies.authorization import current_tenant


def vision_policies(
    settings: Annotated[Settings, Depends(get_settings)],
    tenant_id: Annotated[str, Depends(current_tenant)],
) -> Iterator[VisionPolicies]:
    # Authentication precedes database access. All use-case writes share this transaction.
    del tenant_id
    with transactional_session(create_session_factory(settings)) as session:
        yield VisionPolicies(
            settings, SqlAlchemyConfigurationRepository(session),
            SqlAlchemyAuditEventRepository(session),
        )


def vision_policy_correlation_id() -> UUID:
    context = current_trace_context()
    return context.correlation_id if context is not None else uuid4()


async def vision_screen(
    settings: Annotated[Settings, Depends(get_settings)],
    tenant_id: Annotated[str, Depends(current_tenant)],
) -> AsyncIterator[VisionScreen]:
    del tenant_id
    async with AsyncClient(timeout=4) as client:
        with transactional_session(create_session_factory(settings)) as session:
            yield VisionScreen(
                SqlAlchemyVisionRepository(session),
                HttpVisualWorker(
                    client, settings.playwright_worker_url, settings.vision_worker_secret or "",
                ),
            )


def vision_reload(
    settings: Annotated[Settings, Depends(get_settings)],
    tenant_id: Annotated[str, Depends(current_tenant)],
) -> Iterator[ReloadVisualExploration]:
    del tenant_id
    with transactional_session(create_session_factory(settings)) as session:
        repository = SqlAlchemyVisionRepository(session)
        configs = SqlAlchemyConfigurationRepository(session)
        submit = SubmitVisualExploration(
            repository, configs, SqlAlchemyCatalogRepository(session),
            SqlAlchemyGenerationRepository(session), SqlAlchemyAuditEventRepository(session),
            SqlAlchemyActivityEventRepository(session), SqlAlchemyOutboxEventRepository(session),
        )
        yield ReloadVisualExploration(repository, configs, submit, settings)
