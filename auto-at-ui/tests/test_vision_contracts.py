from datetime import UTC, datetime
from uuid import uuid4

import pytest
from auto_at.contracts.vision import (
    ClickAction,
    VisualEvidenceMetadata,
    VisualExplorationRequest,
    VisualExplorationResult,
    VisualExplorationState,
    VisualReplayFrame,
    VisualTrajectoryActionSummary,
    VisualTrajectoryEdge,
    VisualTrajectoryEdgeStatus,
)
from pydantic import ValidationError


def test_visual_contract_is_separate_from_execution_and_bounds_actions() -> None:
    request = VisualExplorationRequest(
        tenant_id="tenant-a", project_id=uuid4(), correlation_id=uuid4(),
        target_url="https://example.test/home", task_intent="Find the sign in button",
        allowed_origins=["https://example.test"], max_steps=2,
        max_screenshot_bytes=1024, max_session_seconds=60,
    )
    result = VisualExplorationResult(
        session_id=request.id, correlation_id=request.correlation_id,
        state=VisualExplorationState.COMPLETED,
        actions=[ClickAction(x=0.5, y=0.5, confidence=0.8, expected_outcome="Dialog opens")],
        evidence=[VisualEvidenceMetadata(
            artifact_id=uuid4(), checksum="a" * 64, content_type="image/png", byte_count=100
        )],
    )

    assert request.contract_version == "v1"
    assert result.actions[0].kind == "click"
    assert "screenshot" not in result.model_dump_json()


def test_visual_contract_forbids_unknown_fields_and_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        ClickAction(x=1.1, y=0.5, confidence=0.5, expected_outcome="x", shell_command="no")


def test_replay_frame_contract_is_metadata_only_and_validated() -> None:
    frame = VisualReplayFrame(
        id=uuid4(), session_id=uuid4(), state_id=uuid4(), sequence=1,
        checksum="b" * 64, byte_count=100, content_type="image/png",
        captured_at=datetime.now(UTC),
    )

    assert "storage" not in frame.model_dump_json()
    with pytest.raises(ValidationError):
        VisualReplayFrame(
            **frame.model_dump(), storage_url="https://storage.example/frame.png"
        )
    with pytest.raises(ValidationError):
        VisualReplayFrame(**{**frame.model_dump(), "checksum": "invalid"})


def test_trajectory_edge_is_immutable_redacted_and_bounded() -> None:
    edge = VisualTrajectoryEdge(
        id=uuid4(), tenant_id="tenant-a", session_id=uuid4(), parent_state_id=uuid4(),
        proposal_id=uuid4(), attempt=1,
        action=VisualTrajectoryActionSummary(kind="click", x=0.4, y=0.6),
        confidence=0.8, status=VisualTrajectoryEdgeStatus.OBSERVED,
        child_state_id=uuid4(), observed_at=datetime.now(UTC), duration_ms=120,
        url_fingerprint="a" * 64, child_screenshot_checksum="b" * 64,
    )

    assert edge.action.kind == "click"
    assert "text" not in edge.model_dump_json()
    with pytest.raises(ValidationError):
        VisualTrajectoryEdge(**{**edge.model_dump(), "duration_ms": -1})
    with pytest.raises(ValidationError):
        VisualTrajectoryEdge(**{**edge.model_dump(), "raw_url": "https://secret.example"})
    with pytest.raises(ValidationError):
        VisualTrajectoryActionSummary(kind="type", text="secret")


@pytest.mark.parametrize("value", [
    "password: abc", "alice@example.test", "token=abc", "[REDACTED]", "123456789",
    "https://provider.test/image", "line\nfeed",
])
def test_locator_rejects_sensitive_identity_instead_of_redacting_verified_value(value):
    from auto_at.contracts.vision import VisualLocatorDescriptor

    with pytest.raises(ValidationError):
        VisualLocatorDescriptor(strategy="label", value=value)


@pytest.mark.parametrize("descriptor", [
    {"strategy": "css", "value": "button >> nth=0"},
    {"strategy": "css", "value": "[onclick=alert(1)]"},
    {"strategy": "role", "value": "Explore"},
    {"strategy": "label", "value": "Explore", "role": "button"},
    {"strategy": "test_id", "value": "explore", "exact": False},
    {"strategy": "label", "value": "Explore", "scope": [
        {"kind": "iframe", "selector": "iframe:nth-child(2)"},
    ]},
    {"strategy": "label", "value": "Explore", "scope": [
        {"kind": "cross_origin", "selector": 'iframe[id="embedded"]'},
    ]},
])
def test_locator_rejects_invalid_scope_or_executable_selector(descriptor):
    from auto_at.contracts.vision import VisualLocatorDescriptor

    with pytest.raises(ValidationError):
        VisualLocatorDescriptor.model_validate(descriptor)


def test_locator_parity_fixtures():
    import json
    from pathlib import Path

    from auto_at.contracts import (
        VisualLocatorDescriptor,
        VisualLocatorEvidence,
        VisualLocatorHandoff,
        VisualOperation,
        VisualWorkerCommand,
    )

    models = {model.__name__: model for model in (
        VisualLocatorDescriptor, VisualLocatorEvidence, VisualLocatorHandoff,
        VisualOperation, VisualWorkerCommand,
    )}
    directory = Path(__file__).parents[1] / "packages/contracts/fixtures/vision-locator-v1"
    fixtures = list(directory.glob("*.json"))
    assert len(fixtures) >= 10
    for path in fixtures:
        fixture = json.loads(path.read_text(encoding="utf-8"))
        model = models[fixture["contract"]]
        if fixture["accepted"]:
            model.model_validate(fixture["payload"])
        else:
            with pytest.raises(ValidationError):
                model.model_validate(fixture["payload"])


def test_input_reference_blocks_executable_branch_and_never_contains_typed_values():
    from auto_at.contracts.vision import VisualHandoffBranch, VisualHandoffStep

    step = VisualHandoffStep(operation_id=uuid4(), input_reference=uuid4())
    with pytest.raises(ValidationError, match="input_binding_required"):
        VisualHandoffBranch(id=uuid4(), steps=(step,), status="ready")
    branch = VisualHandoffBranch(id=uuid4(), steps=(step,), status="blocked",
                                 reason_code="input_binding_required")
    assert "text" not in branch.model_dump_json()
    with pytest.raises(ValidationError):
        VisualHandoffStep(operation_id=uuid4(), text="sensitive")
