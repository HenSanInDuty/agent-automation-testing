"""Vision policy composition and transaction ownership."""

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID, uuid4

from application.vision_policy import VisionPolicies
from config import Settings, get_settings
from fastapi import Depends
from infrastructure.observability.telemetry import current_trace_context
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session

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
