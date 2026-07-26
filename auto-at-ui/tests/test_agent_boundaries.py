from uuid import uuid4

from agents.shared.evidence import REDACTION_POLICY_VERSION, build_evidence_bundle
from agents.shared.redaction import redact_mapping, redact_value
from agents.shared.runtime import EvidencePolicy
from agents.triage.service import propose_failure_triage, validate_triage_output
from auto_at.contracts.agent import (
    AgentProposal,
    ApprovalDecision,
    HealingProposal,
    ProposalKind,
    ProposalProvenance,
)
from auto_at.contracts.execution import Artifact, RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from domain.proposals import may_apply_proposal


def test_proposal_requires_matching_explicit_approval() -> None:
    proposal = AgentProposal(
        kind=ProposalKind.HEALING,
        correlation_id=uuid4(),
        summary="Update a locator after human review.",
    )

    assert not may_apply_proposal(proposal, None)
    assert not may_apply_proposal(
        proposal,
        ApprovalDecision(proposal_id=proposal.id, approved=False, decided_by="reviewer"),
    )
    assert may_apply_proposal(
        proposal,
        ApprovalDecision(proposal_id=proposal.id, approved=True, decided_by="reviewer"),
    )


def test_redaction_hides_common_secret_fields() -> None:
    assert redact_mapping({"token": "secret-value", "selector": "#submit"}) == {
        "token": "[REDACTED]",
        "selector": "#submit",
    }


def test_redaction_recursively_hides_secrets_in_evidence_and_urls() -> None:
    evidence = {
        "request": {
            "headers": {"Authorization": "Bearer secret-value"},
            "body": {"profile": {"password": "not-for-prompts"}},
        },
        "events": [
            {"url": "https://example.test/login?email=person%40example.test&token=secret"},
            "POST /login?session=private-value",
        ],
    }
    assert redact_value(evidence) == {
        "request": {
            "headers": {"Authorization": "[REDACTED]"},
            "body": {"profile": {"password": "[REDACTED]"}},
        },
        "events": [
            {"url": "https://example.test/login?email=%5BREDACTED%5D&token=%5BREDACTED%5D"},
            "POST /login?session=%5BREDACTED%5D",
        ],
    }


def test_evidence_bundle_is_redacted_bounded_and_hashes_its_prompt_input() -> None:
    run_id = uuid4()
    correlation_id = uuid4()
    result = ExecutionResult(
        run_id=run_id,
        correlation_id=correlation_id,
        status=RunStatus.FAILED,
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
        summary="Login failed: token=do-not-send",
        runner_metadata={"headers": {"authorization": "Bearer private"}},
        artifacts=[
            Artifact(kind="trace", uri="s3://private/trace.zip?signature=private"),
            Artifact(kind="screenshot", uri="s3://private/failure.png?signature=private"),
        ],
    )

    bundle = build_evidence_bundle(
        result,
        EvidencePolicy(
            include_metadata=False,
            include_redacted_text=True,
            include_screenshots=True,
        ),
    )

    assert bundle.run_id == run_id
    assert bundle.redaction_policy_version == REDACTION_POLICY_VERSION
    assert bundle.summary == "Login failed: token=[REDACTED]"
    assert bundle.runner_metadata == {}
    assert [artifact.kind for artifact in bundle.artifacts] == ["screenshot"]
    assert bundle.artifacts[0].uri.endswith("?signature=%5BREDACTED%5D")
    assert len(bundle.input_hash) == 64


def test_healing_proposal_requires_a_versioned_provenance_record() -> None:
    proposal = HealingProposal(
        correlation_id=uuid4(),
        summary="Use the accessible save-button locator.",
        confidence=0.8,
        evidence_references=["artifact:screenshot"],
        proposed_change={"locator": "get_by_role('button', name='Save')"},
        provenance=ProposalProvenance(
            provider="openrouter",
            model="openai/gpt-5-mini",
            prompt_version="healing-v1",
            redaction_policy_version=REDACTION_POLICY_VERSION,
            evidence_input_hash="a" * 64,
        ),
    )

    assert proposal.confidence == 0.8
    assert proposal.provenance.prompt_version == "healing-v1"


def test_triage_is_schema_validated_and_remains_an_advisory_proposal() -> None:
    result = ExecutionResult(
        run_id=uuid4(),
        correlation_id=uuid4(),
        status=RunStatus.ERRORED,
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
        summary="Browser process exited.",
    )

    triage = validate_triage_output(
        '{"category":"environment","confidence":0.9,"rationale":"Browser exited.",'
        '"evidence_references":[],"stop_conditions":["Do not retry after budget exhaustion"]}'
    )
    proposal = propose_failure_triage(result)

    assert triage.category == "environment"
    assert proposal.kind == ProposalKind.TRIAGE
    assert proposal.proposed_change is None
