"""Authorized, metadata-safe access to private Vision replay evidence."""

from uuid import UUID, uuid4

from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from domain.runs import AuditEvent


class VisionReplayNotFoundError(LookupError):
    """Return a non-enumerating response for missing or unauthorized replay data."""


class VisionReplayDeletionError(RuntimeError):
    """A byte deletion failed, so metadata intentionally remains available for retry."""


class VisionReplay:
    def __init__(self, sessions, store, audits) -> None:
        self._sessions, self._store, self._audits = sessions, store, audits

    def list(self, *, tenant_id: str, principal: Principal, session_id: UUID):
        self._session(tenant_id, principal, session_id, Permission.READ)
        frames = self._sessions.list_replay_frames(tenant_id, session_id)
        actions = self._sessions.list_actions(tenant_id, session_id)
        return frames, actions

    def read(self, *, tenant_id: str, principal: Principal, session_id: UUID, frame_id: UUID):
        self._session(tenant_id, principal, session_id, Permission.READ)
        frame = self._sessions.get_replay_frame(tenant_id, session_id, frame_id)
        if frame is None:
            raise VisionReplayNotFoundError
        content = self._store.read_replay_frame(frame)
        self._audit(tenant_id, principal.subject, "vision.replay_frame_read", frame_id, session_id)
        return content

    def delete_one(
        self, *, tenant_id: str, principal: Principal, session_id: UUID, frame_id: UUID
    ) -> bool:
        self._session(tenant_id, principal, session_id, Permission.MANAGE_TENANT)
        frame = self._sessions.get_replay_frame(tenant_id, session_id, frame_id)
        if frame is None:
            return False
        self._audit(
            tenant_id,
            principal.subject,
            "vision.replay_frame_delete_requested",
            frame_id,
            session_id,
        )
        try:
            self._store.delete_replay_frame(frame)
        except Exception as error:
            self._audit(
                tenant_id,
                principal.subject,
                "vision.replay_frame_delete_failed",
                frame_id,
                session_id,
            )
            raise VisionReplayDeletionError from error
        deleted = self._sessions.delete_replay_frame(tenant_id, session_id, frame_id)
        self._audit(
            tenant_id,
            principal.subject,
            "vision.replay_frame_delete_completed",
            frame_id,
            session_id,
        )
        return deleted

    def delete_all(self, *, tenant_id: str, principal: Principal, session_id: UUID) -> int:
        self._session(tenant_id, principal, session_id, Permission.MANAGE_TENANT)
        frames = self._sessions.list_replay_frames(tenant_id, session_id)
        deleted = 0
        for frame in frames:
            if self.delete_one(
                tenant_id=tenant_id,
                principal=principal,
                session_id=session_id,
                frame_id=frame.id,
            ):
                deleted += 1
        return deleted

    def _session(self, tenant_id, principal, session_id, permission):
        session = self._sessions.get(tenant_id, session_id)
        try:
            # Replay screenshots are human-facing private evidence.  A service's
            # generic project READ grant must not create a new byte/metadata path.
            if session is None or principal.is_service:
                raise AuthorizationError("missing")
            require(actor_for_tenant(principal, tenant_id, session.project_id), permission)
        except AuthorizationError as error:
            raise VisionReplayNotFoundError from error
        return session

    def _audit(self, tenant_id, actor, action, frame_id, session_id) -> None:
        self._audits.append(
            AuditEvent(
                id=uuid4(), tenant_id=tenant_id, actor=actor, action=action,
                entity_type="visual_replay_frame",
                entity_id=frame_id,
                correlation_id=self._sessions.get(tenant_id, session_id).correlation_id,
            )
        )
