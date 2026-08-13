from uuid import uuid4

import pytest
from agents.shared.evidence import build_run_report_evidence_bundle
from agents.shared.runtime import EvidencePolicy
from auto_at.contracts.agent import RunReport, RunReportFailure, RunReportStatus
from auto_at.contracts.execution import Artifact, RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.entities import ArtifactRecord, RunReportRecord
from pydantic import ValidationError


class BytesReader:
    def __init__(self, value: bytes) -> None:
        self.value = value
        self.calls: list[tuple[ArtifactRecord, int]] = []

    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes:
        self.calls.append((artifact, max_bytes))
        return self.value


def test_run_report_contract_is_strict_and_bounded() -> None:
    with pytest.raises(ValidationError):
        RunReport.model_validate(
            {
                "deterministic_status": "failed",
                "headline": "Failed",
                "what_ran": "Checkout test",
                "unexpected": "not allowed",
            }
        )

    report = RunReport(
        deterministic_status="failed",
        headline="Checkout failed.",
        what_ran="One checkout test ran.",
        failure=RunReportFailure(
            stage="assertion",
            location="checkout.spec.ts:42",
            message="Expected total.",
        ),
    )
    assert report.failure is not None
    assert report.failure.location == "checkout.spec.ts:42"


def test_report_evidence_uses_only_allowlisted_redacted_text() -> None:
    run_id = uuid4()
    output_uri = "file:///artifacts/output.txt"
    result = ExecutionResult(
        run_id=run_id,
        correlation_id=uuid4(),
        status=RunStatus.FAILED,
        started_at="2026-08-13T00:00:00Z",
        completed_at="2026-08-13T00:00:01Z",
        summary="Assertion failed.",
        artifacts=[
            Artifact(kind="playwright-output", uri=output_uri, content_type="text/plain"),
            Artifact(
                kind="trace", uri="file:///artifacts/trace.zip", content_type="application/zip"
            ),
        ],
    )
    verified = [
        ArtifactRecord(
            id=uuid4(),
            tenant_id="tenant-a",
            run_id=run_id,
            kind="playwright-output",
            uri=output_uri,
            checksum="a" * 64,
            size=64,
            content_type="text/plain",
        ),
        ArtifactRecord(
            id=uuid4(),
            tenant_id="tenant-a",
            run_id=run_id,
            kind="trace",
            uri="file:///artifacts/trace.zip",
            checksum="b" * 64,
            size=64,
            content_type="application/zip",
        ),
    ]
    reader = BytesReader(b"password=not-for-prompt\nAssertion at checkout.spec.ts:42")

    bundle = build_run_report_evidence_bundle(
        result, EvidencePolicy(include_redacted_text=True), verified, reader
    )

    assert len(bundle.excerpts) == 1
    assert "not-for-prompt" not in bundle.excerpts[0].text
    assert "password=[REDACTED]" in bundle.excerpts[0].text
    assert len(reader.calls) == 1


def test_unavailable_report_cannot_persist_a_payload() -> None:
    with pytest.raises(ValueError, match="unavailable"):
        RunReportRecord.create(
            tenant_id="tenant-a",
            run_id=uuid4(),
            correlation_id=uuid4(),
            deterministic_status=RunStatus.FAILED,
            status=RunReportStatus.UNAVAILABLE,
            payload=RunReport(
                deterministic_status="failed", headline="Failed", what_ran="One test ran."
            ),
            input_hash="a" * 64,
        )
