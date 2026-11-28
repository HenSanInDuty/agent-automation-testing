"""QA phase 11: independent checks of the linear renderer and the additive provenance.

Reuses only the trace builders of the developer tests; every oracle below is written separately
(grammar of allowed lines, node evaluation of literals, sentinel scan, subprocess determinism).
"""

# ruff: noqa: E501
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path
from uuid import UUID

import pytest
from application.agent_task_renderer import (
    AgentTaskRenderRefused,
    has_test_values,
    render_agent_task_source,
)
from application.vision_source_renderer import literal
from auto_at.contracts.agent_task_trace import AgentTaskTrace, AgentTaskTraceStep
from auto_at.contracts.execution import PlaywrightTestSourceMode, sha256_text
from auto_at.contracts.generation import (
    AgentTraceSource,
    GeneratedTestDraft,
    PlanningProvenance,
    origin_for_url,
)
from auto_at.contracts.vision import VisualLocatorDescriptor
from pydantic import ValidationError
from test_agent_task_renderer import (
    PROJECT,
    SESSION,
    URL,
    clicked,
    login_success,
    provenance_of,
    role,
    search_results,
    step,
    todo_add,
    trace_of,
    typed,
)

NODE = shutil.which("node")
SENTINEL = "ZQsentinel9f3A"
UNICODE_SENTINEL = "Zqết-Sấn-9f3A"


def refusal(trace, values=()):
    with pytest.raises(AgentTaskRenderRefused) as caught:
        render_agent_task_source(trace, values)
    return caught.value


def everything_about(error):
    """Every textual surface of an exception, chain included."""
    parts = [str(error), repr(error), repr(error.args), repr(vars(error))]
    parts += traceback.format_exception(error)
    link = error
    seen = set()
    while link is not None and id(link) not in seen:
        seen.add(id(link))
        parts += [str(link), repr(link)]
        link = link.__cause__ or link.__context__
    return "\n".join(parts)


# ----------------------------------------------------------------------------- criterion 1


def test_p11_c1_unsupported_action_kind_is_not_a_step_at_all():
    base = clicked(1, "Go")
    with pytest.raises(ValidationError):
        AgentTaskTraceStep.model_validate(base.model_dump() | {"kind": "hover"})


@pytest.mark.xfail(
    reason="QA note N1: an unknown kind (unreachable: the contract Literal is closed) falls into the wait branch",
    strict=True,
)
def test_p11_c1_renderer_never_emits_garbage_for_a_kind_it_does_not_know():
    """Defence in depth: a hand-made step of an unknown kind must not become `waitForTimeout(None)`."""
    good = clicked(1, "Go")
    alien = AgentTaskTraceStep.model_construct(
        step_index=2, operation_id=UUID(int=0x555), kind="hover", locator=None, locator_id=None
    )
    base = trace_of([good])
    fields = {name: getattr(base, name) for name in type(base).model_fields}
    trace = AgentTaskTrace.model_construct(**fields | {"steps": (good, alien)})
    try:
        output = render_agent_task_source(trace)
    except AgentTaskRenderRefused:
        return
    except Exception as error:  # an unplanned crash is also a refusal of sorts, but note it
        pytest.fail(f"unplanned exception type {type(error).__name__}")
    assert "None" not in output.playwright_test_source, output.playwright_test_source


@pytest.mark.parametrize("target", [0, 1])
def test_p11_c1_first_unusable_locator_is_named_even_with_two_bad_steps(target):
    bad = [
        AgentTaskTraceStep.model_construct(
            step_index=idx, operation_id=UUID(int=0x600 + idx), kind="click", locator=None
        )
        for idx in (3, 7)
    ]
    good = clicked(1, "Fine")
    base = trace_of([good])
    fields = {name: getattr(base, name) for name in type(base).model_fields}
    steps = (good, *bad) if target == 0 else (bad[0], good, bad[1])
    trace = AgentTaskTrace.model_construct(**fields | {"steps": steps})
    error = refusal(trace)
    assert (error.code, error.step_index) == ("locator_unavailable", 3)


def test_p11_c1_locator_error_wins_over_value_errors():
    bad = AgentTaskTraceStep.model_construct(
        step_index=2, operation_id=UUID(int=0x700), kind="type", locator=None, text_chars=3
    )
    good = typed(1, "A", 3)
    base = trace_of([good])
    fields = {name: getattr(base, name) for name in type(base).model_fields}
    trace = AgentTaskTrace.model_construct(**fields | {"steps": (good, bad)})
    assert refusal(trace, ["wrong-length-value"]).code == "locator_unavailable"


def test_p11_c1_dom_path_locator_is_never_rendered():
    from test_agent_task_trace import DOM_PATH

    path = VisualLocatorDescriptor(schema_version="v2", strategy="dom_path", value=DOM_PATH)
    bad = AgentTaskTraceStep.model_construct(
        step_index=1, operation_id=UUID(int=0x800), kind="click", locator=path, locator_id=UUID(int=1)
    )
    base = trace_of([clicked(1, "Fine")])
    fields = {name: getattr(base, name) for name in type(base).model_fields}
    trace = AgentTaskTrace.model_construct(**fields | {"steps": (bad,)})
    assert refusal(trace).code == "locator_unavailable"


def test_p11_c1_password_labelled_locator_cannot_exist_in_any_strategy():
    for strategy_kwargs in (
        {"strategy": "role", "role": "textbox", "value": "Password"},
        {"strategy": "label", "value": "Password"},
        {"strategy": "placeholder", "value": "Password"},
    ):
        with pytest.raises(ValueError):
            VisualLocatorDescriptor(**strategy_kwargs)


def test_p11_c1_order_and_every_kind_in_a_long_mixed_trace():
    steps = [
        step(1, "navigate"),
        typed(2, "A", 1),
        step(3, "scroll", delta_y=2000),
        step(4, "wait", duration_ms=100),
        clicked(5, "B"),
        step(6, "scroll", delta_y=-2000),
        typed(7, "C", 2),
        step(8, "wait", duration_ms=10_000),
    ]
    source = render_agent_task_source(trace_of(steps), ["a", "bc"]).playwright_test_source
    markers = [
        "goto(",
        "goto(",
        'fill("a")',
        "wheel(0, 2000)",
        "waitForTimeout(100)",
        ".click()",
        "wheel(0, -2000)",
        'fill("bc")',
        "waitForTimeout(10000)",
    ]
    at = -1
    for marker in markers:
        at = source.index(marker, at + 1)


def test_p11_c1_trace_with_zero_steps_never_reaches_the_renderer():
    with pytest.raises(ValidationError):
        trace_of([])


# ----------------------------------------------------------------------------- criterion 2

POLICY_WORDS = [
    "process",
    "fetch",
    "require",
    "eval",
    "Function",
    "XMLHttpRequest",
    "WebSocket",
    "Worker",
    "Buffer",
    "__dirname",
    "child_process",
    "fs",
    "net",
    "vm",
    "import(1)",
    "import  (x)",
    "export 'evil'",
    "say fetch now",
    "a process b",
]


@pytest.mark.parametrize("value", POLICY_WORDS)
def test_p11_c2_policy_value_is_named_by_step_and_never_echoed(value):
    trace = trace_of([typed(1, "A", 2), typed(2, "B", len(value)), clicked(3, "Go")])
    error = refusal(trace, ["ok", value])
    assert (error.code, error.step_index) == ("input_value_rejected_by_source_policy", 2)
    assert error.operation_id == trace.steps[1].operation_id
    assert value not in everything_about(error)


def test_p11_c2_first_bad_value_is_named_when_two_are_bad():
    trace = trace_of([typed(1, "A", 5), typed(2, "B", 5)])
    assert refusal(trace, ["fetch", "eval("[:5].ljust(5, "x")]).step_index == 1


@pytest.mark.parametrize("value", ["Process", "processing", "prefetch", "FETCH", "refs", "netto"])
def test_p11_c2_words_outside_the_word_boundary_rule_are_accepted(value):
    trace = trace_of([typed(1, "A", len(value))])
    assert value in render_agent_task_source(trace, [value]).playwright_test_source


def test_p11_c2_missing_value_zero_given_names_first_type_step():
    trace = trace_of([clicked(1, "x"), typed(2, "A", 3), typed(3, "B", 3)])
    error = refusal(trace, [])
    assert (error.code, error.step_index) == ("input_value_missing", 2)


def test_p11_c2_extra_values_and_generator_free_input():
    trace = trace_of([typed(1, "A", 3)])
    assert refusal(trace, ["abc", "d"]).code == "input_value_mismatch"
    assert refusal(trace, ["abc", "", ""]).code == "input_value_mismatch"
    # tuple works like a list
    assert render_agent_task_source(trace, ("abc",)).playwright_test_source.count("fill(") == 1


@pytest.mark.parametrize(
    "value,chars",
    [("ab", 3), ("abcd", 3), ("", 3), ("\U0001f600\U0001f600", 4), ("é", 2)],
)
def test_p11_c2_length_mismatch_counts_characters(value, chars):
    trace = trace_of([typed(1, "A", chars)])
    error = refusal(trace, [value])
    assert (error.code, error.step_index) == ("input_value_mismatch", 1)
    assert value not in everything_about(error) or value == ""


def test_p11_c2_decomposed_unicode_has_longer_length_than_composed():
    composed = "ế"  # one char
    decomposed = "ế"  # three chars
    trace = trace_of([typed(1, "A", len(composed))])
    assert render_agent_task_source(trace, [composed])
    assert refusal(trace, [decomposed]).code == "input_value_mismatch"


def test_p11_c2_mismatch_checked_before_policy():
    trace = trace_of([typed(1, "A", 3)])
    assert refusal(trace, ["process"]).code == "input_value_mismatch"


def test_p11_c2_policy_trip_not_from_values_is_source_policy_rejected():
    trace = trace_of([typed(1, "A", 3), clicked(2, "fetch")])
    error = refusal(trace, ["abc"])
    assert error.code == "source_policy_rejected"
    assert error.step_index is None


def test_p11_c2_many_steps_refusal_search_stays_fast():
    n = 300
    trace = trace_of([typed(i, f"F{i}", 4) for i in range(1, n + 1)])
    values = ["abcd"] * (n - 1) + ["eval"]
    started = time.monotonic()
    error = refusal(trace, values)
    assert error.step_index == n
    assert time.monotonic() - started < 20


# ----------------------------------------------------------------------------- criterion 3

CONTROL_CHARS = "".join(chr(c) for c in range(0, 32)) + "\x7f\x80\x9f  ﻿​"
HOSTILE = [
    'a"b',
    "a'b",
    "a\\b",
    "a\\\\b\\",
    '\\"',
    "tab\there",
    "cr\rlf\n",
    CONTROL_CHARS,
    "${process}",  # policy word, replaced below for acceptance tests
    "`tick`${1}",
    "</script><!--",
    "Tiếng Việt có dấu \U0001f600 中文",
    "\ud800",  # lone surrogate
    "x" * 1000,
]
ACCEPTED = [value for value in HOSTILE if "process" not in value]


@pytest.mark.parametrize("value", ACCEPTED, ids=lambda v: repr(v)[:24])
def test_p11_c3_value_literal_is_ascii_json_on_one_line(value):
    trace = trace_of([typed(1, "F", len(value))])
    source = render_agent_task_source(trace, [value]).playwright_test_source
    assert f".fill({json.dumps(value, ensure_ascii=True)});" in source
    assert source.isascii()
    assert "\r" not in source and "\x07" not in source


@pytest.mark.skipif(NODE is None, reason="node missing")
def test_p11_c3_node_reads_back_exactly_the_values_and_texts():
    values = ACCEPTED[:-1]  # 1000-char value stays in the earlier test
    texts = [v for v in values if v and "fetch" not in v][:8]
    steps = [typed(1 + n, f"F{n}", len(v)) for n, v in enumerate(values)]
    trace = trace_of(steps, [("alert", t) for t in texts])
    source = render_agent_task_source(trace, values).playwright_test_source
    fills = re.findall(r"\.fill\((\".*\")\);", source)
    gets = re.findall(r"getByText\((\".*?\")\)\.first", source)
    scratch = tempfile.TemporaryDirectory()
    script = Path(scratch.name) / "read.mjs"
    script.write_text(
        "const f=[" + ",".join(fills) + "];const g=[" + ",".join(gets) + "];"
        "console.log(JSON.stringify({f,g}));",
        encoding="utf-8",
    )
    done = subprocess.run(
        [NODE, str(script)], capture_output=True, text=True, timeout=60, check=False, encoding="utf-8"
    )
    assert done.returncode == 0, done.stderr
    scratch.cleanup()
    back = json.loads(done.stdout)
    assert back["f"] == values
    assert len(back["g"]) == len({*texts})  # duplicates collapse


@pytest.mark.skipif(NODE is None, reason="node missing")
def test_p11_c3_whole_rendered_file_parses():
    values = ACCEPTED[:-1]
    trace = trace_of(
        [typed(1 + n, f"F{n}", len(v)) for n, v in enumerate(values)],
        [("alert", t) for t in values[:6] if t],
    )
    scratch = tempfile.TemporaryDirectory()
    target = Path(scratch.name) / "t.spec.mjs"
    target.write_text(
        render_agent_task_source(trace, values).playwright_test_source, encoding="utf-8"
    )
    done = subprocess.run(
        [NODE, "--check", str(target)], capture_output=True, text=True, timeout=60, check=False
    )
    scratch.cleanup()
    assert done.returncode == 0, done.stderr


def test_p11_c3_candidate_with_every_hostile_text_is_one_line_literal():
    rendered = 0
    for text in ACCEPTED[:-1]:
        try:
            trace = trace_of([clicked(1, "Go")], [("status", text)])
        except ValidationError:
            continue  # the assessment contract itself refuses this text (lone surrogate, control chars)
        rendered += 1
        source = render_agent_task_source(trace).playwright_test_source
        assert f"getByText({literal(text)}).first()" in source
        assert source.isascii()
    assert rendered >= 8


def test_p11_c3_assertion_placement_is_after_last_step_and_before_close():
    trace = trace_of(
        [clicked(1, "A"), step(2, "wait", duration_ms=100)], [("alert", "Saved"), ("status", "Ok")]
    )
    lines = render_agent_task_source(trace).playwright_test_source.splitlines()
    last_action = max(i for i, line in enumerate(lines) if "waitForTimeout" in line)
    asserts = [i for i, line in enumerate(lines) if "getByText" in line]
    assert asserts and min(asserts) > last_action and max(asserts) == len(lines) - 2
    assert lines[-1] == "});"


def test_p11_c3_no_candidates_states_the_gap_in_stop_conditions():
    for items in ((), None):
        output = render_agent_task_source(trace_of([clicked(1, "Go")], items))
        assert "getByText" not in output.playwright_test_source
        joined = " ".join(output.stop_conditions)
        assert "kết quả task chưa được assert" in joined


def test_p11_c3_all_candidates_refused_by_policy_is_treated_as_no_assertion():
    trace = trace_of([clicked(1, "Go")], [("status", "process done"), ("alert", "fetch ok")])
    output = render_agent_task_source(trace)
    assert "getByText" not in output.playwright_test_source
    joined = " ".join(output.stop_conditions)
    assert "2 candidate(s) were left out" in joined
    assert "chưa được assert" in joined


# ----------------------------------------------------------------------------- criterion 4

LINE_GRAMMAR = [
    r"^import \{ test, expect \} from '@playwright/test';$",
    r'^test\("Agent task [0-9a-f-]{36}", async \(\{ page \}\) => \{$',
    r"^  const active = page;$",
    r'^  await active\.goto\("[\x20-\x7e]+"\);$',
    r"^  const target\d+ = active\..+;$",
    r"^  await expect\(target\d+\)\.to(Be(Visible|Enabled))\(\);$",
    r"^  await target\d+\.click\(\);$",
    r'^  await target\d+\.fill\("[\x20-\x7e]*"\);$',
    r"^  await active\.mouse\.wheel\(0, -?\d+\);$",
    r"^  await active\.waitForTimeout\(\d+\);$",
    r'^  await expect\(active\.getByText\(".*"(, \{ exact: true \}\)\.or\(active\.getByLabel\(".*", \{ exact: true \}\))?\)\.first\(\)\)\.toBeVisible\(\);$',
    r"^\}\);$",
]


@pytest.mark.parametrize("make", [login_success, todo_add, search_results])
def test_p11_c4_every_line_matches_the_linear_grammar_and_contract(make):
    trace, values = make()
    output = render_agent_task_source(trace, values)
    source = output.playwright_test_source
    assert source.endswith("});\n") and "\n\n" not in source
    for line in source.splitlines():
        assert any(re.match(rule, line) for rule in LINE_GRAMMAR), line
    for banned in ("if (", "for (", "while", "try", "catch", "=>  ", "page.", "evaluate", "route("):
        assert banned not in source.replace("async ({ page }) =>", "")
    mode = PlaywrightTestSourceMode(
        playwright_test_source=source,
        source_hash=sha256_text(source),
        allowed_origins=[origin_for_url(trace.target_url)],
    )
    assert mode.source_hash == sha256_text(source)
    with pytest.raises(ValidationError):
        PlaywrightTestSourceMode(
            playwright_test_source=source,
            source_hash=sha256_text(source + " "),
            allowed_origins=[origin_for_url(trace.target_url)],
        )


@pytest.mark.parametrize(
    "url,origin",
    [
        ("http://task-target:7300/login", "http://task-target:7300"),
        ("HTTP://Task-Target:7300/a/b?x=1#frag", "http://task-target:7300"),
        ("http://app.test:80/", "http://app.test"),
        ("https://App.Test:443/x", "https://app.test"),
        ("https://app.test", "https://app.test"),
        ("http://[::1]:8080/x", "http://[::1]:8080"),
    ],
)
def test_p11_c4_allowed_origin_is_canonical_for_any_target_url_shape(url, origin):
    trace = trace_of([clicked(1, "Go")], target_url=url)
    output = render_agent_task_source(trace)
    mode = PlaywrightTestSourceMode(
        playwright_test_source=output.playwright_test_source,
        source_hash=sha256_text(output.playwright_test_source),
        allowed_origins=[origin_for_url(url)],
    )
    assert mode.allowed_origins == [origin]
    assert literal(url) in output.playwright_test_source


def test_p11_c4_url_with_quote_or_backslash_is_still_a_json_literal():
    url = 'http://app.test/p?q="a"&b=\\x'
    trace = trace_of([clicked(1, "Go")], target_url=url)
    source = render_agent_task_source(trace).playwright_test_source
    assert f"goto({json.dumps(url)})" in source


def test_p11_c4_each_snapshot_is_distinct_and_stable_across_calls():
    hashes = []
    for make in (login_success, todo_add, search_results):
        trace, values = make()
        first = sha256_text(render_agent_task_source(trace, values).playwright_test_source)
        again = sha256_text(render_agent_task_source(trace, values).playwright_test_source)
        assert first == again
        hashes.append(first)
    assert len(set(hashes)) == 3


# ----------------------------------------------------------------------------- criterion 5


def all_surfaces(output, trace):
    surfaces = {
        "title": output.title,
        "assumptions": json.dumps(output.assumptions, ensure_ascii=False),
        "stop_conditions": json.dumps(output.stop_conditions, ensure_ascii=False),
        "fields_except_source": json.dumps(
            output.model_dump(exclude={"playwright_test_source"}), ensure_ascii=False
        ),
        "repr_except_source": repr(
            output.model_copy(update={"playwright_test_source": ""})
        ),
        "provenance_json": provenance_of(trace).model_dump_json(),
        "provenance_dump": json.dumps(provenance_of(trace).model_dump(mode="json")),
        "trace_json": trace.model_dump_json(),
        "trace_repr": repr(trace),
        "trace_hash": trace.trace_hash,
    }
    return surfaces


@pytest.mark.parametrize("sentinel", [SENTINEL, UNICODE_SENTINEL])
def test_p11_c5_success_path_sentinel_only_in_the_source(sentinel, caplog):
    values = [sentinel, sentinel[::-1]]
    trace = trace_of(
        [typed(1, "A", len(values[0])), typed(2, "B", len(values[1])), clicked(3, "Go")],
        [("status", "Welcome")],
    )
    with caplog.at_level(logging.DEBUG):
        output = render_agent_task_source(trace, values)
    assert json.dumps(sentinel, ensure_ascii=True) in output.playwright_test_source
    for name, text in all_surfaces(output, trace).items():
        for value in values:
            assert value not in text, name
    for record in caplog.records:
        assert all(value not in record.getMessage() for value in values)


@pytest.mark.parametrize("sentinel", [SENTINEL, UNICODE_SENTINEL])
def test_p11_c5_sentinel_in_the_ascii_source_is_the_json_literal(sentinel):
    trace = trace_of([typed(1, "A", len(sentinel))])
    source = render_agent_task_source(trace, [sentinel]).playwright_test_source
    assert source.count(json.dumps(sentinel, ensure_ascii=True)) == 1


@pytest.mark.parametrize(
    "build",
    [
        lambda s: (trace_of([typed(1, "A", len(s) + 1)]), [s]),  # length mismatch
        lambda s: (trace_of([clicked(1, "Go")]), [s]),  # extra
        lambda s: (trace_of([typed(1, "A", len(s) + 8)]), [s + " process"]),  # policy, right length
        lambda s: (trace_of([typed(1, "A", len(s) + 6)]), [s + " fetch"]),
        lambda s: (trace_of([typed(1, "A", len(s)), clicked(2, "process")]), [s]),  # not the value
        lambda s: (trace_of([typed(1, "A", len(s)), typed(2, "B", 3)]), [s]),  # missing
        lambda s: (trace_of([typed(1, "A", len(s))], target_url="ftp://x/"), [s]),  # url
        lambda s: (trace_of([typed(n, f"F{n}", len(s)) for n in range(1, 300)]), [s] * 299),  # limit
    ],
    ids=["mismatch", "extra", "policy-process", "policy-fetch", "not-the-value", "missing", "url", "limit"],
)
@pytest.mark.parametrize("sentinel", [SENTINEL, UNICODE_SENTINEL])
def test_p11_c5_no_refusal_surface_ever_holds_the_sentinel(build, sentinel, caplog):
    trace, values = build(sentinel)
    with caplog.at_level(logging.DEBUG):
        try:
            render_agent_task_source(trace, values)
        except AgentTaskRenderRefused as error:
            text = everything_about(error)
            assert sentinel not in text
            assert sentinel[::-1] not in text
        else:
            # `limit` may legitimately render when 300 short steps fit; then no refusal to scan
            assert len(trace.steps) > 100
    assert all(sentinel not in record.getMessage() for record in caplog.records)


def test_p11_c5_pydantic_validation_text_on_the_output_never_leaks():
    """If the output model rejects something, its message must not embed the value."""
    trace = trace_of([typed(1, "A", 4)])
    output = render_agent_task_source(trace, ["abcd"])
    assert output.assumptions and all(isinstance(note, str) for note in output.assumptions)
    assert "abcd" not in " ".join(output.assumptions + output.stop_conditions + [output.title])


def test_p11_c5_provenance_helper_fields_do_not_carry_values():
    trace = trace_of([typed(1, "A", len(SENTINEL))])
    render_agent_task_source(trace, [SENTINEL])
    dumped = provenance_of(trace).model_dump(mode="json")
    assert SENTINEL not in json.dumps(dumped)
    assert set(dumped["agent_trace_source"]) == {"session_id", "trace_hash"}
    assert dumped["contains_test_values"] is True


# ----------------------------------------------------------------------------- criterion 6

OLD_PROVENANCE = {
    "provider": "codex_cli",
    "model": "gpt-x",
    "prompt_version": "vision-generation-v4",
    "redaction_policy_version": "v1",
    "vision_source": {
        "session_id": str(SESSION),
        "handoff_id": str(UUID(int=5)),
        "handoff_hash": "a" * 64,
    },
    "selected_branch_ids": [str(UUID(int=9))],
    "operation_ids": [str(UUID(int=10))],
}
NEW_KEYS = {"agent_trace_source", "contains_test_values", "owned_test_target", "requested_by"}


def test_p11_c6_old_stored_provenance_validates_and_new_keys_default_to_none():
    old = PlanningProvenance.model_validate(OLD_PROVENANCE)
    assert all(getattr(old, key) is None for key in NEW_KEYS)
    minimal = PlanningProvenance.model_validate(
        {k: OLD_PROVENANCE[k] for k in ("provider", "model", "prompt_version", "redaction_policy_version")}
    )
    assert minimal.vision_source is None


def test_p11_c6_dump_of_old_provenance_differs_only_by_the_four_null_keys():
    dumped = PlanningProvenance.model_validate(OLD_PROVENANCE).model_dump(mode="json")
    assert set(dumped) - set(OLD_PROVENANCE) == NEW_KEYS
    assert all(dumped[key] is None for key in NEW_KEYS)
    assert {k: v for k, v in dumped.items() if k not in NEW_KEYS} == OLD_PROVENANCE
    assert PlanningProvenance.model_dump(
        PlanningProvenance.model_validate(OLD_PROVENANCE), mode="json", exclude_none=True
    ) == OLD_PROVENANCE


def test_p11_c6_row_written_with_null_keys_reads_back_and_equals():
    written = PlanningProvenance.model_validate(OLD_PROVENANCE).model_dump(mode="json")
    again = PlanningProvenance.model_validate(written)
    assert again.model_dump(mode="json") == written


def test_p11_c6_draft_hash_check_unaffected_by_new_keys():
    source = "import { test } from '@playwright/test';\n"
    for extra in ({}, {"contains_test_values": False, "owned_test_target": False}):
        draft = GeneratedTestDraft(
            planning_request_id=UUID(int=1),
            correlation_id=UUID(int=2),
            title="t",
            playwright_test_source=source,
            source_hash=sha256_text(source),
            provenance=PlanningProvenance(
                provider="p", model="m", prompt_version="v", redaction_policy_version="v1", **extra
            ),
        )
        assert draft.source_hash == sha256_text(source)
    with pytest.raises(ValidationError):
        GeneratedTestDraft(
            planning_request_id=UUID(int=1),
            correlation_id=UUID(int=2),
            title="t",
            playwright_test_source=source,
            source_hash="0" * 64,
            provenance=PlanningProvenance(
                provider="p", model="m", prompt_version="v", redaction_policy_version="v1"
            ),
        )


@pytest.mark.parametrize(
    "change",
    [
        {"requested_by": ""},
        {"requested_by": "x" * 201},
        {"contains_test_values": "maybe"},
        {"agent_trace_source": {"session_id": str(SESSION), "trace_hash": "A" * 64}},
        {"agent_trace_source": {"session_id": str(SESSION), "trace_hash": "a" * 63}},
        {"agent_trace_source": {"session_id": "nope", "trace_hash": "a" * 64}},
        {"agent_trace_source": {"session_id": str(SESSION)}},
        {"agent_trace_source": {"session_id": str(SESSION), "trace_hash": "a" * 64, "x": 1}},
        {"unknown_key": 1},
    ],
)
def test_p11_c6_new_fields_are_closed_and_validated(change):
    with pytest.raises(ValidationError):
        PlanningProvenance.model_validate(OLD_PROVENANCE | change)


def test_p11_c6_boundary_values_of_requested_by():
    for text in ("x", "x" * 200, "Nguyễn Văn A"):
        assert PlanningProvenance.model_validate(OLD_PROVENANCE | {"requested_by": text}).requested_by == text


def test_p11_c6_agent_trace_source_is_frozen():
    source = AgentTraceSource(session_id=SESSION, trace_hash="a" * 64)
    with pytest.raises(ValidationError):
        source.trace_hash = "b" * 64


def test_p11_c6_contains_test_values_matches_the_trace():
    with_type, _ = login_success()
    only_clicks = trace_of([clicked(1, "A"), step(2, "scroll", delta_y=5)])
    assert has_test_values(with_type) is True
    assert has_test_values(only_clicks) is False
    assert provenance_of(with_type).contains_test_values is True
    assert provenance_of(only_clicks).contains_test_values is False


def test_p11_c6_planner_provenance_dump_is_what_application_generation_stores():
    """application/generation.py:179 stores `model_dump(mode="json")`: planner-v4 drafts get 4 nulls."""
    fresh = PlanningProvenance(
        provider="codex_cli", model="m", prompt_version="v4", redaction_policy_version="v1"
    )
    stored = fresh.model_dump(mode="json")
    assert {key: stored[key] for key in NEW_KEYS} == {key: None for key in NEW_KEYS}
    json.dumps(stored)  # JSONB-serialisable


# ----------------------------------------------------------------------------- criterion 7


def test_p11_c7_repeat_is_identical_and_inputs_are_untouched():
    trace, values = login_success()
    snapshot_trace, snapshot_values = trace.model_dump_json(), list(values)
    runs = [render_agent_task_source(trace, values) for _ in range(5)]
    assert all(run == runs[0] for run in runs)
    assert {sha256_text(run.playwright_test_source) for run in runs} == {
        sha256_text(runs[0].playwright_test_source)
    }
    assert trace.model_dump_json() == snapshot_trace and values == snapshot_values


def test_p11_c7_output_has_no_clock_or_random_content():
    trace, values = todo_add()
    source = render_agent_task_source(trace, values).playwright_test_source
    assert not re.search(r"\d{4}-\d{2}-\d{2}T", source)
    assert str(SESSION) in source  # only the trace session id identifies the test
    assert str(PROJECT) not in source and "tenant-a" not in source


@pytest.mark.parametrize("seed", ["0", "1", "random"])
def test_p11_c7_same_hash_in_separate_processes_whatever_the_hash_seed(seed):
    code = (
        "from test_agent_task_renderer import login_success, todo_add, search_results\n"
        "from application.agent_task_renderer import render_agent_task_source as r\n"
        "from auto_at.contracts.execution import sha256_text as h\n"
        "print(','.join(h(r(*[f() for f in (m,)][0]).playwright_test_source) for m in (login_success, todo_add, search_results)))\n"
    )
    code = (
        "from test_agent_task_renderer import login_success, todo_add, search_results\n"
        "from application.agent_task_renderer import render_agent_task_source as r\n"
        "from auto_at.contracts.execution import sha256_text as h\n"
        "out=[]\n"
        "for make in (login_success, todo_add, search_results):\n"
        "    t, v = make()\n"
        "    out.append(h(r(t, v).playwright_test_source))\n"
        "print(','.join(out))\n"
    )
    env = os.environ | {"PYTHONPATH": os.pathsep.join(p for p in sys.path if p), "PYTHONHASHSEED": seed}
    done = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env=env,
        cwd=str(Path(__file__).parent),
    )
    assert done.returncode == 0, done.stderr[-2000:]
    expected = []
    for make in (login_success, todo_add, search_results):
        trace, values = make()
        expected.append(sha256_text(render_agent_task_source(trace, values).playwright_test_source))
    assert done.stdout.strip().splitlines()[-1] == ",".join(expected)


# ----------------------------------------------------------------------------- misc / boundary


def test_p11_misc_title_and_notes_are_fixed_vocabulary():
    trace, values = login_success()
    output = render_agent_task_source(trace, values)
    assert output.title == f"Agent task test from session {SESSION}"
    assert len(output.title) <= 200
    assert any("2 typed value(s)" in note for note in output.assumptions)


def test_p11_misc_page_text_with_the_role_text_of_a_password_is_just_text():
    """Q4: only locators are policed; observed page text containing `Password` is an assertion."""
    trace = trace_of([clicked(1, "Go")], [("status", "Password changed")])
    assert "Password changed" in render_agent_task_source(trace).playwright_test_source


def test_p11_misc_default_url_constant_is_a_plain_http_origin():
    assert origin_for_url(URL) == "http://task-target:7300"
    assert role("button", "x").strategy == "role"
