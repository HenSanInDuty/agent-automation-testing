"""ADR-047 phase B4: the deterministic renderer from an `AgentTaskTrace` to Playwright source.

Traces are built by hand in the shape of the three fixture tasks (`benchmarks/task-ui/tasks.v1.json`)
and sealed through the real contract, so the renderer sees exactly what phase 08 produces.
"""

# ruff: noqa: E501  (the snapshots below are single generated lines)
import itertools
import json
import shutil
import subprocess
from uuid import UUID

import pytest
from application.agent_task_renderer import (
    AgentTaskRenderRefused,
    has_test_values,
    render_agent_task_source,
)
from application.vision_source_renderer import literal
from auto_at.contracts.agent_task_trace import (
    AgentTaskAssessmentCopy,
    AgentTaskTrace,
    AgentTaskTraceOutcome,
    AgentTaskTraceStep,
)
from auto_at.contracts.execution import PlaywrightTestSourceMode, sha256_text
from auto_at.contracts.generation import (
    AgentTraceSource,
    GeneratedTestDraft,
    PlanningProvenance,
    origin_for_url,
)
from auto_at.contracts.vision import VisualLocatorDescriptor

SESSION = UUID("00000000-0000-4000-8000-0000000000a1")
PROJECT = UUID("00000000-0000-4000-8000-0000000000b2")
URL = "http://task-target:7300/login"


def role(kind, name):
    return VisualLocatorDescriptor(strategy="role", role=kind, value=name)


_NUMBERS = itertools.count(1)


def step(index, kind, *, locator=None, **params):
    """One trace step with its own operation id (the contract refuses a repeated one)."""
    number = next(_NUMBERS)
    targeted = locator is not None
    return AgentTaskTraceStep(
        step_index=index,
        operation_id=UUID(int=0x1000 + number),
        kind=kind,
        locator_id=UUID(int=0x2000 + number) if targeted else None,
        locator=locator,
        outcome=AgentTaskTraceOutcome(
            outcome_code="observed", url_change="unchanged", visual_change="changed"
        ),
        **params,
    )


def typed(index, name, chars):
    return step(index, "type", locator=role("textbox", name), text_chars=chars)


def clicked(index, name, kind="button"):
    return step(index, "click", locator=role(kind, name))


def assessment(items=(), *, dropped=0, truncated=False, status="achieved"):
    verified = None
    if items is not None:
        verified = {
            "items": [
                {"kind": kind, "text": text, "check_index": 0}
                | ({"derived_from_typed": True} if flagged else {})
                for kind, text, *flagged in items
            ],
            "dropped": dropped,
            "truncated": truncated,
        }
    return AgentTaskAssessmentCopy.model_validate(
        {
            "schema_version": "v1",
            "status": status,
            "summary": "Did the task.",
            "checks": [{"expectation": "Result shown", "status": "met", "evidence": "'x'"}],
            "source": "agent",
            "stop_reason": "agent_done",
            "facts": {
                "actions_completed": 1,
                "actions_failed": 0,
                "actions_blocked_or_skipped": 0,
            },
            "advisory": True,
            "verified_text": verified,
        }
    )


def trace_of(steps, items=(), *, target_url=URL, **options):
    return AgentTaskTrace.seal(
        tenant_id="tenant-a",
        project_id=PROJECT,
        session_id=SESSION,
        target_url=target_url,
        intent_hash="b" * 64,
        task_assessment=assessment(items, **options),
        steps=tuple(steps),
    )


def login_success():
    return trace_of(
        [typed(1, "Tên đăng nhập", 4), typed(1, "Mật khẩu", 8), clicked(1, "Đăng nhập")],
        [("status", "Xin chào, demo"), ("control_name", "Đăng xuất")],
        target_url="http://task-target:7300/login",
    ), ["demo", "Demo1234"]


def todo_add():
    return trace_of(
        [typed(1, "Việc mới", 12), clicked(1, "Thêm")],
        [("paragraph", "3 việc, 1 đã xong"), ("status", "Viết báo cáo")],
        target_url="http://task-target:7300/todos",
    ), ["Viết báo cáo"]


def search_results():
    label = VisualLocatorDescriptor(strategy="label", value="Từ khoá")
    return trace_of(
        [step(1, "type", locator=label, text_chars=4), clicked(1, "Tìm")],
        [("paragraph", "Balo laptop")],
        target_url="http://task-target:7300/search",
    ), ["balo"]


def refused(trace, values=()):
    with pytest.raises(AgentTaskRenderRefused) as caught:
        render_agent_task_source(trace, values)
    return caught.value


def lines_of(output):
    return output.playwright_test_source.splitlines()


# --------------------------------------------------------------------------- snapshots

HEAD = r"""import { test, expect } from '@playwright/test';
test("Agent task 00000000-0000-4000-8000-0000000000a1", async ({ page }) => {
  const active = page;
"""
LOGIN_SUCCESS = HEAD + r"""  await active.goto("http://task-target:7300/login");
  const target0 = active.getByRole("textbox", { name: "T\u00ean \u0111\u0103ng nh\u1eadp", exact: true });
  await expect(target0).toBeVisible();
  await expect(target0).toBeEnabled();
  await target0.fill("demo");
  const target1 = active.getByRole("textbox", { name: "M\u1eadt kh\u1ea9u", exact: true });
  await expect(target1).toBeVisible();
  await expect(target1).toBeEnabled();
  await target1.fill("Demo1234");
  const target2 = active.getByRole("button", { name: "\u0110\u0103ng nh\u1eadp", exact: true });
  await expect(target2).toBeVisible();
  await expect(target2).toBeEnabled();
  await target2.click();
  await expect(active.getByText("Xin ch\u00e0o, demo").first()).toBeVisible();
  await expect(active.getByText("\u0110\u0103ng xu\u1ea5t", { exact: true }).or(active.getByLabel("\u0110\u0103ng xu\u1ea5t", { exact: true })).first()).toBeVisible();
});
"""
TODO_ADD = HEAD + r"""  await active.goto("http://task-target:7300/todos");
  const target0 = active.getByRole("textbox", { name: "Vi\u1ec7c m\u1edbi", exact: true });
  await expect(target0).toBeVisible();
  await expect(target0).toBeEnabled();
  await target0.fill("Vi\u1ebft b\u00e1o c\u00e1o");
  const target1 = active.getByRole("button", { name: "Th\u00eam", exact: true });
  await expect(target1).toBeVisible();
  await expect(target1).toBeEnabled();
  await target1.click();
  await expect(active.getByText("3 vi\u1ec7c, 1 \u0111\u00e3 xong").first()).toBeVisible();
  await expect(active.getByText("Vi\u1ebft b\u00e1o c\u00e1o").first()).toBeVisible();
});
"""
SEARCH_RESULTS = HEAD + r"""  await active.goto("http://task-target:7300/search");
  const target0 = active.getByLabel("T\u1eeb kho\u00e1", { exact: true });
  await expect(target0).toBeVisible();
  await expect(target0).toBeEnabled();
  await target0.fill("balo");
  const target1 = active.getByRole("button", { name: "T\u00ecm", exact: true });
  await expect(target1).toBeVisible();
  await expect(target1).toBeEnabled();
  await target1.click();
  await expect(active.getByText("Balo laptop").first()).toBeVisible();
});
"""
SAMPLES = {
    "login-success": (login_success, LOGIN_SUCCESS),
    "todo-add": (todo_add, TODO_ADD),
    "search-results": (search_results, SEARCH_RESULTS),
}


def provenance_of(trace, **options):
    return PlanningProvenance(
        provider="deterministic",
        model="agent-task-renderer",
        prompt_version="none",
        redaction_policy_version="v1",
        agent_trace_source=AgentTraceSource(
            session_id=trace.session_id, trace_hash=trace.trace_hash
        ),
        contains_test_values=has_test_values(trace),
        owned_test_target=True,
        requested_by="actor-1",
        **options,
    )


@pytest.mark.parametrize("name", SAMPLES)
def test_fixture_task_sources_match_their_snapshot_and_pass_the_runner_contract(name):
    make, expected = SAMPLES[name]
    trace, values = make()
    output = render_agent_task_source(trace, values)
    assert output.playwright_test_source == expected
    source_hash = sha256_text(expected)
    mode = PlaywrightTestSourceMode(
        playwright_test_source=output.playwright_test_source,
        source_hash=source_hash,
        allowed_origins=[origin_for_url(trace.target_url)],
    )
    assert mode.allowed_origins == ["http://task-target:7300"]
    draft = GeneratedTestDraft(
        planning_request_id=UUID(int=7),
        correlation_id=UUID(int=8),
        title=output.title,
        playwright_test_source=output.playwright_test_source,
        source_hash=source_hash,
        assumptions=output.assumptions,
        stop_conditions=output.stop_conditions,
        provenance=provenance_of(trace),
    )
    assert draft.provenance.contains_test_values is True


def test_the_source_is_valid_javascript(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    hostile = [
        'say "hi"',
        "back\\slash",
        "line\nbreak\ttab\x07bell",
        "</script>${x}`",
        "\u2028\u2029",
    ]
    steps = [typed(1, f"Field {n}", len(value)) for n, value in enumerate(hostile)]
    trace = trace_of(steps, [("alert", 'a "quoted" \\ line\nbreak \x07')])
    source = render_agent_task_source(trace, hostile).playwright_test_source
    target = tmp_path / "generated.spec.mjs"
    target.write_text(source, encoding="utf-8")
    done = subprocess.run(
        [node, "--check", str(target)], capture_output=True, text=True, timeout=60, check=False
    )
    assert done.returncode == 0, done.stderr


# --------------------------------------------------------------------------- steps and order


def test_every_supported_kind_is_rendered_in_trace_order_with_values_in_step_order():
    steps = [
        step(1, "navigate"),
        typed(2, "First", 5),
        clicked(2, "Go"),
        step(3, "scroll", delta_y=-400),
        step(4, "wait", duration_ms=750),
        typed(5, "Second", 6),
    ]
    source = render_agent_task_source(trace_of(steps), ["alpha", "bravo!"]).playwright_test_source
    wanted = [
        f"await active.goto({literal(URL)});",  # the trace starts from the target url
        f"await active.goto({literal(URL)});",  # the recorded navigate step
        'fill("alpha")',
        ".click();",
        "await active.mouse.wheel(0, -400);",
        "await active.waitForTimeout(750);",
        'fill("bravo!")',
    ]
    at = -1
    for marker in wanted:
        at = source.index(marker, at + 1)
    assert source.count("await active.goto(") == 2


def test_each_targeted_step_uses_its_own_verified_locator_and_baseline_checks():
    source = render_agent_task_source(
        trace_of([clicked(1, "Open", kind="link"), clicked(2, "Save")])
    ).playwright_test_source
    for n, (kind, name) in enumerate([("link", "Open"), ("button", "Save")]):
        locator = f'active.getByRole("{kind}", {{ name: "{name}", exact: true }})'
        assert f"const target{n} = {locator};" in source
        checks = f"await expect(target{n}).toBeVisible();\n  await expect(target{n}).toBeEnabled();"
        assert checks in source


def test_a_real_trace_from_the_builder_renders_its_steps_in_session_order():
    from test_agent_task_trace import TYPED_NAME, TYPED_SECRET, login_rows

    rows, _ = login_rows()
    source = render_agent_task_source(
        rows.build(), [TYPED_NAME, TYPED_SECRET]
    ).playwright_test_source
    order = [source.index(literal(text)) for text in (TYPED_NAME, TYPED_SECRET)]
    assert order == sorted(order)
    names = ["Tên đăng nhập", "Mật khẩu", "Đăng nhập", "Tiếp tục"]
    positions = [source.index(literal(name)) for name in names]
    assert positions == sorted(positions)
    assert source.count(".click();") == 2 and source.count(".fill(") == 2


# --------------------------------------------------------------------------- locators


def broken_trace(bad):
    """A trace built around the contract: a step with no usable locator (the builder refuses it)."""
    good = clicked(1, "Fine")
    base = trace_of([good])
    fields = {name: getattr(base, name) for name in type(base).model_fields}
    return AgentTaskTrace.model_construct(**fields | {"steps": (good, bad)})


def test_a_click_without_a_locator_is_refused_naming_that_step():
    bad = AgentTaskTraceStep.model_construct(
        step_index=4, operation_id=UUID(int=0x99), kind="click", locator=None, locator_id=None
    )
    error = refused(broken_trace(bad))
    assert (error.code, error.step_index, error.operation_id) == (
        "locator_unavailable",
        4,
        UUID(int=0x99),
    )
    assert str(error) == "locator_unavailable"


def test_a_type_step_with_an_ephemeral_locator_is_refused_naming_that_step():
    from test_agent_task_trace import DOM_PATH

    path = VisualLocatorDescriptor(schema_version="v2", strategy="dom_path", value=DOM_PATH)
    bad = AgentTaskTraceStep.model_construct(
        step_index=2,
        operation_id=UUID(int=0x77),
        kind="type",
        locator=path,
        locator_id=UUID(int=1),
        text_chars=3,
    )
    error = refused(broken_trace(bad), ["abc"])
    assert (error.code, error.step_index, error.operation_id) == (
        "locator_unavailable",
        2,
        UUID(int=0x77),
    )


def test_a_password_labelled_field_never_reaches_the_renderer():
    """Q4 unchanged: the locator filter cannot bind the field, so the trace is not even built."""
    from domain.agent_task_trace import AgentTaskTraceRefused
    from test_agent_task_trace import Rows

    rows = Rows()
    rows.op("navigate", purpose="setup")
    user = rows.op("type", name="Tên đăng nhập", text="demo")
    password = rows.op("type", name="Password", text="hunter22", locator="absent")
    rows.step(1, user, password)
    with pytest.raises(AgentTaskTraceRefused) as caught:
        rows.build()
    assert (caught.value.code, caught.value.step_index) == ("locator_unavailable", 1)
    assert caught.value.operation_id == password.id
    with pytest.raises(ValueError):  # and the label itself cannot become a descriptor
        role("textbox", "Password")


# --------------------------------------------------------------------------- typed values


def one_type_trace():
    return trace_of([typed(1, "Name", 5), clicked(1, "Go")])


def test_a_missing_value_is_refused_naming_the_first_step_without_one():
    trace = trace_of([typed(1, "A", 3), typed(2, "B", 4)])
    error = refused(trace, ["abc"])
    assert (error.code, error.step_index) == ("input_value_missing", 2)
    assert refused(trace).step_index == 1


@pytest.mark.parametrize("value", ["abcd", "abcdef", ""])
def test_a_value_of_another_length_than_the_recorded_text_is_refused(value):
    error = refused(one_type_trace(), [value])
    assert (error.code, error.step_index) == ("input_value_mismatch", 1)


def test_the_length_is_counted_in_characters_not_bytes():
    render_agent_task_source(one_type_trace(), ["Việt!"])  # 5 characters, 7 bytes
    assert refused(one_type_trace(), ["Việt"]).code == "input_value_mismatch"


def test_a_value_no_step_asked_for_is_refused():
    assert refused(trace_of([clicked(1, "Go")]), ["x"]).code == "input_value_mismatch"
    assert refused(one_type_trace(), ["abcde", "extra"]).code == "input_value_mismatch"


@pytest.mark.parametrize("value", ["process", "fetch", "eval()", "import(1)"])
def test_a_value_the_source_policy_rejects_is_refused_without_echoing_it(value):
    trace = trace_of([typed(1, "A", 4), typed(1, "B", len(value))])
    error = refused(trace, ["safe", value])
    assert (error.code, error.step_index) == ("input_value_rejected_by_source_policy", 1)
    assert error.operation_id == trace.steps[1].operation_id
    for shown in (str(error), repr(error), repr(error.args), repr(error.__context__)):
        assert value not in shown


def test_a_policy_rejection_that_is_not_the_value_is_not_blamed_on_it():
    # a control named `process` is a legitimate descriptor but the source policy refuses `process`
    trace = trace_of([step(1, "click", locator=role("button", "process"))])
    assert refused(trace).code == "source_policy_rejected"


@pytest.mark.parametrize(
    "value",
    [
        'quo"te',
        "back\\slash",
        "tab\tnew\nline",
        "bell\x07",
        "${x}`",
        "\u2028x",
        "Việt \U0001f600",
    ],
)
def test_values_are_emitted_as_json_literals_whatever_they_contain(value):
    trace = trace_of([typed(1, "Field", len(value))])
    source = render_agent_task_source(trace, [value]).playwright_test_source
    assert f".fill({json.dumps(value, ensure_ascii=True)});" in source
    assert source.isascii()


# --------------------------------------------------------------------------- assertions


def final_lines(output):
    lines = lines_of(output)
    return lines[lines.index("  await target1.click();") + 1 : -1]


def test_candidates_become_assertions_after_the_last_step_in_observed_order():
    trace = trace_of(
        [typed(1, "Name", 4), clicked(1, "Go")],
        [("alert", "Saved"), ("heading", "Done"), ("status", "Saved")],  # a repeat is not doubled
    )
    output = render_agent_task_source(trace, ["abcd"])
    assert final_lines(output) == [
        '  await expect(active.getByText("Saved").first()).toBeVisible();',
        '  await expect(active.getByText("Done").first()).toBeVisible();',
    ]
    assert any("2 assertion" in note for note in output.stop_conditions)


def test_a_control_name_candidate_is_matched_exactly_by_text_or_label():
    trace = trace_of([typed(1, "Name", 4), clicked(1, "Go")], [("control_name", "Logout")])
    (line,) = final_lines(render_agent_task_source(trace, ["abcd"]))
    assert line == (
        '  await expect(active.getByText("Logout", { exact: true })'
        '.or(active.getByLabel("Logout", { exact: true })).first()).toBeVisible();'
    )


def test_candidate_text_goes_through_the_safe_literal():
    text = 'He said "hi" \\ done\x07\u2028'
    trace = trace_of([typed(1, "Name", 4), clicked(1, "Go")], [("alert", text)])
    (line,) = final_lines(render_agent_task_source(trace, ["abcd"]))
    assert line == f"  await expect(active.getByText({json.dumps(text)}).first()).toBeVisible();"
    assert "\x07" not in line and "\u2028" not in line


@pytest.mark.parametrize("items", [(), None], ids=["empty list", "assessment without the key"])
def test_without_candidates_only_the_baseline_remains_and_the_gap_is_stated(items):
    trace = trace_of([typed(1, "Name", 4), clicked(1, "Go")], items)
    output = render_agent_task_source(trace, ["abcd"])
    assert final_lines(output) == []
    assert output.playwright_test_source.count("expect(") == 4  # visible + enabled per control
    assert any(
        "not asserted" in note and "chưa được assert" in note for note in output.stop_conditions
    )
    assert not any("assertion(s)" in note for note in output.stop_conditions)


def test_a_candidate_the_source_policy_refuses_is_left_out_and_counted():
    trace = trace_of(
        [clicked(1, "Go")], [("status", "Order process finished"), ("status", "Order placed")]
    )
    output = render_agent_task_source(trace)
    assert "process" not in output.playwright_test_source
    assert 'getByText("Order placed")' in output.playwright_test_source
    assert any("1 candidate(s) were left out" in note for note in output.stop_conditions)


# A third element of an item marks it `derived_from_typed` (phase 17, F5).
TYPED = True


def test_a_candidate_holding_a_typed_value_is_not_asserted_and_the_note_says_why():
    trace = trace_of(
        [typed(1, "Name", 4), clicked(1, "Go")],
        [("status", "Saved: abcd", TYPED), ("heading", "Done")],
    )
    output = render_agent_task_source(trace, ["wxyz"])
    assert final_lines(output) == ['  await expect(active.getByText("Done").first()).toBeVisible();']
    assert "Saved" not in output.playwright_test_source
    notes = " ".join(output.stop_conditions)
    assert "1 candidate(s) were left out: their text holds a value typed in the session" in notes
    assert "1 assertion(s)" in notes  # only the clean candidate counts as asserted
    assert not any("Saved" in note or "abcd" in note or "wxyz" in note for note in output.stop_conditions)
    assert not any("abcd" in note or "wxyz" in note for note in output.assumptions)


def test_when_every_candidate_holds_a_typed_value_the_outcome_is_stated_as_not_asserted():
    trace = trace_of(
        [typed(1, "Name", 4), clicked(1, "Go")],
        [("status", "Hi abcd", TYPED), ("alert", "Saved abcd", TYPED)],
    )
    output = render_agent_task_source(trace, ["wxyz"])
    assert final_lines(output) == []
    assert any("not asserted" in note for note in output.stop_conditions)
    assert any("2 candidate(s) were left out" in note for note in output.stop_conditions)


def test_a_clean_candidate_is_still_asserted_whatever_value_the_requester_types():
    trace = trace_of([typed(1, "Name", 4), clicked(1, "Go")], [("heading", "Todo list")])
    for value in ("abcd", "wxyz"):
        output = render_agent_task_source(trace, [value])
        assert final_lines(output) == [
            '  await expect(active.getByText("Todo list").first()).toBeVisible();']
        assert not any("typed in the session" in note for note in output.stop_conditions)


def test_the_typed_note_is_not_mixed_up_with_the_source_policy_note():
    trace = trace_of(
        [clicked(1, "Go")],
        [("status", "Order process finished"), ("status", "Order abcd", TYPED), ("status", "Placed")],
    )
    output = render_agent_task_source(trace)
    assert any("1 candidate(s) were left out: the source policy" in n for n in output.stop_conditions)
    assert any("1 candidate(s) were left out: their text holds" in n for n in output.stop_conditions)
    assert 'getByText("Placed")' in output.playwright_test_source


def test_unverified_or_truncated_quotes_are_reported_not_asserted():
    trace = trace_of([clicked(1, "Go")], [("status", "Ok")], dropped=3, truncated=True)
    notes = render_agent_task_source(trace).stop_conditions
    assert any("dropped 3" in note and "truncated True" in note for note in notes)


# --------------------------------------------------------------------------- values stay in the source

SENTINEL = "ZQsentinel9f3A"


def test_a_typed_value_appears_only_in_the_returned_source():
    trace = trace_of([typed(1, "Name", len(SENTINEL)), clicked(1, "Go")], [("status", "Welcome")])
    output = render_agent_task_source(trace, [SENTINEL])
    assert output.playwright_test_source.count(SENTINEL) == 1
    elsewhere = output.model_dump(exclude={"playwright_test_source"})
    assert SENTINEL not in json.dumps(elsewhere, ensure_ascii=False)
    assert SENTINEL not in provenance_of(trace).model_dump_json()
    assert SENTINEL not in trace.model_dump_json()


@pytest.mark.parametrize(
    "case",
    [
        (lambda: trace_of([typed(1, "Name", 2)]), SENTINEL),  # wrong length
        (lambda: trace_of([clicked(1, "Go")]), SENTINEL),  # no step wants it
        (lambda: trace_of([typed(1, "Name", 7)]), "process"),  # the source policy refuses it
    ],
    ids=["mismatch", "extra", "policy"],
)
def test_no_refusal_carries_the_value(case):
    build, secret = case
    error = refused(build(), [secret])
    for shown in (str(error), repr(error), repr(error.args), repr(error.__context__), error.code):
        assert secret not in shown
    assert error.__cause__ is None


def test_the_title_and_notes_do_not_depend_on_the_value():
    trace = trace_of([typed(1, "Name", 4)])
    first = render_agent_task_source(trace, ["aaaa"])
    second = render_agent_task_source(trace, ["bbbb"])
    assert (first.title, first.assumptions, first.stop_conditions) == (
        second.title,
        second.assumptions,
        second.stop_conditions,
    )
    assert first.playwright_test_source != second.playwright_test_source


# --------------------------------------------------------------------------- misc and purity


def test_the_same_input_gives_the_same_source_and_hash():
    trace, values = login_success()
    first = render_agent_task_source(trace, values)
    again = render_agent_task_source(trace, list(values))
    rebuilt = render_agent_task_source(AgentTaskTrace.model_validate(trace.model_dump()), values)
    assert first == again == rebuilt
    assert sha256_text(first.playwright_test_source) == sha256_text(rebuilt.playwright_test_source)


@pytest.mark.parametrize("url", ["ftp://app.test/", "http://user:pw@app.test/", "app.test/login"])
def test_a_target_that_is_not_a_plain_http_origin_is_refused(url):
    assert refused(trace_of([clicked(1, "Go")], target_url=url)).code == "target_url_invalid"


def test_a_source_over_the_limit_is_refused_not_truncated():
    trace = trace_of([step(n, "wait", duration_ms=100) for n in range(1, 3000)])
    assert refused(trace).code == "rendered_source_limit"


def test_contains_test_values_follows_the_type_steps():
    assert has_test_values(one_type_trace()) is True
    assert has_test_values(trace_of([clicked(1, "Go"), step(2, "scroll", delta_y=100)])) is False
    clicks_only = render_agent_task_source(trace_of([clicked(1, "Go")]))
    assert not any("typed value" in note for note in clicks_only.assumptions)
    assert provenance_of(trace_of([clicked(1, "Go")])).contains_test_values is False


