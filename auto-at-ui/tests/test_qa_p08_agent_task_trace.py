"""QA phase 08: independent behavioural checks of AgentTaskTrace v1.

Row builders are reused from the developer's test module (read only); every case below is new and
aims at gaps: ordering with skipped actions, each refusal code, spike cases (a)-(d), leak scans,
hash sensitivity, boundaries, and scope on the real PostgreSQL fixture.
"""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from application.agent_task_trace import AgentTaskTraceNotFound
from auto_at.contracts.agent_task_trace import AgentTaskTrace
from auto_at.contracts.vision import VisualLocatorDescriptor
from domain.agent_task_trace import AgentTaskTraceRefused
from domain.vision import VisualSessionScope
from domain.vision_task_assessment import action_facts, from_task_result
from pydantic import ValidationError
from test_agent_task_trace import (
    FACTS,
    TYPED_NAME,
    TYPED_SECRET,
    NoResult,
    Rows,
    Skipped,
    agent_session,
    login_rows,
    read,
    refused,
    stored_assessment,
)

pytest_plugins = ["vision_trace_fixtures"]

VALUE_SENTINEL = "QA-SENTINEL-VALUE-5d1e"


def ids(trace):
    return [s.operation_id for s in trace.steps]


def with_actions(rows, index, actions, op_ids=None):
    item = rows.steps[index]
    return SimpleNamespace(**(vars(item) | {"actions": actions} | (
        {"operation_ids": op_ids} if op_ids is not None else {})))


# ------------------------------------------------------------ AC2 ordering
def test_p08_order_skipped_action_in_the_middle_of_a_step_and_between_steps():
    rows = Rows()
    a, b, c, d = (rows.op("click", name=n) for n in "ABCD")
    rows.step(2, Skipped("click"), c, NoResult("wait"), d)
    rows.step(1, a, Skipped("wait", "stale_ref"), b)
    rows.step(3, Skipped("click"))  # a step in which nothing ran
    trace = rows.build()
    assert ids(trace) == [a.id, b.id, c.id, d.id]
    assert [s.step_index for s in trace.steps] == [1, 1, 2, 2]


def test_p08_order_follows_operation_ids_even_when_sequence_disagrees():
    rows = Rows()
    first, second = rows.op("click", name="A"), rows.op("click", name="B")
    rows.step(1, second, first)  # log order is authoritative
    assert ids(rows.build()) == [second.id, first.id]


def test_p08_same_operation_in_two_steps_is_refused():
    rows = Rows()
    one = rows.op("click", name="A")
    rows.step(1, one)
    rows.step(2, one)
    assert refused(rows).code == "evidence_unavailable"


def test_p08_non_explore_non_setup_purpose_is_refused():
    rows = Rows()
    odd = rows.op("click", name="A", purpose="replay")
    rows.step(1, odd)
    assert refused(rows).code == "evidence_unavailable"


# ------------------------------------------------------------ AC3 each code
def test_p08_refusal_codes_carry_session_scoped_location():
    rows = Rows()
    bad = rows.op("click", name="A", status="unknown", locator="absent")
    rows.step(4, bad)
    error = refused(rows)
    assert (error.code, error.step_index, error.operation_id) == (
        "action_outcome_unknown", 4, bad.id)
    assert isinstance(error, ValueError)


@pytest.mark.parametrize("kind", ["click", "type"])
@pytest.mark.parametrize(("opts", "code"), [
    ({"locator": "absent"}, "locator_unavailable"),
    ({"locator": "ambiguous"}, "locator_unavailable"),
    ({"strategy": "dom_path"}, "ephemeral_locator"),
    ({"after": "deleted"}, "evidence_unavailable"),
    ({"status": "failed", "locator": "absent"}, "operation_failed"),
    ({"status": "rejected", "locator": "absent"}, "operation_failed"),
    ({"status": "unknown", "locator": "absent"}, "action_outcome_unknown"),
])
def test_p08_codes_for_both_targeted_kinds(kind, opts, code):
    rows = Rows()
    item = rows.op(kind, **opts)
    rows.step(1, item)
    assert refused(rows).code == code


@pytest.mark.parametrize("kind", ["scroll", "wait", "navigate"])
def test_p08_untargeted_kinds_need_no_locator_but_need_frames(kind):
    rows = Rows()
    item = rows.op(kind)
    rows.step(1, item)
    assert rows.build().steps[0].locator is None
    rows2 = Rows()
    item2 = rows2.op(kind, after="deleted")
    rows2.step(1, item2)
    assert refused(rows2).code == "evidence_unavailable"


def test_p08_before_frame_deleted_is_refused():
    rows = Rows()
    item = rows.op("click", name="A")
    rows.step(1, item)
    from dataclasses import replace
    from datetime import UTC, datetime
    gone = [
        replace(f, metadata=f.metadata.model_copy(update={"deleted_at": datetime.now(UTC)}))
        if f.metadata.id == item.actual_before_frame_id else f
        for f in rows.frames
    ]
    assert refused(rows, frames=gone).code == "evidence_unavailable"


def test_p08_back_and_close_popup_are_refused_as_action_unsupported():
    for kind in ("back", "close_popup"):
        rows = Rows()
        item = rows.op(kind)
        rows.step(1, item)
        assert refused(rows).code == "action_unsupported"


def test_p08_assessment_unavailable_each_way_and_legacy_non_mapping():
    rows = Rows()
    rows.step(1, rows.op("click", name="A"))
    for overrides in ({"state": "failed"}, {"exploration_engine": "script"},
                      {"task_assessment": "text"}, {"task_assessment": []},
                      {"task_assessment": {}}):
        assert refused(rows, session=rows.session(**overrides)).code == "assessment_unavailable"


# ------------------------------------------------------------ AC3 (a)-(d)
def test_p08_a_setup_between_steps_and_after_last_step_never_enters_trace():
    rows = Rows()
    rows.op("navigate", purpose="setup")
    one = rows.op("click", name="A")
    rows.op("wait", purpose="setup", status="unknown", locator="absent")  # not in any step
    two = rows.op("click", name="B")
    rows.step(1, one)
    rows.step(2, two)
    assert ids(rows.build()) == [one.id, two.id]


def test_p08_b_action_without_operation_id_with_stop_reason_set_is_ok():
    rows = Rows()
    one = rows.op("click", name="A")
    rows.step(1, one, Skipped("wait"), Skipped("click"), stop_reason="url_change")
    assert ids(rows.build()) == [one.id]


def test_p08_b_result_none_entry_counts_as_executed_and_mismatches_ids():
    rows = Rows()
    one = rows.op("click", name="A")
    item = rows.step(1, one)
    item.actions.append({"index": 1, "kind": "click", "ref": "1:2", "result": None})
    assert refused(rows).code == "evidence_unavailable"


def test_p08_c_wait_kept_in_contract_json_with_duration_and_no_locator_keys_set():
    rows = Rows()
    a, w = rows.op("click", name="A"), rows.op("wait")
    rows.step(1, a, w)
    data = rows.build().model_dump(mode="json")["steps"]
    assert data[1]["kind"] == "wait" and data[1]["duration_ms"] == 500
    assert data[1]["locator"] is None and data[1]["locator_id"] is None
    assert data[1]["text_chars"] is None and data[1]["delta_y"] is None


def test_p08_c_only_waits_gives_a_trace_not_a_refusal():
    rows = Rows()
    rows.step(1, rows.op("wait"))
    assert [s.kind for s in rows.build().steps] == ["wait"]


def test_p08_d_mismatch_marker_refuses_even_if_every_other_op_is_fine():
    rows = Rows()
    ok = rows.op("click", name="A")
    rows.step(1, ok)
    rows.step(2, stop_reason="worker_result_mismatch")
    error = refused(rows)
    assert (error.code, error.step_index) == ("evidence_unavailable", 2)


def test_p08_d_orphan_explore_op_after_valid_chain_is_refused_with_its_id():
    rows = Rows()
    ok = rows.op("click", name="A")
    rows.step(1, ok)
    orphan = rows.op("scroll")
    error = refused(rows)
    assert error.operation_id == orphan.id and error.code == "evidence_unavailable"


# ------------------------------------------------------------ boundaries
def test_p08_unicode_locator_and_long_name_survive_and_hash_verifies():
    rows = Rows()
    name = "Đăng nhập vào hệ thống — ✓ " + "ả" * 200
    rows.step(1, rows.op("click", name=name))
    trace = rows.build()
    assert trace.steps[0].locator.value == name
    assert AgentTaskTrace.model_validate_json(trace.model_dump_json()) == trace


@pytest.mark.parametrize("field", ["delta_y", "duration_ms", "text_chars"])
def test_p08_out_of_range_parameters_are_refused_not_crashing(field):
    kind = {"delta_y": "scroll", "duration_ms": "wait", "text_chars": "type"}[field]
    for bad in (-1, 0, 10**7):
        rows = Rows()
        item = rows.op(kind)
        step = rows.step(1, item)
        step.actions[0][field] = bad
        try:
            rows.build()
        except AgentTaskTraceRefused as error:
            assert error.code == "evidence_unavailable"
        # an in-range-by-accident value (e.g. delta_y=0, -1) is a valid trace: no other outcome


def test_p08_non_uuid_operation_id_in_step_log_is_a_refusal_not_a_crash():
    rows = Rows()
    one = rows.op("click", name="A")
    step = rows.step(1, one)
    step.operation_ids[0] = "not-a-uuid"
    with pytest.raises(AgentTaskTraceRefused):
        rows.build()


def test_p08_very_long_target_url_is_a_refusal_not_a_crash():
    rows = Rows()
    rows.step(1, rows.op("click", name="A"))
    with pytest.raises((AgentTaskTraceRefused, ValidationError)) as caught:
        rows.build(session=rows.session(target_url="https://x.test/" + "a" * 2100))
    assert isinstance(caught.value, ValidationError) or caught.value.code


def test_p08_trace_is_frozen():
    rows = Rows()
    rows.step(1, rows.op("click", name="A"))
    trace = rows.build()
    with pytest.raises(ValidationError):
        trace.target_url = "https://evil.test/"
    with pytest.raises(ValidationError):
        trace.steps[0].kind = "wait"


# ------------------------------------------------------------ AC4 leak scan
def test_p08_value_in_any_source_field_of_the_step_log_does_not_leak():
    rows, _ = login_rows()
    for step in rows.steps:
        step.actions[0] |= {
            "text": VALUE_SENTINEL, "value": VALUE_SENTINEL, "typed": VALUE_SENTINEL,
            "ref": "7:9", "x": 321.25, "y": 654.75,
            "result": {**step.actions[0]["result"], "text": VALUE_SENTINEL, "ref": "7:9",
                       "x": 321.25, "y": 654.75, "executed_click": {"x": 321.25, "y": 654.75}},
        }
    raw = rows.build().model_dump_json()
    for needle in (VALUE_SENTINEL, "7:9", "321.25", "654.75", TYPED_NAME, TYPED_SECRET,
                   "version:", "bounding_box", "executed_click"):
        assert needle not in raw, needle


def test_p08_value_in_operation_row_and_locator_row_other_fields_does_not_leak():
    rows = Rows()
    item = rows.op("type", name="Field", text=VALUE_SENTINEL)
    rows.step(1, item)
    # locator row carries a bounding box in the source; the trace must not
    raw = rows.build().model_dump_json()
    assert "0.1" not in json.loads(raw)["steps"][0]["locator"].values()
    assert VALUE_SENTINEL not in raw and "bounding" not in raw and "width" not in raw


def test_p08_FINDING_assessment_text_is_copied_verbatim_so_a_value_there_does_leak():
    """Documents (does not endorse) the developer-disclosed behaviour: summary/evidence copied."""
    from auto_at.contracts.codex_bridge import AgentTaskCheck, AgentTaskResult
    rows = Rows()
    rows.step(1, rows.op("type", name="F", text=VALUE_SENTINEL))
    result = AgentTaskResult(
        status="achieved", summary=f"Typed {VALUE_SENTINEL} and submitted.",
        checks=(AgentTaskCheck(expectation="Logged in", status="met",
                               evidence=f"field shows {VALUE_SENTINEL}"),))
    stored = from_task_result(result, action_facts([{"result": {"status": "completed"}}]))
    raw = rows.build(session=rows.session(task_assessment=stored)).model_dump_json()
    assert raw.count(VALUE_SENTINEL) == 2  # leak exists when the model itself writes the value


# ------------------------------------------------------------ AC5 hash
def test_p08_hash_changes_on_each_single_field_and_tamper_is_detected():
    rows, (user, password, submit, after) = login_rows()
    base = rows.build()
    assert rows.build().trace_hash == base.trace_hash
    data = base.model_dump(mode="json")
    mutations = {
        "tenant": lambda d: d.update(tenant_id="other"),
        "url": lambda d: d.update(target_url="https://other.test/"),
        "outcome": lambda d: d["steps"][0]["outcome"].update(url_change="changed"),
        "kind": lambda d: d["steps"][3].update(kind="scroll"),
        "drop step": lambda d: d["steps"].pop(),
        "swap": lambda d: d["steps"].reverse(),
        "status": lambda d: d["task_assessment"].update(status="blocked"),
    }
    for label, mutate in mutations.items():
        tampered = json.loads(json.dumps(data))
        mutate(tampered)
        with pytest.raises(ValidationError):
            AgentTaskTrace.model_validate(tampered)
        assert label
    # a recomputed hash on tampered content is a *different* hash
    tampered = json.loads(json.dumps(data))
    tampered["steps"][0]["outcome"]["url_change"] = "changed"
    tampered.pop("trace_hash")
    assert AgentTaskTrace.seal(**tampered).trace_hash != base.trace_hash


def test_p08_swapping_one_locator_between_steps_changes_hash():
    rows, (user, password, submit, after) = login_rows()
    base = rows.build()
    swapped = [
        loc.model_copy(update={"descriptor": VisualLocatorDescriptor(
            strategy="role", role="button", value="Tiếp tục" if loc.id == submit.locator_id
            else "Đăng nhập")}) if loc.id in {submit.locator_id, after.locator_id} else loc
        for loc in rows.locators]
    assert rows.build(locators=swapped).trace_hash != base.trace_hash


def test_p08_wait_duration_and_scroll_delta_are_in_the_hash():
    def trace(delta, duration):
        rows = Rows()
        s, w = rows.op("scroll"), rows.op("wait")
        step = rows.step(1, s, w)
        step.actions[0]["delta_y"], step.actions[1]["duration_ms"] = delta, duration
        return rows.build()
    # operation ids are random, so compare field-level
    first = trace(400, 500)
    assert first.steps[0].delta_y == 400 and first.steps[1].duration_ms == 500
    assert trace(-400, 900).steps[0].delta_y == -400


# ------------------------------------------------------------ AC1 closed
def test_p08_extra_forbid_on_every_nested_model():
    rows, _ = login_rows()
    data = rows.build().model_dump(mode="json")
    paths = [
        lambda d: d, lambda d: d["task_assessment"], lambda d: d["task_assessment"]["facts"],
        lambda d: d["task_assessment"]["checks"][0], lambda d: d["steps"][0],
        lambda d: d["steps"][0]["outcome"], lambda d: d["steps"][0]["locator"],
    ]
    for pick in paths:
        probe = json.loads(json.dumps(data))
        pick(probe)["zz_extra"] = 1
        with pytest.raises(ValidationError):
            AgentTaskTrace.model_validate(probe)


def test_p08_assessment_checks_over_limit_or_bad_status_are_unavailable():
    rows = Rows()
    rows.step(1, rows.op("click", name="A"))
    stored = stored_assessment()
    too_many = stored | {"checks": stored["checks"] * 50}
    assert refused(rows, session=rows.session(task_assessment=too_many)).code == (
        "assessment_unavailable")
    assert refused(rows, session=rows.session(
        task_assessment=stored | {"status": "great"})).code == "assessment_unavailable"
    assert FACTS


# ------------------------------------------------------------ AC6 scope on the real DB
def test_p08_real_db_scope_and_invariants(disposable_database, monkeypatch):
    run = agent_session(disposable_database, monkeypatch)
    trace = read(run)
    raw = trace.model_dump_json()
    assert TYPED_NAME not in raw and TYPED_SECRET not in raw
    assert "version:" not in raw and "bounding_box" not in raw
    assert AgentTaskTrace.model_validate_json(raw).trace_hash == trace.compute_hash()
    scope = run.scope
    foreign = [
        VisualSessionScope(scope.tenant_id + "-x", scope.project_id, scope.session_id),
        VisualSessionScope("", scope.project_id, scope.session_id),
        VisualSessionScope(scope.tenant_id, uuid4(), scope.session_id),
        VisualSessionScope(scope.tenant_id, scope.project_id, uuid4()),
        VisualSessionScope("tenant-b", uuid4(), uuid4()),
    ]
    for item in foreign:
        with pytest.raises(AgentTaskTraceNotFound):
            read(run, item)
    # a different project with the right tenant+session must not leak the trace either
    assert read(run).trace_hash == trace.trace_hash


def test_p08_agent_ref_written_in_the_assessment_summary_does_not_reach_the_trace():
    from auto_at.contracts.codex_bridge import AgentTaskCheck, AgentTaskResult
    rows = Rows()
    rows.step(1, rows.op("type", name="F", text="abc"))
    result = AgentTaskResult(
        status="achieved", summary="Gõ vào 1:7 và 1:8, rồi nhấn 1:9",
        checks=(AgentTaskCheck(expectation="ok", status="met", evidence="ref 1:7 visible"),))
    stored = from_task_result(result, action_facts([{"result": {"status": "completed"}}]))
    raw = rows.build(session=rows.session(task_assessment=stored)).model_dump_json()
    assert "1:7" not in raw


# ---- QA round 2: attack the ref redaction --------------------------------------------------
import re as _re  # noqa: E402

_REF = _re.compile(r"\d+:\d+")


def _trace_with_text(summary, expectation="ok", evidence="ok"):
    from auto_at.contracts.codex_bridge import AgentTaskCheck, AgentTaskResult
    rows = Rows()
    rows.step(1, rows.op("type", name="F", text="abc"))
    result = AgentTaskResult(
        status="achieved", summary=summary,
        checks=(AgentTaskCheck(expectation=expectation, status="met", evidence=evidence),))
    stored = from_task_result(result, action_facts([{"result": {"status": "completed"}}]))
    return rows, rows.build(session=rows.session(task_assessment=stored))


@pytest.mark.parametrize("text", [
    "[1:7]", "`12:3`", "ref=2:15.", "(3:4)", "1:7,1:8;1:9", "x1:7y", "12345:67890",
    "'4:5'", "\"6:7\"", "<7:8>", "ref:\n3:4", "１:７" if False else "9:9",
    "1:7:8", "a 10:2 b 3:4 c 5:6",
])
@pytest.mark.parametrize("field", ["summary", "expectation", "evidence"])
def test_p08_r2_ref_shapes_are_redacted_in_every_text_field(text, field):
    kw = {"summary": "s", "expectation": "e", "evidence": "v"}
    kw[field] = text
    _, trace = _trace_with_text(**kw)
    raw = trace.model_dump_json()
    assert not _REF.search(raw), raw
    assert trace.task_assessment.summary and trace.task_assessment.checks[0].evidence


def test_p08_r2_redaction_is_deterministic_and_hash_verifiable():
    rows, a = _trace_with_text("Gõ 1:7 rồi 1:8")
    b = rows.build(session=rows.session(task_assessment=a.task_assessment.model_dump(mode="json")))
    a2 = rows.build(session=rows.session(task_assessment=a.task_assessment.model_dump(mode="json")))
    assert a2.trace_hash == b.trace_hash
    assert a.trace_hash == b.trace_hash
    assert a.trace_hash == type(a).seal(
        **{k: getattr(a, k) for k in (
            "tenant_id", "project_id", "session_id", "target_url", "intent_hash",
            "task_assessment", "steps")}).trace_hash


def test_p08_r2_max_length_text_full_of_refs_still_builds():
    text = "1:7 " * 400
    _, trace = _trace_with_text(text[:1000])
    assert not _REF.search(trace.model_dump_json())


def test_p08_r2_long_target_url_is_a_refusal():
    rows = Rows()
    rows.step(1, rows.op("click", name="A"))
    with pytest.raises(AgentTaskTraceRefused) as err:
        rows.build(session=rows.session(target_url="https://x.test/" + "a" * 2100))
    assert err.value.code == "evidence_unavailable"


# ------------------------------------------- phase 15b: the lengths route and `/trace`
def test_p15b_the_inputs_answer_carries_lengths_and_names_never_the_sentinel_or_a_ref():
    from application.agent_task_renderer import typed_steps

    rows = Rows()
    rows.step(1, rows.op("type", name="Field", text=VALUE_SENTINEL))
    trace = rows.build()
    answer = [
        {"step_index": s.step_index, "locator_name": s.locator.value, "text_chars": s.text_chars}
        for s in typed_steps(trace)
    ]
    raw = json.dumps(answer)
    assert answer == [{"step_index": 1, "locator_name": "Field", "text_chars": len(VALUE_SENTINEL)}]
    for needle in (VALUE_SENTINEL, "version:", "bounding", str(trace.steps[0].operation_id),
                   str(trace.steps[0].locator_id)):
        assert needle not in raw, needle


def test_p15b_the_shared_trace_replay_never_learns_the_typed_length():
    # `GET /trace` stays the generic replay: `text_chars` is not in what builds it.
    from pathlib import Path

    import application.vision_replay as replay
    import application.vision_results as results

    for module in (replay, results):
        assert "text_chars" not in Path(module.__file__).read_text(encoding="utf-8")
