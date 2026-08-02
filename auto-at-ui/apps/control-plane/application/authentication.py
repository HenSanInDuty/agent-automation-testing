"""Account and session use cases.  HTTP and SQLAlchemy stay at the edges."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from domain.authorization import Role
from infrastructure.persistence.models import SessionModel, TenantMembershipModel, UserModel
from sqlalchemy import select
from sqlalchemy.orm import Session


class AuthenticationError(ValueError):
    """Intentionally non-specific authentication failure."""


class PasswordPolicyError(ValueError):
    pass


def utcnow() -> datetime:
    return datetime.now(UTC)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class PasswordService:
    def __init__(self) -> None:
        self._hasher = PasswordHasher()

    @staticmethod
    def validate(password: str) -> None:
        if (
            len(password) < 12
            or not any(c.islower() for c in password)
            or not any(c.isupper() for c in password)
            or not any(c.isdigit() for c in password)
        ):
            raise PasswordPolicyError(
                "Password must be at least 12 characters with upper, lower, and digit."
            )

    def hash(self, password: str) -> str:
        self.validate(password)
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            # Preserve a comparable code path for malformed/stale hashes.
            hmac.compare_digest(digest(password), digest("invalid-password"))
            return False


@dataclass(frozen=True)
class Account:
    id: UUID
    email: str
    enabled: bool
    force_password_change: bool
    role: Role


@dataclass(frozen=True)
class IssuedSession:
    token: str
    csrf_token: str
    account: Account


class AccountService:
    def __init__(self, session: Session, password_service: PasswordService | None = None) -> None:
        self._session = session
        self._passwords = password_service or PasswordService()

    def bootstrap_admin(self, tenant_id: str, email: str, temporary_password: str) -> Account:
        existing = self._user_by_email(email)
        if existing is not None:
            membership = self._membership(existing.id, tenant_id)
            if membership is None or Role(membership.role) is not Role.TENANT_ADMIN:
                raise AuthenticationError(
                    "Bootstrap account already exists with a different grant."
                )
            return self._account(existing, membership)
        return self._create(tenant_id, email, temporary_password, Role.TENANT_ADMIN, True)

    def login(self, tenant_id: str, email: str, password: str, ttl_seconds: int) -> IssuedSession:
        user = self._user_by_email(email)
        membership = self._membership(user.id, tenant_id) if user else None
        if (
            user is None
            or membership is None
            or not user.enabled
            or not self._passwords.verify(user.password_hash, password)
        ):
            raise AuthenticationError("Invalid email or password.")
        token, csrf_token = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self._session.add(
            SessionModel(
                token_hash=digest(token),
                user_id=user.id,
                tenant_id=tenant_id,
                csrf_token_hash=digest(csrf_token),
                expires_at=utcnow() + timedelta(seconds=ttl_seconds),
                revoked_at=None,
                created_at=utcnow(),
            )
        )
        self._session.flush()
        return IssuedSession(token, csrf_token, self._account(user, membership))

    def principal(self, token: str) -> Account | None:
        record = self._session.scalar(
            select(SessionModel).where(SessionModel.token_hash == digest(token))
        )
        if record is None or record.revoked_at is not None or record.expires_at <= utcnow():
            return None
        user = self._session.get(UserModel, record.user_id)
        membership = self._membership(record.user_id, record.tenant_id)
        if user is None or membership is None or not user.enabled:
            return None
        return self._account(user, membership)

    def csrf_is_valid(self, token: str, csrf_token: str | None) -> bool:
        record = self._session.scalar(
            select(SessionModel).where(SessionModel.token_hash == digest(token))
        )
        return bool(
            record
            and csrf_token
            and record.revoked_at is None
            and record.expires_at > utcnow()
            and hmac.compare_digest(record.csrf_token_hash, digest(csrf_token))
        )

    def logout(self, token: str) -> None:
        record = self._session.scalar(
            select(SessionModel).where(SessionModel.token_hash == digest(token))
        )
        if record is not None and record.revoked_at is None:
            record.revoked_at = utcnow()

    def change_password(self, account: Account, current_password: str, new_password: str) -> None:
        user = self._session.get(UserModel, account.id)
        if user is None or not self._passwords.verify(user.password_hash, current_password):
            raise AuthenticationError("Invalid current password.")
        user.password_hash = self._passwords.hash(new_password)
        user.force_password_change = False
        user.updated_at = utcnow()

    def create_user(
        self, tenant_id: str, email: str, role: Role, temporary_password: str
    ) -> Account:
        if self._user_by_email(email) is not None:
            raise ValueError("A user with this email already exists.")
        return self._create(tenant_id, email, temporary_password, role, True)

    def list_users(self, tenant_id: str) -> list[Account]:
        rows = self._session.execute(
            select(UserModel, TenantMembershipModel)
            .join(TenantMembershipModel, TenantMembershipModel.user_id == UserModel.id)
            .where(TenantMembershipModel.tenant_id == tenant_id)
            .order_by(UserModel.email)
        ).all()
        return [self._account(user, membership) for user, membership in rows]

    def set_role(self, tenant_id: str, user_id: UUID, role: Role) -> Account:
        membership = self._membership(user_id, tenant_id)
        user = self._session.get(UserModel, user_id)
        if membership is None or user is None:
            raise AuthenticationError("User not found.")
        membership.role = role.value
        return self._account(user, membership)

    def disable(self, tenant_id: str, user_id: UUID) -> Account:
        membership = self._membership(user_id, tenant_id)
        user = self._session.get(UserModel, user_id)
        if membership is None or user is None:
            raise AuthenticationError("User not found.")
        user.enabled = False
        user.updated_at = utcnow()
        return self._account(user, membership)

    def _create(
        self, tenant_id: str, email: str, password: str, role: Role, force: bool
    ) -> Account:
        normalized = email.strip().lower()
        now = utcnow()
        user = UserModel(
            id=uuid4(),
            email=normalized,
            password_hash=self._passwords.hash(password),
            enabled=True,
            force_password_change=force,
            created_at=now,
            updated_at=now,
        )
        membership = TenantMembershipModel(
            id=uuid4(), tenant_id=tenant_id, user_id=user.id, role=role.value, created_at=now
        )
        self._session.add_all([user, membership])
        self._session.flush()
        return self._account(user, membership)

    def _user_by_email(self, email: str) -> UserModel | None:
        return self._session.scalar(
            select(UserModel).where(UserModel.email == email.strip().lower())
        )

    def _membership(self, user_id: UUID, tenant_id: str) -> TenantMembershipModel | None:
        return self._session.scalar(
            select(TenantMembershipModel).where(
                TenantMembershipModel.user_id == user_id,
                TenantMembershipModel.tenant_id == tenant_id,
            )
        )

    @staticmethod
    def _account(user: UserModel, membership: TenantMembershipModel) -> Account:
        return Account(
            user.id, user.email, user.enabled, user.force_password_change, Role(membership.role)
        )
