"""Local development principal adapter; production IdPs plug in at this boundary."""

from typing import Annotated

from config import Settings, get_settings
from domain.authorization import Principal, Role
from fastapi import Depends, Header, HTTPException, status


def current_principal(
    settings: Annotated[Settings, Depends(get_settings)],
    tenant_id: Annotated[str, Header(alias="X-Tenant-Id", min_length=1)],
    actor_id: Annotated[str | None, Header(alias="X-Actor-Id")] = None,
    roles: Annotated[str | None, Header(alias="X-Actor-Roles")] = None,
) -> Principal:
    """Construct a local principal; production adapters must validate an OIDC token."""
    if settings.auth_mode != "local":
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="An OIDC principal adapter is required outside local mode.",
        )
    try:
        parsed_roles = frozenset(
            Role(role.strip()) for role in (roles or "tenant_admin").split(",")
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid role."
        ) from error
    return Principal(
        subject=actor_id or "local-developer",
        tenant_roles={tenant_id: parsed_roles},
        project_roles={},
        is_service=Role.SERVICE in parsed_roles,
    )
