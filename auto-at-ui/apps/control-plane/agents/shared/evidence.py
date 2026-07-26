"""Build bounded, redacted evidence bundles for advisory agent work."""

from hashlib import sha256
from json import dumps

from auto_at.contracts.agent import EvidenceBundle, EvidenceReference
from auto_at.contracts.execution import Artifact, TestExecutionResult

from agents.shared.redaction import redact_mapping, redact_value
from agents.shared.runtime import EvidencePolicy

REDACTION_POLICY_VERSION = "v1"


def build_evidence_bundle(
    result: TestExecutionResult, policy: EvidencePolicy
) -> EvidenceBundle:
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
