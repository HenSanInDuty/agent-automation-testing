"""Authoritative v4 transport and generated worker schema parity; no services/providers."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from auto_at.contracts import vision_worker
from pydantic import ValidationError

ROOT = Path(__file__).parents[1]


def test_generated_worker_contracts_are_current():
    spec = importlib.util.spec_from_file_location(
        "export_vision_worker", ROOT / "packages/contracts/export_vision_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert (ROOT / "workers/playwright/src/vision-contract.generated.ts").read_text(
        encoding="utf-8"
    ) == module.render()


def test_worker_transport_shared_fixtures():
    fixtures = ROOT / "packages/contracts/fixtures/vision-worker-v4"
    for path in fixtures.glob("*.json"):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        model = getattr(vision_worker, fixture["contract"])
        if fixture["accepted"]:
            model.model_validate(fixture["payload"])
        else:
            with pytest.raises(ValidationError):
                model.model_validate(fixture["payload"])


@pytest.mark.parametrize(
    "action",
    [
        {"kind": "stop"},
        {"kind": "click", "x": 0.5},
        {"kind": "type", "x": 0.5, "y": 0.5},
        {"kind": "wait", "duration_ms": 10_001},
        {"kind": "navigate", "text": "unexpected"},
        {"kind": "scroll", "delta_y": 2001},
    ],
)
def test_action_fields_are_exact_and_bounded(action):
    with pytest.raises(ValidationError):
        vision_worker.VisualWorkerAction.model_validate(action)


def test_target_prepare_requires_state_proposal_and_paired_checkpoint():
    payload = dict(
        tenant_id="fixture",
        project_id=UUID(int=1),
        session_id=UUID(int=2),
        fencing_token=1,
        operation_id=UUID(int=3),
        purpose="explore",
        expected_state_fingerprint="a" * 64,
        action={"kind": "click", "x": 0.5, "y": 0.5},
    )
    with pytest.raises(ValidationError, match="state and proposal"):
        vision_worker.VisualWorkerPrepare(**payload)
    payload.update(state_id=UUID(int=4), proposal_id=UUID(int=5), checkpoint_id=UUID(int=6))
    with pytest.raises(ValidationError, match="checkpoint requires state"):
        vision_worker.VisualWorkerPrepare(**payload)


def test_open_does_not_change_execution_contract_or_accept_browser_storage():
    payload = dict(
        tenant_id="fixture",
        project_id=UUID(int=1),
        session_id=UUID(int=2),
        fencing_token=1,
        target_url="http://127.0.0.1:1234",
        allowed_origins=["http://127.0.0.1:1234"],
        deadline=datetime.now(UTC),
        max_session_seconds=60,
        max_states=2,
        max_hops=1,
        max_screenshot_bytes=1024,
    )
    assert vision_worker.VisualWorkerOpen(**payload).contract_version == "v4"
    with pytest.raises(ValidationError):
        vision_worker.VisualWorkerOpen(**payload, storage_state={"cookies": []})
