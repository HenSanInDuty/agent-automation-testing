"""Build bounded, redacted evidence bundles for advisory agent work."""

from collections.abc import Iterable
from hashlib import sha256
from json import dumps
from typing import Protocol

from auto_at.contracts.agent import (
    EvidenceBundle,
    EvidenceReference,
    RedactedTextExcerpt,
    RunReportEvidenceBundle,
)
from auto_at.contracts.execution import Artifact, TestExecutionResult
from domain.entities import ArtifactRecord

from agents.shared.redaction import redact_mapping, redact_value
from agents.shared.runtime import EvidencePolicy

REDACTION_POLICY_VERSION = "v1"
REPORT_RAW_ARTIFACT_BYTES = 32_768
REPORT_REDACTED_ARTIFACT_BYTES = 16_384
REPORT_MAX_TEXT_ARTIFACTS = 4
REPORT_TEXTUAL_KINDS = frozenset({"playwright-output", "worker-result"})


class VerifiedArtifactTextReader(Protocol):
    """Reads only a verified, run-scoped artifact after enforcing a raw-byte cap."""

    def read_verified_bytes(self, artifact: ArtifactRecord, max_bytes: int) -> bytes: ...


def build_evidence_bundle(result: TestExecutionResult, policy: EvidencePolicy) -> EvidenceBundle:
    """Convert a deterministic result into the only evidence shape an agent may receive."""
    metadata = redact_mapping(result.runner_metadata) if policy.include_metadata else {}
    artifacts = _artifact_references(result.artifacts, policy)
    summary = (
        redact_value(result.summary)
        if policy.include_redacted_text
        else "Summary excluded by policy."
    )
    bundle_without_hash = {
        "run_id": str(result.run_id),
        "correlation_id": str(result.correlation_id),
        "deterministic_status": result.status.value,
        "summary": summary,
        "runner_metadata": metadata,
        "artifacts": [artifact.model_dump(mode="json") for artifact in artifacts],
        "redaction_policy_version": REDACTION_POLICY_VERSION,
    }
    input_hash = sha256(
        dumps(bundle_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return EvidenceBundle.model_validate({"input_hash": input_hash, **bundle_without_hash})


def build_run_report_evidence_bundle(
    result: TestExecutionResult,
    policy: EvidencePolicy,
    verified_artifacts: Iterable[ArtifactRecord],
    reader: VerifiedArtifactTextReader,
) -> RunReportEvidenceBundle:
    """Add only allowlisted, bounded redacted text to the ordinary evidence bundle.

    Artifact records must originate from the tenant/run-scoped repository.  The
    reader verifies each local object before bytes are returned, so no raw or
    unverified file crosses the agent boundary.
    """
    base = build_evidence_bundle(result, policy)
    excerpts: list[RedactedTextExcerpt] = []
    permitted_uris = {str(artifact.uri) for artifact in result.artifacts}
    if policy.include_redacted_text:
        for artifact in verified_artifacts:
            if len(excerpts) >= REPORT_MAX_TEXT_ARTIFACTS:
                break
            if artifact.run_id != result.run_id or artifact.uri not in permitted_uris:
                continue
            if not _is_allowlisted_text_artifact(artifact):
                continue
            try:
                raw = reader.read_verified_bytes(artifact, REPORT_RAW_ARTIFACT_BYTES)
                decoded = raw.decode("utf-8", errors="replace")
            except (OSError, UnicodeError, ValueError):
                continue
            text = str(redact_value(decoded))
            capped = text.encode("utf-8")[:REPORT_REDACTED_ARTIFACT_BYTES].decode(
                "utf-8", errors="ignore"
            )
            if capped:
                excerpts.append(
                    RedactedTextExcerpt(
                        kind=artifact.kind,
                        uri=str(redact_value(artifact.uri)),
                        checksum=artifact.checksum,
                        content_type=artifact.content_type or "",
                        text=capped,
                    )
                )
    bundle_without_hash = {
        **base.model_dump(mode="json", exclude={"input_hash"}),
        "excerpts": [excerpt.model_dump(mode="json") for excerpt in excerpts],
    }
    input_hash = sha256(
        dumps(bundle_without_hash, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return RunReportEvidenceBundle.model_validate({"input_hash": input_hash, **bundle_without_hash})


def _is_allowlisted_text_artifact(artifact: ArtifactRecord) -> bool:
    content_type = (artifact.content_type or "").lower()
    return artifact.kind in REPORT_TEXTUAL_KINDS and (
        content_type == "text/plain"
        or content_type == "application/json"
        or content_type.endswith("+json")
    )


def _artifact_references(
    artifacts: list[Artifact], policy: EvidencePolicy
) -> list[EvidenceReference]:
    allowed = []
    for artifact in artifacts:
        if policy.include_metadata or (
            policy.include_screenshots and artifact.kind == "screenshot"
        ):
            allowed.append(
                EvidenceReference(
                    kind=artifact.kind,
                    uri=str(redact_value(artifact.uri)),
                    content_type=artifact.content_type,
                )
            )
    return allowed
