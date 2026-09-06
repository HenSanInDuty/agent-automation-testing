"""Privileged, tenant-admin-only Vision diagnostic reads."""

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from agents.vision.debug_evidence import EncryptedDebugEvidence, decrypt_debug_evidence
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from domain.runs import AuditEvent


class DebugEvidenceNotFoundError(LookupError):
    """Deliberately non-enumerating result for missing, expired, or unreadable evidence."""


@dataclass(frozen=True)
class DebugEvidenceMetadata:
    id: UUID
    diagnostic_code: str
    provider: str
    model: str
    prompt_version: str
    captured_at: datetime
    retention_until: datetime


@dataclass(frozen=True)
class DebugEvidencePayload(DebugEvidenceMetadata):
    payload: str


class ReadVisionDebugEvidence:
    def __init__(
        self,
        repository,
        audits,
        *,
        key: str | None,
        key_id: str | None,
        previous_key: str | None = None,
        previous_key_id: str | None = None,
    ) -> None:
        self._repository = repository
        self._audits = audits
        self._key = key
        self._key_id = key_id
        self._previous_key = previous_key
        self._previous_key_id = previous_key_id

    def list(
        self, *, tenant_id: str, principal: Principal, session_id: UUID
    ) -> list[DebugEvidenceMetadata]:
        self._authorize(tenant_id, principal, session_id, None, "vision.debug_evidence_listed")
        records = self._repository.list_debug_evidence_metadata(tenant_id, session_id)
        return [self._metadata(item) for item in records]

    def read(
        self, *, tenant_id: str, principal: Principal, session_id: UUID, evidence_id: UUID
    ) -> DebugEvidencePayload:
        self._authorize(tenant_id, principal, session_id, evidence_id, "vision.debug_evidence_read")
        record = self._repository.get_debug_evidence(tenant_id, evidence_id)
        if (
            record is None
            or record.session_id != session_id
            or record.retention_until <= datetime.now(UTC)
        ):
            self._audit(
                tenant_id,
                principal.subject,
                "vision.debug_evidence_unavailable",
                session_id,
                record,
            )
            raise DebugEvidenceNotFoundError
        try:
            payload = decrypt_debug_evidence(
                EncryptedDebugEvidence(
                    record.encrypted_payload,
                    record.key_id,
                    record.payload_checksum,
                    record.payload_byte_count,
                    record.redaction_version,
                ),
                key=self._key,
                key_id=self._key_id,
                previous_key=self._previous_key,
                previous_key_id=self._previous_key_id,
            )
        except Exception as error:
            self._audit(
                tenant_id,
                principal.subject,
                "vision.debug_evidence_unavailable",
                session_id,
                record,
            )
            raise DebugEvidenceNotFoundError from error
        self._audit(tenant_id, principal.subject, "vision.debug_evidence_read", session_id, record)
        metadata = self._metadata(record)
        return DebugEvidencePayload(**metadata.__dict__, payload=payload)

    def _authorize(self, tenant_id, principal, session_id, evidence_id, action) -> None:
        try:
            session = self._repository.get(tenant_id, session_id)
            if session is None:
                raise AuthorizationError("missing")
            require(actor_for_tenant(principal, tenant_id), Permission.READ_VISION_DEBUG_EVIDENCE)
        except AuthorizationError as error:
            self._audit(
                tenant_id, principal.subject, "vision.debug_evidence_denied", session_id, None
            )
            raise DebugEvidenceNotFoundError from error

    def _audit(self, tenant_id, actor, action, session_id, record) -> None:
        self._audits.append(
            AuditEvent(
                id=uuid4(),
                tenant_id=tenant_id,
                actor=actor,
                action=action,
                entity_type="vision_debug_evidence" if record else "visual_exploration_session",
                entity_id=record.id if record else session_id,
                correlation_id=record.correlation_id if record else uuid4(),
            )
        )

    @staticmethod
    def _metadata(record) -> DebugEvidenceMetadata:
        return DebugEvidenceMetadata(
            id=record.id,
            diagnostic_code=record.diagnostic_code,
            provider=record.provider,
            model=record.model,
            prompt_version=record.prompt_version,
            captured_at=record.captured_at,
            retention_until=record.retention_until,
        )
