from uuid import uuid4

import pytest
from auto_at.contracts.vision import (
    ClickAction,
    VisualEvidenceMetadata,
    VisualExplorationRequest,
    VisualExplorationResult,
    VisualExplorationState,
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
