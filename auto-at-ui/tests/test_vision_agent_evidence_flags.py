"""ADR-040: opt-in agent evidence (A1 click context, A2 dom_path capability, A3 inventory).

Offline and database-free: contracts, domain merge, capability list and the processor's inventory
write are exercised with stubs. Every flag off must leave the old shapes byte-identical.
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from application.vision_agent_loop import (
    AgentRun,
    VisionAgentLoopProcessor,
    run_operation,
    worker_capabilities,
)
from auto_at.contracts.vision import VisualCheckpoint, VisualExecutedClick, VisualOperation
from auto_at.contracts.vision_coverage import VisualPageControl, VisualPageInventory
from auto_at.contracts.vision_worker import VisualWorkerAction, VisualWorkerOpen
from config import Settings
from domain.vision_coverage import inventory, merge_inventory
from pydantic import ValidationError
from test_vision_agent_loop import bound_for, dom_element

FRAME = uuid4()
FINGERPRINT = "c" * 64
NOW = datetime.now(UTC)
OLD_CLICK_KEYS = {"x", "y", "viewport_width", "viewport_height", "before_frame_id", "confirmed_at"}


def click(confirmed_at=NOW, **context):
    return VisualExecutedClick(x=0.5, y=0.5, viewport_width=1280, viewport_height=720,
                               before_frame_id=FRAME, confirmed_at=confirmed_at, **context)


# --------------------------------------------------------------------------------- A1 contract

def test_absent_click_context_is_never_serialized_so_stored_and_served_shapes_do_not_change():
    plain = click()
    assert set(plain.model_dump(mode="json")) == OLD_CLICK_KEYS
    assert set(json.loads(plain.model_dump_json())) == OLD_CLICK_KEYS
    assert plain.scroll_x is None and plain.scroll_y is None and plain.url_fingerprint is None


def test_click_context_round_trips_and_a_stored_old_payload_still_validates():
    full = click(scroll_x=0, scroll_y=640, url_fingerprint=FINGERPRINT)
    dumped = full.model_dump(mode="json")
    assert dumped["scroll_y"] == 640 and dumped["scroll_x"] == 0
    assert dumped["url_fingerprint"] == FINGERPRINT
    assert VisualExecutedClick.model_validate(dumped) == full
    old = {key: dumped[key] for key in OLD_CLICK_KEYS}
    assert VisualExecutedClick.model_validate(old) == click()


@pytest.mark.parametrize("bad", [{"scroll_y": -1}, {"scroll_x": 1.5},
                                 {"url_fingerprint": "not-a-fingerprint"},
                                 {"scroll_y": 10_000_001}, {"unknown": 1}])
def test_click_context_rejects_invalid_values_and_unknown_keys(bad):
    with pytest.raises(ValidationError):
        click(**bad)


def test_an_operation_dump_keeps_the_old_click_shape_without_context():
    """`/trace` and the trace revision hash use this dump: it must not gain null keys."""
    def operation(executed):
        started = NOW - timedelta(seconds=2)
        return VisualOperation(
            id=uuid4(), tenant_id="t", project_id=uuid4(), session_id=uuid4(), sequence=2,
            purpose="explore", action_kind="click", started_at=started, ended_at=NOW,
            status="completed", outcome_code="observed", actual_before_frame_id=FRAME,
            actual_after_frame_id=uuid4(), executed_click=executed)

    plain = operation(click(confirmed_at=NOW - timedelta(seconds=1))).model_dump(mode="json")
    assert set(plain["executed_click"]) == OLD_CLICK_KEYS
    rich = operation(click(confirmed_at=NOW - timedelta(seconds=1), scroll_x=0, scroll_y=3,
                           url_fingerprint=FINGERPRINT))
    assert rich.model_dump(mode="json")["executed_click"]["scroll_y"] == 3
    assert VisualOperation.model_validate(rich.model_dump(mode="json")) == rich


# --------------------------------------------------------------------------------- flags / A2

def test_flags_default_to_off():
    settings = Settings(_env_file=None)
    assert (settings.vision_agent_click_context_enabled, settings.vision_agent_dom_path_enabled,
            settings.vision_agent_inventory_enabled) == (False, False, False)


@pytest.mark.parametrize("step", [None, 30])
def test_capabilities_are_unchanged_while_every_flag_is_off(step):
    expected = ("dom-observation-v1",) + (("step-timeout-v1",) if step else ())
    assert worker_capabilities(Settings(_env_file=None), step) == expected


def test_each_flag_adds_only_its_own_capability():
    for flags, extra in (({"vision_agent_click_context_enabled": True}, ("click-context-v1",)),
                         ({"vision_agent_dom_path_enabled": True}, ("agent-dom-path-v1",)),
                         ({"vision_agent_inventory_enabled": True}, ())):
        got = worker_capabilities(Settings(_env_file=None, **flags), None)
        assert got == ("dom-observation-v1", *extra)
    both = worker_capabilities(Settings(
        _env_file=None, vision_agent_click_context_enabled=True,
        vision_agent_dom_path_enabled=True, vision_agent_inventory_enabled=True), 5)
    assert both == ("dom-observation-v1", "step-timeout-v1", "click-context-v1",
                    "agent-dom-path-v1")


def test_the_worker_open_contract_accepts_the_new_capabilities_and_nothing_else():
    ids = dict(tenant_id="t", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
               target_url="https://app.test/", allowed_origins=(), deadline=NOW + timedelta(60),
               max_session_seconds=60, max_states=5, max_hops=1, max_screenshot_bytes=1024)
    old = VisualWorkerOpen(**ids, required_capabilities=("dom-observation-v1", "step-timeout-v1"))
    assert old.required_capabilities == ("dom-observation-v1", "step-timeout-v1")
    new = VisualWorkerOpen(**ids, required_capabilities=(
        "dom-observation-v1", "step-timeout-v1", "click-context-v1", "agent-dom-path-v1"))
    assert "agent-dom-path-v1" in new.required_capabilities
    with pytest.raises(ValidationError):
        VisualWorkerOpen(**ids, required_capabilities=("made-up-v1",))


# --------------------------------------------------------------------------------- A3 inventory

def checkpoint(state_id=None, url=FINGERPRINT):
    return VisualCheckpoint(id=uuid4(), state_id=state_id or uuid4(), url_fingerprint=url,
                            semantic_fingerprint="d" * 64, scroll_x=0, scroll_y=0,
                            page_url="https://app.test/")


def observation(names, **kwargs):
    return bound_for([dom_element(index, name) for index, name in enumerate(names, 1)], **kwargs)


def test_merge_keeps_the_union_by_key_and_the_newest_flags():
    point = checkpoint()
    first = inventory(point, observation(["A", "B"], skipped=2), {}, "all")
    second = inventory(point, observation(["B", "C"], skipped=1).model_copy(), {}, "all")
    merged = merge_inventory(first, second.model_copy(update={"scrollable": True}))
    assert sorted(control.name for control in merged.controls) == ["A", "B", "C"]
    assert merged.skipped_count == 2 and merged.scrollable is True and merged.truncated is False
    assert merge_inventory(None, first) is first


def test_merge_is_capped_at_the_contract_limit_and_marks_truncation():
    point = checkpoint()
    first = inventory(point, observation([f"a{i}" for i in range(100)]), {}, "all")
    second = inventory(point, observation([f"b{i}" for i in range(20)]), {}, "all")
    merged = merge_inventory(first, second)
    assert len(merged.controls) == 100 and merged.truncated is True
    VisualPageInventory.model_validate(merged.model_dump())


class Uow:
    def __init__(self, fail_first=False):
        self.saved, self.fail_first = [], fail_first

    def page_inventory(self, lease, page):
        if self.fail_first:
            self.fail_first = False
            raise ValueError("inventory checkpoint mismatch")
        self.saved.append((lease, page))


def processor(uow, **flags):
    return VisionAgentLoopProcessor(uow, None, Settings(_env_file=None, **flags))


def stub_run(point):
    return SimpleNamespace(checkpoint=point, inventories={}, operations=SimpleNamespace(lease="L"))


def test_inventory_is_not_written_while_its_flag_is_off():
    uow = Uow()
    run = stub_run(checkpoint())
    processor(uow)._save_inventory(run, observation(["A"]))
    assert uow.saved == [] and run.inventories == {}


def test_inventory_is_written_per_state_and_accumulates_across_observations():
    uow, point = Uow(), checkpoint()
    run = stub_run(point)
    worker = processor(uow, vision_agent_inventory_enabled=True)
    worker._save_inventory(run, observation(["A", "B"]))
    worker._save_inventory(run, observation(["B", "C"]))  # same state, scrolled
    assert [page.state_id for _, page in uow.saved] == [point.state_id] * 2
    assert all(lease == "L" and page.checkpoint_id == point.id for lease, page in uow.saved)
    assert sorted(control.name for control in uow.saved[-1][1].controls) == ["A", "B", "C"]
    other = checkpoint()
    run.checkpoint = other
    worker._save_inventory(run, observation(["Z"]))
    assert uow.saved[-1][1].state_id == other.state_id
    assert [control.name for control in uow.saved[-1][1].controls] == ["Z"]
    assert all(isinstance(control, VisualPageControl) for control in uow.saved[-1][1].controls)


def test_an_inventory_failure_never_stops_the_agent_and_is_retried_with_the_next_observation():
    uow = Uow(fail_first=True)
    run = stub_run(checkpoint())
    worker = processor(uow, vision_agent_inventory_enabled=True)
    worker._save_inventory(run, observation(["A"]))  # swallowed: evidence only
    assert uow.saved == [] and run.inventories == {}
    worker._save_inventory(run, observation(["B"]))
    assert [control.name for control in uow.saved[0][1].controls] == ["B"]


def test_no_inventory_without_a_checkpoint_of_the_current_page():
    uow = Uow()
    processor(uow, vision_agent_inventory_enabled=True)._save_inventory(
        stub_run(None), observation(["A"]))
    assert uow.saved == []


def test_run_operation_remembers_the_checkpoint_of_the_current_page():
    """The inventory is attached to the state that the newest completed checkpoint created."""
    point = checkpoint()
    operation = SimpleNamespace(
        id=uuid4(), outcome_code="observed", status="completed", url_change="changed",
        actual_after_frame_id=uuid4())
    result = SimpleNamespace(operation=operation, state_fingerprint=FINGERPRINT, checkpoint=point)

    class Operations:
        identity = SimpleNamespace(model_dump=lambda: {
            "tenant_id": "t", "project_id": uuid4(), "session_id": uuid4(), "fencing_token": 1})
        step_timeout_seconds, max_frame_bytes = None, 1_000_000

        async def execute(self, op, command):
            return result

    class Origins:
        async def capture(self):
            return None

    run = AgentRun(
        Operations(), SimpleNamespace(tenant_id="t", project_id=uuid4(), session_id=uuid4()),
        Origins(),
        lambda: (SimpleNamespace(max_session_seconds=60, max_screenshot_bytes=1000), None),
        None, FINGERPRINT, uuid4())
    action = VisualWorkerAction(kind="navigate")
    asyncio.run(run_operation(run, action, "setup", checkpoint=True))
    assert run.checkpoint is point and run.state_id == point.state_id
    assert run.page_url == "https://app.test/"
