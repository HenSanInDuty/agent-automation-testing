"""Session-cookie principal adapter with an explicitly local header fallback."""

from typing import Annotated

from application.authentication import Account, AccountService
from config import Settings, get_settings
from domain.authorization import Principal, Role
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from infrastructure.persistence.session import create_session_factory


def _local_principal(
    settings: Settings, tenant_id: str | None, actor_id: str | None, roles: str | None
) -> Principal:
    if settings.auth_mode != "local" or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
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
        actor_id or "local-developer", {tenant_id: parsed_roles}, {}, Role.SERVICE in parsed_roles
    )


def current_principal(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_token: Annotated[str | None, Cookie(alias="auto_at_session")] = None,
    tenant_id: Annotated[str | None, Header(alias="X-Tenant-Id")] = None,
    actor_id: Annotated[str | None, Header(alias="X-Actor-Id")] = None,
    roles: Annotated[str | None, Header(alias="X-Actor-Roles")] = None,
) -> Principal:
    if session_token:
        with create_session_factory(settings)() as session:
            account = AccountService(session).principal(session_token)
        if account is not None:
            request.state.tenant_id = _session_tenant(session_token, settings)
            request.state.session_authenticated = True
            return Principal(
                str(account.id), {request.state.tenant_id: frozenset({account.role})}, {}
            )
    principal = _local_principal(settings, tenant_id, actor_id, roles)
    request.state.tenant_id = tenant_id
    request.state.session_authenticated = False
    return principal


def _session_tenant(token: str, settings: Settings) -> str:
    # AccountService validates expiry/revocation; this lookup simply supplies the selected tenant.
    from application.authentication import digest
    from infrastructure.persistence.models import SessionModel
    from sqlalchemy import select

    with create_session_factory(settings)() as session:
        record = session.scalar(
            select(SessionModel).where(SessionModel.token_hash == digest(token))
        )
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
            )
        return record.tenant_id


def current_account(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_token: Annotated[str | None, Cookie(alias="auto_at_session")] = None,
) -> Account:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
        )
    with create_session_factory(settings)() as session:
        account = AccountService(session).principal(session_token)
        if account is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required."
            )
        request.state.tenant_id = _session_tenant(session_token, settings)
        request.state.session_authenticated = True
        return account


def current_tenant(
    request: Request, principal: Annotated[Principal, Depends(current_principal)]
) -> str:
    del principal
    return request.state.tenant_id


def require_csrf(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    session_token: Annotated[str | None, Cookie(alias="auto_at_session")] = None,
    csrf_cookie: Annotated[str | None, Cookie(alias="auto_at_csrf")] = None,
    csrf_header: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    # Existing local header clients deliberately remain usable until M6 removes the dev adapter.
    if not session_token and settings.auth_mode == "local":
        return
    if not session_token or not csrf_cookie or csrf_cookie != csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed.")
    with create_session_factory(settings)() as session:
        if not AccountService(session).csrf_is_valid(session_token, csrf_cookie):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed."
            )
