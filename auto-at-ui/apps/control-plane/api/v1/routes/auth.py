"""Cookie session authentication and tenant account administration."""

from typing import Annotated
from uuid import UUID

from application.authentication import (
    Account,
    AccountService,
    AuthenticationError,
    PasswordPolicyError,
)
from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    Role,
    actor_for_tenant,
    require,
)
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, Field

from api.v1.dependencies.authorization import current_account, current_principal, require_csrf

router = APIRouter(prefix="/auth", tags=["authentication"])
admin_router = APIRouter(prefix="/admin/users", tags=["administration"])


class LoginRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=1024)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=1024)
    new_password: str = Field(min_length=12, max_length=1024)


class CreateUserRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: Role


class RoleRequest(BaseModel):
    role: Role


class UserResponse(BaseModel):
    id: UUID
    email: str
    role: Role
    enabled: bool
    force_password_change: bool


class ProvisionedUserResponse(UserResponse):
    temporary_password: str


class MeResponse(UserResponse):
    tenant_id: str


def response_account(account: Account) -> UserResponse:
    return UserResponse(
        id=account.id,
        email=account.email,
        role=account.role,
        enabled=account.enabled,
        force_password_change=account.force_password_change,
    )


def set_session_cookies(
    response: Response, settings: Settings, token: str, csrf_token: str
) -> None:
    secure = settings.environment != "local"
    response.set_cookie(
        settings.session_cookie_name,
        token,
        httponly=True,
        secure=secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf_token,
        httponly=False,
        secure=secure,
        samesite="lax",
        max_age=settings.session_ttl_seconds,
        path="/",
    )


@router.post("/login", response_model=MeResponse)
def login(
    body: LoginRequest,
    response: Response,
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    # This in-process limiter is a local safety net; production needs a shared limiter.
    attempts = getattr(request.app.state, "login_attempts", {})
    key = f"{request.client.host if request.client else 'unknown'}:{body.email.lower()}"
    if attempts.get(key, 0) >= settings.auth_login_max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Try again later."
        )
    try:
        with transactional_session(create_session_factory(settings)) as session:
            issued = AccountService(session).login(
                body.tenant_id, str(body.email), body.password, settings.session_ttl_seconds
            )
        attempts.pop(key, None)
    except AuthenticationError as error:
        attempts[key] = attempts.get(key, 0) + 1
        request.app.state.login_attempts = attempts
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password."
        ) from error
    request.app.state.login_attempts = attempts
    set_session_cookies(response, settings, issued.token, issued.csrf_token)
    account = response_account(issued.account)
    return MeResponse(**account.model_dump(), tenant_id=body.tenant_id)


@router.post(
    "/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_csrf)]
)
def logout(
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    token: Annotated[str | None, Cookie(alias="auto_at_session")] = None,
) -> Response:
    if token:
        with transactional_session(create_session_factory(settings)) as session:
            AccountService(session).logout(token)
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=MeResponse)
def me(account: Annotated[Account, Depends(current_account)], request: Request) -> MeResponse:
    return MeResponse(**response_account(account).model_dump(), tenant_id=request.state.tenant_id)


@router.post("/change-password", response_model=MeResponse, dependencies=[Depends(require_csrf)])
def change_password(
    body: ChangePasswordRequest,
    account: Annotated[Account, Depends(current_account)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> MeResponse:
    try:
        with transactional_session(create_session_factory(settings)) as session:
            AccountService(session).change_password(
                account, body.current_password, body.new_password
            )
    except (AuthenticationError, PasswordPolicyError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    updated = Account(account.id, account.email, account.enabled, False, account.role)
    return MeResponse(**response_account(updated).model_dump(), tenant_id=request.state.tenant_id)


def tenant_admin(principal: Principal, request: Request) -> str:
    tenant_id = request.state.tenant_id
    try:
        require(actor_for_tenant(principal, tenant_id), Permission.MANAGE_TENANT)
    except AuthorizationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.") from error
    return tenant_id


@admin_router.get("", response_model=list[UserResponse])
def list_users(
    principal: Annotated[Principal, Depends(current_principal)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[UserResponse]:
    tenant_id = tenant_admin(principal, request)
    with create_session_factory(settings)() as session:
        return [
            response_account(account) for account in AccountService(session).list_users(tenant_id)
        ]


@admin_router.post(
    "",
    response_model=ProvisionedUserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_user(
    body: CreateUserRequest,
    principal: Annotated[Principal, Depends(current_principal)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProvisionedUserResponse:
    tenant_id = tenant_admin(principal, request)
    temporary_password = "Aa1!" + __import__("secrets").token_urlsafe(16)
    try:
        with transactional_session(create_session_factory(settings)) as session:
            account = AccountService(session).create_user(
                tenant_id, str(body.email), body.role, temporary_password
            )
    except (ValueError, PasswordPolicyError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return ProvisionedUserResponse(
        **response_account(account).model_dump(), temporary_password=temporary_password
    )


@admin_router.put(
    "/{user_id}/role", response_model=UserResponse, dependencies=[Depends(require_csrf)]
)
def change_role(
    user_id: UUID,
    body: RoleRequest,
    principal: Annotated[Principal, Depends(current_principal)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    tenant_id = tenant_admin(principal, request)
    try:
        with transactional_session(create_session_factory(settings)) as session:
            account = AccountService(session).set_role(tenant_id, user_id, body.role)
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.") from error
    return response_account(account)


@admin_router.delete(
    "/{user_id}", response_model=UserResponse, dependencies=[Depends(require_csrf)]
)
def disable_user(
    user_id: UUID,
    principal: Annotated[Principal, Depends(current_principal)],
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> UserResponse:
    tenant_id = tenant_admin(principal, request)
    try:
        with transactional_session(create_session_factory(settings)) as session:
            account = AccountService(session).disable(tenant_id, user_id)
    except AuthenticationError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.") from error
    return response_account(account)
