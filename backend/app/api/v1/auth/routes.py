"""
api/v1/auth/routes.py – Authentication and user management endpoints.

Endpoints:
    POST   /auth/login              – obtain JWT token (form: username + password)
    GET    /auth/me                 – current user profile
    POST   /auth/users              – create user (admin only)
    GET    /auth/users              – list all users (admin only)
    GET    /auth/users/{username}   – get user by username (admin only)
    PUT    /auth/users/{username}   – update user role / name (admin only)
    DELETE /auth/users/{username}   – delete user (admin only)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

from app.db.models import UserDocument, UserRole
from app.services.auth_service import create_access_token, hash_password, verify_password

from ..deps import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Auth"])


# ─────────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────────


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    role: str
    full_name: str


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    password: str = Field(..., min_length=6)
    full_name: str = ""
    role: UserRole = UserRole.QA


class UserUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=6)


class UserResponse(BaseModel):
    username: str
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_user_or_404(username: str) -> UserDocument:
    user = await UserDocument.find_one(UserDocument.username == username)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{username}' not found.")
    return user


def _to_response(user: UserDocument) -> UserResponse:
    return UserResponse(
        username=user.username,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Obtain a JWT access token",
)
async def login(form: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    user = await UserDocument.find_one(UserDocument.username == form.username)
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is disabled.")

    token = create_access_token(user.username, extra={"role": user.role.value})
    return TokenResponse(
        access_token=token,
        username=user.username,
        role=user.role.value,
        full_name=user.full_name,
    )


@router.get("/me", response_model=UserResponse, summary="Get current user profile")
async def get_me(current_user: UserDocument = Depends(get_current_user)) -> UserResponse:
    return _to_response(current_user)


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user (admin only)",
)
async def create_user(
    body: UserCreateRequest,
    _: UserDocument = Depends(require_admin),
) -> UserResponse:
    existing = await UserDocument.find_one(UserDocument.username == body.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Username '{body.username}' already exists.")

    user = UserDocument(
        username=body.username,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role=body.role,
    )
    await user.insert()
    logger.info("Created user '%s' with role %s", user.username, user.role)
    return _to_response(user)


@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="List all users (admin only)",
)
async def list_users(_: UserDocument = Depends(require_admin)) -> list[UserResponse]:
    users = await UserDocument.find_all().to_list()
    return [_to_response(u) for u in users]


@router.get(
    "/users/{username}",
    response_model=UserResponse,
    summary="Get user by username (admin only)",
)
async def get_user(
    username: str,
    _: UserDocument = Depends(require_admin),
) -> UserResponse:
    user = await _get_user_or_404(username)
    return _to_response(user)


@router.put(
    "/users/{username}",
    response_model=UserResponse,
    summary="Update user (admin only)",
)
async def update_user(
    username: str,
    body: UserUpdateRequest,
    current_admin: UserDocument = Depends(require_admin),
) -> UserResponse:
    user = await _get_user_or_404(username)

    # Prevent admin from downgrading themselves
    if user.username == current_admin.username and body.role is not None and body.role != UserRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot change your own admin role.")

    updates: dict = {"updated_at": datetime.now(timezone.utc)}
    if body.full_name is not None:
        updates["full_name"] = body.full_name
    if body.role is not None:
        updates["role"] = body.role
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.password is not None:
        updates["hashed_password"] = hash_password(body.password)

    await user.update({"$set": updates})
    await user.sync()
    return _to_response(user)


@router.delete(
    "/users/{username}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete user (admin only)",
)
async def delete_user(
    username: str,
    current_admin: UserDocument = Depends(require_admin),
) -> None:
    if username == current_admin.username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own account.")
    user = await _get_user_or_404(username)
    await user.delete()
    logger.info("Deleted user '%s'", username)
