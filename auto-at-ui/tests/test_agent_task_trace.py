"""ADR-047 phase B1: the linear task trace of a completed agent-loop session.

Pure cases build the rows by hand (shape taken from the phase 07 spike over real sessions); the
scope cases run the real agent loop against the PostgreSQL fixture and read it back.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from application.agent_task_trace import AgentTaskTraceNotFound, read_agent_task_trace
from auto_at.contracts.agent_task_trace import (
    VERIFIED_TEXT_ITEMS_MAX,
    AgentTaskAssessmentCopy,
    AgentTaskTrace,
)
from auto_at.contracts.codex_bridge import AgentTaskCheck, AgentTaskResult
from auto_at.contracts.vision import (
    VisualLocatorDescriptor,
    VisualLocatorEvidence,
    VisualOperation,
)
from domain.agent_task_trace import AgentTaskTraceRefused, build_agent_task_trace
from domain.entities import VisualOperationFrameRecord
from domain.verified_text import VERIFIED_ITEMS_MAX, ObservedText, verify_quotes
from domain.vision import VisualSessionScope
from domain.vision_task_assessment import action_facts, from_stop, from_task_result
from infrastructure.persistence.repositories import (
    SqlAlchemyVisionRepository,
    SqlAlchemyVisualTraceRepository,
)
from pydantic import ValidationError
from test_vision_agent_loop import DONE, Outcome, click, ended, run_agent, step, typed, wait
from vision_trace_fixtures import evolve, frame

pytest_plugins = ["vision_trace_fixtures"]

TYPED_NAME = "SENTINEL-TYPED-NAME-7f3a"
TYPED_SECRET = "SENTINEL-TYPED-PASS-91c2"
DOM_PATH = "html > body:nth-of-type(1) > button:nth-of-type(1)"
FACTS = action_facts([{"result": {"status": "completed"}}])


def stored_assessment(status="achieved"):
    result = AgentTaskResult(
        status=status,
        summary="Signed in and read the greeting.",
        checks=(AgentTaskCheck(expectation="Greeting shown", status="met", evidence="'Hi demo'"),),
    )
    return from_task_result(result, FACTS)


@dataclass
class Skipped:
    """An action the batch did not run: `skipped_reason`, no `result`, no operation id."""

    kind: str = "wait"
    reason: str = "batch_stopped"


@dataclass
class NoResult:
    """The shape the spike saw for a leftover action: neither `result` nor a reason."""

    kind: str = "click"


class Rows:
    """Rows of one agent-loop session, as the repository would return them."""

    def __init__(self):
        self.scope = VisualSessionScope("tenant-a", uuid4(), uuid4())
        self.operations, self.locators, self.frames, self.steps = [], [], [], []
        self._text = {}

    # ---- operations
    def _frame(self, item, frame_id, role, deleted=False):
        base = frame(item, role)
        changes = {"id": frame_id} | ({"deleted_at": datetime.now(UTC)} if deleted else {})
        return VisualOperationFrameRecord(evolve(base.metadata, **changes), base.storage_key)

    def op(self, kind, *, purpose="explore", status="completed", name="Control", text=None,
           strategy="role", locator="verified", after="retained", **overrides):
        sequence = len(self.operations) + 1
        before_id, after_id = uuid4(), uuid4()
        targeted = kind in {"click", "type"} and purpose == "explore"
        locator_id = uuid4() if targeted and locator != "absent" else None
        fields = dict(
            id=uuid4(), tenant_id=self.scope.tenant_id, project_id=self.scope.project_id,
            session_id=self.scope.session_id, sequence=sequence, purpose=purpose,
            action_kind=kind, locator_id=locator_id,
            started_at=datetime.now(UTC) - timedelta(seconds=2), status=status,
            actual_before_frame_id=before_id, url_change="unchanged", visual_change="changed",
        )
        if status in {"completed", "failed", "unknown", "rejected"}:
            fields |= dict(ended_at=datetime.now(UTC), outcome_code=(
                "observed" if status == "completed" else f"{status}_code"))
        if status == "completed":
            fields["actual_after_frame_id"] = after_id
        elif status == "rejected":
            fields |= dict(actual_before_frame_id=None, before_unavailable_reason="not_executed",
                           after_unavailable_reason="not_executed")
        elif status in {"failed", "unknown"}:
            fields["after_unavailable_reason"] = "capture_failed"
        item = VisualOperation.model_validate(fields | overrides)
        self.operations.append(item)
        if item.actual_before_frame_id:
            self.frames.append(self._frame(item, item.actual_before_frame_id, "before"))
        if item.actual_after_frame_id and after != "absent":
            self.frames.append(self._frame(
                item, item.actual_after_frame_id, "after", deleted=after == "deleted"))
        if locator_id and locator != "unlisted":
            self.locators.append(self._locator(item, kind, name, strategy, locator))
        self._text[item.id] = text
        return item

    def _locator(self, item, kind, name, strategy, status):
        descriptor = (
            VisualLocatorDescriptor(schema_version="v2", strategy="dom_path", value=DOM_PATH)
            if strategy == "dom_path" else VisualLocatorDescriptor(
                strategy="role", role="textbox" if kind == "type" else "button", value=name)
        )
        verified = status == "verified"
        return VisualLocatorEvidence(
            id=item.locator_id, tenant_id=item.tenant_id, project_id=item.project_id,
            session_id=item.session_id, operation_id=item.id, state_id=uuid4(),
            proposal_id=uuid4(), originating_frame_id=item.actual_before_frame_id,
            descriptor=descriptor if verified else None,
            bounding_box={"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1},
            matched_count=1 if verified else 2, target_match=verified, actionable=verified,
            model_confidence=0.5, verified_at=datetime.now(UTC) if verified else None,
            status=status, reason_code=None if verified else "ambiguous_match",
        )

    # ---- step log
    def step(self, index, *entries, stop_reason=None):
        actions, ids = [], []
        for position, entry in enumerate(entries):
            if isinstance(entry, Skipped):
                actions.append({"index": position, "kind": entry.kind, "ref": None,
                                "skipped_reason": entry.reason, "stop_cause": "state_changed"})
            elif isinstance(entry, NoResult):
                actions.append({"index": position, "kind": entry.kind, "ref": "1:1"})
            else:
                actions.append(self._entry(position, entry))
                ids.append(str(entry.id))
        item = SimpleNamespace(step_index=index, operation_ids=ids, actions=actions,
                               stop_reason=stop_reason)
        self.steps.append(item)
        return item

    def _entry(self, position, item):
        entry = {"index": position, "kind": item.action_kind, "ref": f"1:{position + 1}",
                 "result": {"operation_id": str(item.id), "status": item.status,
                            "outcome_code": item.outcome_code, "url_change": item.url_change}}
        if item.action_kind == "type":
            entry["text_chars"] = len(self._text[item.id] or "abc")
        if item.action_kind == "scroll":
            entry["delta_y"] = 400
        if item.action_kind == "wait":
            entry["duration_ms"] = 500
        return entry

    # ---- build
    def session(self, **overrides):
        return SimpleNamespace(**(dict(
            id=self.scope.session_id, tenant_id=self.scope.tenant_id,
            project_id=self.scope.project_id, target_url="https://app.test/",
            intent_hash="b" * 64, state="completed", exploration_engine="agent_loop",
            task_assessment=stored_assessment(),
        ) | overrides))

    def build(self, *, session=None, steps=None, operations=None, locators=None, frames=None):
        return build_agent_task_trace(
            session or self.session(),
            self.steps if steps is None else steps,
            self.operations if operations is None else operations,
            self.locators if locators is None else locators,
            self.frames if frames is None else frames,
        )


def login_rows():
    """Setup navigate, then step 1 = type + type + click, step 2 = one click (the spike's login)."""
    rows = Rows()
    rows.op("navigate", purpose="setup")
    user = rows.op("type", name="Tên đăng nhập", text=TYPED_NAME)
    password = rows.op("type", name="Mật khẩu", text=TYPED_SECRET)
    submit = rows.op("click", name="Đăng nhập")
    after = rows.op("click", name="Tiếp tục")
    rows.step(1, user, password, submit)
    rows.step(2, after)
    return rows, (user, password, submit, after)


def refused(rows, **build):
    with pytest.raises(AgentTaskTraceRefused) as caught:
        rows.build(**build)
    return caught.value


# --------------------------------------------------------------------------- contract

def test_trace_is_closed_versioned_and_its_hash_verifies():
    rows, _ = login_rows()
    trace = rows.build()
    assert trace.schema_version == "v1" and trace.trace_hash == trace.compute_hash()
    data = trace.model_dump(mode="json")
    assert AgentTaskTrace.model_validate(data) == trace
    with pytest.raises(ValidationError):
        AgentTaskTrace.model_validate(data | {"extra": 1})
    with pytest.raises(ValidationError):
        AgentTaskTrace.model_validate(data | {"schema_version": "v2"})
    with pytest.raises(ValidationError):
        AgentTaskTrace.model_validate(data | {"steps": [data["steps"][0] | {"extra": 1}]})
    with pytest.raises(ValidationError, match="trace_hash mismatch"):
        AgentTaskTrace.model_validate(data | {"trace_hash": "0" * 64})
    tampered = json.loads(json.dumps(data))
    tampered["steps"][0]["locator"]["value"] = "Other"
    with pytest.raises(ValidationError, match="trace_hash mismatch"):
        AgentTaskTrace.model_validate(tampered)


def test_the_contract_itself_refuses_a_chain_the_builder_would_never_produce():
    rows, _ = login_rows()
    trace = rows.build()
    base = {name: getattr(trace, name) for name in (
        "tenant_id", "project_id", "session_id", "target_url", "intent_hash", "task_assessment")}
    typed_step, clicked, later = trace.steps[0], trace.steps[2], trace.steps[3]
    dom_path = VisualLocatorDescriptor(schema_version="v2", strategy="dom_path", value=DOM_PATH)
    assert AgentTaskTrace.seal(**base, steps=trace.steps) == trace   # the control case is valid
    broken = {
        "empty": (),
        "out of step order": (later, typed_step),
        "duplicate operation": (clicked, clicked),
        "click without its locator": (clicked.model_copy(update={"locator": None,
                                                                 "locator_id": None}),),
        "type without its length": (typed_step.model_copy(update={"text_chars": None}),),
        "parameter of another kind": (clicked.model_copy(update={"duration_ms": 500}),),
        "ephemeral locator": (clicked.model_copy(update={"locator": dom_path}),),
    }
    for label, steps in broken.items():
        with pytest.raises(ValidationError):
            AgentTaskTrace.seal(**base, steps=steps)
        assert label


# --------------------------------------------------------------------------- order

def test_steps_follow_step_index_then_operation_ids_not_the_order_rows_arrive_in():
    rows, (user, password, submit, after) = login_rows()
    trace = rows.build()
    assert [s.operation_id for s in trace.steps] == [user.id, password.id, submit.id, after.id]
    assert [(s.step_index, s.kind) for s in trace.steps] == [
        (1, "type"), (1, "type"), (1, "click"), (2, "click")]
    # visual_operations.sequence agrees with the step-log order (spike mục 6: 106/106 sessions).
    by_sequence = [o.id for o in sorted(rows.operations, key=lambda o: o.sequence)
                   if o.purpose == "explore"]
    assert by_sequence == [s.operation_id for s in trace.steps]
    shuffled = rows.build(steps=rows.steps[::-1], operations=rows.operations[::-1],
                          locators=rows.locators[::-1], frames=rows.frames[::-1])
    assert shuffled == trace


def test_many_actions_per_step_and_many_steps_keep_their_place():
    rows = Rows()
    ops = [rows.op("click", name=f"B{i}") for i in range(6)]
    scroll = rows.op("scroll")
    rows.step(3, ops[3], ops[4])
    rows.step(1, ops[0])
    rows.step(2, ops[1], scroll, ops[2])
    rows.step(4, ops[5])
    trace = rows.build()
    assert [s.step_index for s in trace.steps] == [1, 2, 2, 2, 3, 3, 4]
    assert [s.operation_id for s in trace.steps] == [
        ops[0].id, ops[1].id, scroll.id, ops[2].id, ops[3].id, ops[4].id, ops[5].id]
    assert trace.steps[2].delta_y == 400 and trace.steps[2].locator is None


def test_a_step_with_a_skipped_action_keeps_only_what_ran_in_order():
    rows = Rows()
    first, last = rows.op("click", name="A"), rows.op("click", name="B")
    rows.step(1, first, Skipped("wait"), NoResult("click"), Skipped("click", "stale_ref"))
    rows.step(2, last)
    assert [s.operation_id for s in rows.build().steps] == [first.id, last.id]


# --------------------------------------------------------------------------- spike cases (a)-(d)

def test_case_a_controller_setup_operations_are_not_steps_and_never_refuse():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    rows.op("wait", purpose="setup")
    rows.op("wait", purpose="setup", status="failed")           # outside every step
    rows.op("navigate", purpose="setup", status="rejected")
    clicked = rows.op("click", name="Go")
    rows.op("wait", purpose="setup")                            # a trailing refresh
    rows.step(1, clicked)
    trace = rows.build()
    assert [s.operation_id for s in trace.steps] == [clicked.id]
    # Even a setup id that a step log listed is skipped, not turned into a step.
    stray = rows.op("wait", purpose="setup")
    rows.step(2, stray)
    assert [s.operation_id for s in rows.build().steps] == [clicked.id]
    assert trace.target_url == "https://app.test/"


def test_case_b_actions_with_no_operation_id_are_skipped_not_errors():
    rows = Rows()
    ran = rows.op("click", name="Open")
    rows.step(1, ran, Skipped("wait", "batch_stopped"), NoResult("click"),
              stop_reason="state_changed")
    assert ran.id in {s.operation_id for s in rows.build().steps}
    assert len(rows.build().steps) == 1
    # More operation ids than actions that ran is an inconsistent log, not a skip.
    broken = Rows()
    one, two = broken.op("click", name="A"), broken.op("click", name="B")
    item = broken.step(1, one)
    item.operation_ids.append(str(two.id))
    error = refused(broken)
    assert error.code == "evidence_unavailable" and error.step_index == 1


def test_case_c_completed_wait_is_kept_with_its_duration_and_no_locator():
    rows = Rows()
    first, pause, second = rows.op("click", name="A"), rows.op("wait"), rows.op("click", name="B")
    rows.step(1, first, pause, second)
    kept = rows.build().steps
    assert [s.kind for s in kept] == ["click", "wait", "click"]
    assert kept[1].duration_ms == 500 and kept[1].locator is None and kept[1].text_chars is None
    # The decision is written into the contract, so the renderer can rely on it.
    import auto_at.contracts.agent_task_trace as contract
    assert "`wait` is KEPT" in contract.__doc__
    failed = Rows()
    broken = failed.op("wait", status="failed")
    failed.step(1, broken)
    assert refused(failed).code == "operation_failed"


def test_case_d_a_worker_result_mismatch_step_refuses_the_whole_session():
    rows = Rows()
    ok = rows.op("click", name="A")
    rows.op("click", name="B")              # executed, but no step recorded it (spike: 685f76a7)
    rows.step(1, ok)
    rows.step(2, Skipped("click", "worker_result_mismatch"), stop_reason="worker_result_mismatch")
    error = refused(rows)
    assert (error.code, error.step_index) == ("evidence_unavailable", 2)
    # Same hole without the stop marker: an explore operation that belongs to no step.
    unmarked = Rows()
    unmarked.op("click", name="A")
    orphan = unmarked.op("click", name="B")
    unmarked.step(1, unmarked.operations[0])
    error = refused(unmarked)
    assert (error.code, error.operation_id) == ("evidence_unavailable", orphan.id)


@pytest.mark.parametrize(("status", "code"), [
    ("failed", "operation_failed"),
    ("rejected", "operation_failed"),
    ("unknown", "action_outcome_unknown"),
    ("executing", "action_outcome_unknown"),
    ("prepared", "action_outcome_unknown"),
])
def test_case_d_an_operation_that_did_not_complete_refuses_with_its_own_code(status, code):
    rows = Rows()
    good = rows.op("click", name="A")
    bad = rows.op("click", name="B", status=status, locator="absent")
    rows.step(1, good, bad)
    error = refused(rows)
    assert (error.code, error.step_index, error.operation_id) == (code, 1, bad.id)


# --------------------------------------------------------------------------- refusals

def one_step(*, kind="click", **options):
    rows = Rows()
    item = rows.op(kind, **options)
    rows.step(1, item)
    return rows, item


@pytest.mark.parametrize("overrides", [
    {"state": "unavailable"}, {"state": "running"}, {"state": "cancelled"},
    {"exploration_engine": "planner"},
    {"task_assessment": None},
    {"task_assessment": {**stored_assessment(), "schema_version": "v2"}},
    {"task_assessment": {**stored_assessment(), "advisory": False}},
    {"task_assessment": {**stored_assessment(), "surprise": 1}},
])
def test_a_session_that_is_not_a_completed_assessed_agent_loop_is_refused(overrides):
    rows, _ = one_step()
    error = refused(rows, session=rows.session(**overrides))
    assert error.code == "assessment_unavailable" and error.operation_id is None


@pytest.mark.parametrize(("options", "code"), [
    ({"locator": "absent"}, "locator_unavailable"),
    ({"locator": "unlisted"}, "locator_unavailable"),
    ({"locator": "ambiguous"}, "locator_unavailable"),
    ({"locator": "not_found"}, "locator_unavailable"),
    ({"strategy": "dom_path"}, "ephemeral_locator"),
    ({"after": "absent"}, "evidence_unavailable"),
    ({"after": "deleted"}, "evidence_unavailable"),
])
def test_click_evidence_that_cannot_back_a_test_is_refused_with_the_step_named(options, code):
    rows, item = one_step(**options)
    error = refused(rows)
    assert (error.code, error.step_index, error.operation_id) == (code, 1, item.id)


def test_a_missing_frame_row_or_operation_or_pairing_is_evidence_unavailable():
    rows, item = one_step()
    assert refused(rows, frames=[]).code == "evidence_unavailable"
    assert refused(rows, operations=[]).code == "evidence_unavailable"
    rows.steps[0].actions[0]["kind"] = "wait"            # step log and ledger disagree
    assert refused(rows).code == "evidence_unavailable"
    rows.steps[0].actions[0]["kind"] = "click"
    rows.steps[0].actions[0]["result"]["operation_id"] = str(uuid4())
    assert refused(rows).code == "evidence_unavailable"
    assert item.id  # the operation itself was fine
    # A typed step that lost `text_chars` cannot be reproduced.
    typed_rows, _ = one_step(kind="type")
    del typed_rows.steps[0].actions[0]["text_chars"]
    assert refused(typed_rows).code == "evidence_unavailable"


def test_a_session_with_nothing_to_replay_is_refused():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    rows.steps.append(SimpleNamespace(step_index=1, operation_ids=[], actions=[],
                                      stop_reason="agent_done"))
    assert refused(rows).code == "evidence_unavailable"


@pytest.mark.parametrize("kind", ["back", "close_popup"])
def test_actions_with_no_stable_playwright_equivalent_are_refused(kind):
    rows, item = one_step(kind=kind)
    error = refused(rows)
    assert (error.code, error.operation_id) == ("action_unsupported", item.id)


def test_a_failed_unsupported_action_reports_the_failure_first():
    rows, _ = one_step(kind="back", status="failed")
    assert refused(rows).code == "operation_failed"


# --------------------------------------------------------------------------- what is not in it

def test_typed_text_refs_and_coordinates_never_reach_the_trace():
    rows, (user, password, *_) = login_rows()
    for item in rows.steps[0].actions:
        # Even a step log that wrongly kept the text or a point must not leak through the builder.
        item |= {"text": TYPED_NAME, "x": 123.5, "y": 456.5, "ref": "9:9"}
    raw = rows.build().model_dump_json()
    for needle in (TYPED_NAME, TYPED_SECRET, "9:9", "123.5", "456.5"):
        assert needle not in raw
    kinds = {"bounding_box", "executed_click", "x", "y", "width", "height", "ref", "text",
             "before_frame_id", "after_frame_id"}

    def keys(node):
        if isinstance(node, dict):
            yield from node
            for value in node.values():
                yield from keys(value)
        elif isinstance(node, list):
            for value in node:
                yield from keys(value)

    assert not kinds & set(keys(json.loads(raw)))
    lengths = [s.text_chars for s in rows.build().steps if s.kind == "type"]
    assert lengths == [len(TYPED_NAME), len(TYPED_SECRET)]


# --------------------------------------------------------------------------- hash

def test_the_hash_is_stable_and_follows_content_and_order():
    rows, (user, password, submit, after) = login_rows()
    first, second = rows.build(), rows.build()
    assert first == second and first.trace_hash == second.trace_hash
    assert len(first.trace_hash) == 64

    # Same rows, two operations swapped inside one step: the order alone changes the hash.
    reordered = rows.build(steps=[
        SimpleNamespace(**(vars(rows.steps[0]) | {
            "operation_ids": [str(password.id), str(user.id), str(submit.id)],
            "actions": [rows.steps[0].actions[1], rows.steps[0].actions[0],
                        rows.steps[0].actions[2]],
        })),
        rows.steps[1],
    ])
    assert reordered.trace_hash != first.trace_hash

    renamed = [loc.model_copy(update={"descriptor": VisualLocatorDescriptor(
        strategy="role", role="textbox", value="Another")}) if loc.id == user.locator_id else loc
        for loc in rows.locators]
    assert rows.build(locators=renamed).trace_hash != first.trace_hash

    longer = rows.steps[0].actions[0] | {"text_chars": 99}
    changed = SimpleNamespace(**(vars(rows.steps[0]) | {
        "actions": [longer, *rows.steps[0].actions[1:]]}))
    assert rows.build(steps=[changed, rows.steps[1]]).trace_hash != first.trace_hash

    reworded = rows.session(task_assessment=stored_assessment("achieved") | {"summary": "Other"})
    assert rows.build(session=reworded).trace_hash != first.trace_hash
    assert rows.build(session=rows.session(intent_hash="c" * 64)).trace_hash != first.trace_hash
    # A dropped skipped action changes nothing the trace holds.
    rows.steps[1].actions.append({"index": 1, "kind": "wait", "ref": None,
                                  "skipped_reason": "batch_stopped"})
    assert rows.build().trace_hash == first.trace_hash


def test_the_assessment_is_copied_whatever_its_status_and_stays_advisory():
    rows, _ = one_step()
    for status in ("achieved", "not_achieved", "blocked", "inconclusive"):
        stored = from_stop("complete", FACTS) | {"status": status}
        trace = rows.build(session=rows.session(task_assessment=stored))
        assert trace.task_assessment.status == status and trace.task_assessment.advisory is True


def test_agent_refs_in_the_assessment_free_text_are_redacted_but_the_fields_are_kept():
    rows, _ = one_step()
    result = AgentTaskResult(
        status="achieved",
        summary="Typed in 1:7 then 12:30 and 3:17:2, clicked 1:9.",
        checks=(
            AgentTaskCheck(expectation="field 1:7 filled", status="met", evidence="ref 22:345 ok"),
            AgentTaskCheck(expectation="no refs here", status="met", evidence="'Hi demo'"),
        ),
    )
    stored = from_task_result(result, FACTS)
    trace = rows.build(session=rows.session(task_assessment=stored))
    raw = trace.model_dump_json()
    for ref in ("1:7", "12:30", "3:17", "17:2", "1:9", "22:345"):
        assert ref not in raw, ref
    assessment = trace.task_assessment
    assert assessment.summary.startswith("Typed in …") and assessment.summary.endswith("clicked ….")
    assert [c.evidence for c in assessment.checks] == ["ref … ok", "'Hi demo'"]
    assert assessment.checks[0].expectation == "field … filled"
    # the text of a clean assessment is untouched, so its hash does not move
    clean = rows.build(session=rows.session(task_assessment=stored_assessment()))
    assert clean.task_assessment.summary == "Signed in and read the greeting."


def test_redaction_never_pushes_a_field_over_its_limit_and_is_deterministic():
    rows, _ = one_step()
    result = AgentTaskResult(
        status="achieved",
        summary="1:1 " * 250,  # exactly 1000 characters
        checks=(AgentTaskCheck(expectation="e", status="met", evidence="1:2" * 100),),
    )
    stored = from_task_result(result, FACTS)
    first = rows.build(session=rows.session(task_assessment=stored))
    again = rows.build(session=rows.session(task_assessment=stored))
    assert first.trace_hash == again.trace_hash
    assert len(first.task_assessment.summary) <= 1000


def verified(*texts, kind="status", dropped=0):
    return {"items": [{"kind": kind, "text": text, "check_index": 0} for text in texts],
            "dropped": dropped, "truncated": False}


def test_verified_text_is_copied_unredacted_and_the_hash_follows_every_item():
    rows, _ = one_step()
    stored = stored_assessment() | {"verified_text": verified("Hi demo", "Meeting at 12:30")}
    trace = rows.build(session=rows.session(task_assessment=stored))
    copy = trace.task_assessment.verified_text
    assert [item.text for item in copy.items] == ["Hi demo", "Meeting at 12:30"]  # 12:30 kept
    assert '"verified_text":{"items":[{"kind":"status","text":"Hi demo"' in trace.model_dump_json()
    assert AgentTaskTrace.model_validate_json(trace.model_dump_json()) == trace

    for edited in (verified("Hi demo", "Meeting at 12:31"), verified("Hi demo"),
                   verified("Hi demo", "Meeting at 12:30", dropped=1),
                   verified("Hi demo", "Meeting at 12:30", kind="alert")):
        other = rows.build(session=rows.session(
            task_assessment=stored | {"verified_text": edited}))
        assert other.trace_hash != trace.trace_hash
    plain = rows.build()
    assert plain.trace_hash != trace.trace_hash


def test_an_assessment_without_verified_text_hashes_exactly_as_before_phase_10():
    rows, _ = one_step()
    trace = rows.build()
    assert trace.task_assessment.verified_text is None
    payload = trace.model_dump(mode="json", exclude={"trace_hash"})
    del payload["task_assessment"]["verified_text"]  # the pre-phase-10 payload shape
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert hashlib.sha256(canonical.encode()).hexdigest() == trace.trace_hash
    assert "verified_text" not in canonical
    # an empty candidate set is a value, not an absent key: it is hashed
    empty = rows.build(session=rows.session(
        task_assessment=stored_assessment() | {"verified_text": verified()}))
    assert empty.trace_hash != trace.trace_hash


def _old_hash(trace):
    """The hash as phase 16 computed it: sha256 of the canonical payload, which has no flag key."""
    payload = trace.model_dump(mode="json", exclude={"trace_hash"})
    assert not any("derived_from_typed" in item
                   for item in payload["task_assessment"]["verified_text"]["items"])
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def test_a_session_stored_before_phase_17_reads_with_the_flag_false_and_keeps_its_hash():
    rows, _ = one_step()
    stored = stored_assessment() | {"verified_text": verified("Hi demo", "Meeting at 12:30")}
    assert all("derived_from_typed" not in item for item in stored["verified_text"]["items"])
    trace = rows.build(session=rows.session(task_assessment=stored))
    items = trace.task_assessment.verified_text.items
    assert [item.derived_from_typed for item in items] == [False, False]
    assert trace.trace_hash == _old_hash(trace)  # the phase 16 hash, unchanged
    # writing the flag as false explicitly changes nothing either
    explicit = stored | {"verified_text": {**stored["verified_text"], "items": [
        {**item, "derived_from_typed": False} for item in stored["verified_text"]["items"]]}}
    assert rows.build(session=rows.session(task_assessment=explicit)).trace_hash == trace.trace_hash


def test_the_typed_flag_is_kept_hashed_and_round_trips():
    rows, _ = one_step()
    plain = stored_assessment() | {"verified_text": verified("Hi demo", "Meeting at 12:30")}
    flagged_items = [{**item, "derived_from_typed": item["text"] == "Hi demo"}
                     for item in plain["verified_text"]["items"]]
    flagged = plain | {"verified_text": {**plain["verified_text"], "items": flagged_items}}
    plain_trace = rows.build(session=rows.session(task_assessment=plain))
    trace = rows.build(session=rows.session(task_assessment=flagged))
    assert [item.derived_from_typed for item in trace.task_assessment.verified_text.items] == [
        True, False]
    assert trace.trace_hash != plain_trace.trace_hash  # a flag is content: a new session differs
    assert trace.trace_hash == trace.compute_hash()
    assert AgentTaskTrace.model_validate_json(trace.model_dump_json()) == trace
    # moving the flag to the other item is a different trace
    other = flagged | {"verified_text": {**flagged["verified_text"], "items": [
        {**item, "derived_from_typed": not item["derived_from_typed"]}
        for item in flagged_items]}}
    assert rows.build(session=rows.session(task_assessment=other)).trace_hash != trace.trace_hash
    # the flag is a boolean and nothing else is added to the item
    bad = flagged | {"verified_text": {**flagged["verified_text"], "items": [
        {**flagged_items[0], "typed_value": "x"}]}}
    assert refused(rows, session=rows.session(task_assessment=bad)).code == "assessment_unavailable"


@pytest.mark.parametrize("bad", [
    {**verified("x"), "surprise": 1},
    {"items": [{"kind": "status", "text": "x", "check_index": 0, "surprise": 1}],
     "dropped": 0, "truncated": False},
    verified("x", kind="banner"),
    verified("x" * 161),
    verified(""),
    verified(*[f"t{n}" for n in range(101)]),
    {**verified("x"), "dropped": -1},
    {"items": [{"kind": "status", "text": "x", "check_index": 12}],
     "dropped": 0, "truncated": False},
    "text",
])
def test_a_malformed_verified_text_is_a_refusal_not_a_crash(bad):
    rows, _ = one_step()
    error = refused(rows, session=rows.session(
        task_assessment=stored_assessment() | {"verified_text": bad}))
    assert error.code == "assessment_unavailable"


def test_what_verify_quotes_produces_is_accepted_by_the_contract():
    observation = SimpleNamespace(
        page_text=[SimpleNamespace(kind="status", text="Saved at 12:30"),
                   SimpleNamespace(kind="paragraph", text="Welcome back, demo user")],
        elements=[SimpleNamespace(name="Save")],
    )
    seen = ObservedText()
    seen.add(observation)
    result = AgentTaskResult(
        status="achieved", summary="done",
        checks=(AgentTaskCheck(expectation="Banner", status="met",
                               evidence="saw 'Saved at 12:30' and \"Save\" and \"Welcome back\""),
                AgentTaskCheck(expectation="Other", status="met", evidence="'Never shown'")),
    )
    produced = verify_quotes(result.checks, seen)
    assert {item["kind"] for item in produced["items"]} == {"status", "control_name", "paragraph"}
    assert produced["dropped"] == 1
    rows, _ = one_step()
    stored = from_task_result(result, FACTS) | {"verified_text": produced}
    trace = rows.build(session=rows.session(task_assessment=stored))
    assert trace.task_assessment.verified_text.model_dump(mode="json") == produced


def test_verify_quotes_never_emits_more_items_than_the_contract_accepts():
    seen = ObservedText()
    for number in range(150):
        seen.add(SimpleNamespace(page_text=[SimpleNamespace(kind="status", text=f"row {number}")],
                                 elements=[]))
    quotes = " ".join(f"'row {number}'" for number in range(25))
    checks = tuple(
        SimpleNamespace(status="met", expectation="e", evidence=quotes) for _ in range(12))
    produced = verify_quotes(checks, seen)
    assert len(produced["items"]) == VERIFIED_ITEMS_MAX == VERIFIED_TEXT_ITEMS_MAX
    assert produced["dropped"] == 12 * 25 - VERIFIED_ITEMS_MAX
    AgentTaskAssessmentCopy.model_validate(stored_assessment() | {"verified_text": produced})


def test_a_non_uuid_operation_id_in_the_step_log_is_a_refusal():
    rows, op = one_step()
    rows.steps[0].operation_ids[0] = "not-a-uuid"
    error = refused(rows)
    assert error.code == "evidence_unavailable" and error.step_index == rows.steps[0].step_index


def test_a_target_url_over_the_contract_limit_is_a_refusal():
    rows, _ = one_step()
    error = refused(rows, session=rows.session(target_url="https://x.test/" + "a" * 2100))
    assert error.code == "evidence_unavailable"


# --------------------------------------------------------------------------- real sessions, scope

def agent_session(disposable_database, monkeypatch):
    """Real loop, fake worker: type, type, click (page changes, so the wait is skipped), done."""
    def plan(request, ordinal):
        if request.action.kind == "click":
            return Outcome(url_change="changed")
        return Outcome()

    from test_vision_agent_loop import FakeWorker
    worker = FakeWorker(None, None, plan=plan)
    outputs = [step(typed("1:2", TYPED_NAME), typed("1:3", TYPED_SECRET), click("1:6"), wait()),
               DONE]
    run = run_agent(disposable_database, monkeypatch, outputs, worker=worker)
    assert run.error is None and ended(run) == "agent_done"
    return run


def read(run, scope=None):
    scope = scope or run.scope
    with run.factory() as db:
        return read_agent_task_trace(
            SqlAlchemyVisionRepository(db), SqlAlchemyVisualTraceRepository(db), scope)


def test_a_real_agent_session_reads_back_as_a_typed_linear_trace(disposable_database, monkeypatch):
    run = agent_session(disposable_database, monkeypatch)
    skipped = [a for s in run.steps for a in s.actions if a.get("skipped_reason")]
    assert [a["kind"] for a in skipped] == ["wait"]            # case (b) happened for real
    assert any(op.purpose == "setup" for op in run.operations)  # case (a) happened for real
    trace = read(run)
    assert [(s.kind, s.text_chars) for s in trace.steps] == [
        ("type", len(TYPED_NAME)), ("type", len(TYPED_SECRET)), ("click", None)]
    assert [s.step_index for s in trace.steps] == [1, 1, 1]
    assert all(s.locator.strategy == "role" for s in trace.steps)
    assert trace.task_assessment.status == "achieved"
    assert trace.target_url == "https://app.test/"
    assert trace.intent_hash == "a" * 64 and trace.trace_hash == trace.compute_hash()
    assert read(run) == trace                                    # stable across reads
    for needle in (TYPED_NAME, TYPED_SECRET):
        assert needle not in trace.model_dump_json()


def test_another_tenant_project_or_session_cannot_read_the_trace(disposable_database, monkeypatch):
    run = agent_session(disposable_database, monkeypatch)
    scope = run.scope
    for foreign in (
        VisualSessionScope("tenant-b", scope.project_id, scope.session_id),
        VisualSessionScope(scope.tenant_id, uuid4(), scope.session_id),
        VisualSessionScope(scope.tenant_id, scope.project_id, uuid4()),
    ):
        with pytest.raises(AgentTaskTraceNotFound):
            read(run, foreign)
    assert read(run).session_id == scope.session_id


def test_a_real_session_that_is_not_finished_is_refused_not_guessed(
    disposable_database, monkeypatch,
):
    run = agent_session(disposable_database, monkeypatch)
    with run.factory.begin() as db:
        record = SqlAlchemyVisionRepository(db).get(run.scope.tenant_id, run.scope.session_id)
        record.state = "unavailable"
    with pytest.raises(AgentTaskTraceRefused) as caught:
        read(run)
    assert caught.value.code == "assessment_unavailable"
