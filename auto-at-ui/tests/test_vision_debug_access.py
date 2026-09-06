from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from agents.vision.debug_evidence import encrypt_debug_evidence
from agents.vision.diagnostics import VisualDiagnosticCapture
from application.vision_debug_evidence import DebugEvidenceNotFoundError, ReadVisionDebugEvidence
from domain.authorization import Principal, Role


class Repository:
    def __init__(self, session, evidence):
        self.session, self.evidence = session, evidence

    def get(self, tenant_id, session_id):
        return (
            self.session
            if tenant_id == self.session.tenant_id and session_id == self.session.id
            else None
        )

    def list_debug_evidence_metadata(self, tenant_id, session_id):
        return [self.evidence] if self.get(tenant_id, session_id) else []

    def get_debug_evidence(self, tenant_id, evidence_id):
        return (
            self.evidence
            if tenant_id == self.session.tenant_id and evidence_id == self.evidence.id
            else None
        )


class Audits:
    def __init__(self):
        self.items = []

    def append(self, event):
        self.items.append(event)


def test_only_non_service_tenant_admin_reads_redacted_evidence() -> None:
    key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    session_id, evidence_id = uuid4(), uuid4()
    session = SimpleNamespace(id=session_id, tenant_id="tenant-a")
    encrypted = encrypt_debug_evidence(
        VisualDiagnosticCapture.from_content("token=secret"), key=key, key_id="debug-v1"
    )
    evidence = SimpleNamespace(
        id=evidence_id,
        session_id=session_id,
        correlation_id=uuid4(),
        diagnostic_code="invalid_json",
        provider="hf",
        model="m",
        prompt_version="p",
        encrypted_payload=encrypted.ciphertext,
        key_id=encrypted.key_id,
        payload_checksum=encrypted.checksum,
        payload_byte_count=encrypted.byte_count,
        redaction_version=encrypted.redaction_version,
        captured_at=datetime.now(UTC),
        retention_until=datetime.now(UTC) + timedelta(days=1),
    )
    audits = Audits()
    use_case = ReadVisionDebugEvidence(
        Repository(session, evidence), audits, key=key, key_id="debug-v1"
    )
    admin = Principal("admin", {"tenant-a": frozenset({Role.TENANT_ADMIN})}, {})
    result = use_case.read(
        tenant_id="tenant-a", principal=admin, session_id=session_id, evidence_id=evidence_id
    )

    assert result.payload == "[REDACTED]"
    denied = Principal("service", {"tenant-a": frozenset({Role.TENANT_ADMIN})}, {}, is_service=True)
    with pytest.raises(DebugEvidenceNotFoundError):
        use_case.read(
            tenant_id="tenant-a", principal=denied, session_id=session_id, evidence_id=evidence_id
        )
    assert any(event.action == "vision.debug_evidence_denied" for event in audits.items)
