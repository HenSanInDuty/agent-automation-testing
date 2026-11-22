from typing import Annotated

from application.generation_policy import GenerationPolicies
from config import Settings, get_settings
from fastapi import Depends
from infrastructure.codex_bridge.doctor import FileReadiness
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
)
from infrastructure.persistence.session import create_session_factory, transactional_session

from api.v1.dependencies.authorization import current_tenant


def generation_policies(
    settings: Annotated[Settings, Depends(get_settings)],
    tenant_id: Annotated[str, Depends(current_tenant)],
):
    del tenant_id
    with transactional_session(create_session_factory(settings)) as session:
        yield GenerationPolicies(settings, SqlAlchemyConfigurationRepository(session),
                                 SqlAlchemyAuditEventRepository(session), FileReadiness(settings))
