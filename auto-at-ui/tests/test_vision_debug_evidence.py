from datetime import UTC, datetime, timedelta

import pytest
from agents.vision.debug_evidence import (
    DebugEvidenceUnavailableError,
    decrypt_debug_evidence,
    encrypt_debug_evidence,
)
from agents.vision.diagnostics import VisualDiagnosticCapture


def test_debug_evidence_uses_its_own_key_id_and_detects_tampering() -> None:
    key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    capture = VisualDiagnosticCapture.from_content("token=top-secret")
    encrypted = encrypt_debug_evidence(capture, key=key, key_id="debug-v1")

    assert decrypt_debug_evidence(encrypted, key=key, key_id="debug-v1") == "[REDACTED]"
    with pytest.raises(DebugEvidenceUnavailableError):
        decrypt_debug_evidence(encrypted, key=key, key_id="debug-v2")
    with pytest.raises(DebugEvidenceUnavailableError):
        decrypt_debug_evidence(
            encrypted.__class__("bad", "debug-v1", None, 0), key=key, key_id="debug-v1"
        )


def test_debug_evidence_reads_a_previous_key_only_during_rotation() -> None:
    old_key = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
    new_key = "YWJjZGVmZ2hpamtsbW5vcHFyc3R1dnd4eXowMTIzNDU2Nzg="
    encrypted = encrypt_debug_evidence(
        VisualDiagnosticCapture.from_content("safe"), key=old_key, key_id="debug-v1"
    )

    assert (
        decrypt_debug_evidence(
            encrypted,
            key=new_key,
            key_id="debug-v2",
            previous_key=old_key,
            previous_key_id="debug-v1",
        )
        == "safe"
    )
    with pytest.raises(DebugEvidenceUnavailableError):
        decrypt_debug_evidence(encrypted, key=new_key, key_id="debug-v2")


class ExpiryRepository:
    def __init__(self, records, *, fail_once: bool = False):
        self.records = records
        self.fail_once = fail_once

    def list_expired_debug_evidence(self, before, limit):
        return [item for item in self.records if item.retention_until <= before][:limit]

    def delete_expired_debug_evidence(self, tenant_id, evidence_id):
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary storage error")
        for item in list(self.records):
            if item.tenant_id == tenant_id and item.id == evidence_id:
                self.records.remove(item)
                return True
        return False


class Evidence:
    def __init__(self, evidence_id, tenant_id, retention_until):
        self.id, self.tenant_id, self.retention_until = evidence_id, tenant_id, retention_until


class Audits:
    def __init__(self) -> None:
        self.items = []

    def append(self, event) -> None:
        self.items.append(event)


def test_debug_evidence_expiry_is_tenant_scoped_and_retry_safe() -> None:
    from uuid import uuid4

    from application.vision_debug_retention import (
        ExpireVisionDebugEvidence,
        VisionDebugExpiryResult,
    )

    now = datetime.now(UTC)
    first = Evidence(uuid4(), "tenant-a", now - timedelta(seconds=1))
    second = Evidence(uuid4(), "tenant-b", now + timedelta(days=1))
    repository = ExpiryRepository([first, second], fail_once=True)
    audits = Audits()

    expiry = ExpireVisionDebugEvidence(repository, audits)
    assert expiry.execute(now=now) == VisionDebugExpiryResult(0, 1, 1)
    assert expiry.execute(now=now) == VisionDebugExpiryResult(1, 0, 1)
    assert repository.records == [second]
    assert [event.action for event in audits.items] == [
        "vision.debug_evidence_expiry_attempted",
        "vision.debug_evidence_expiry_failed",
        "vision.debug_evidence_expiry_attempted",
        "vision.debug_evidence_deleted",
    ]
