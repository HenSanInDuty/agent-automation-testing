"""QA phase 16: independent checks that complement the developer e2e suite.

Pure and file-based (no database, no model, no stack). Three groups:
- F5/F4 characterisation of the renderer, so a later fix flips a test instead of going unnoticed;
- the r2 run summary, when the gitignored artifact directory is present, against the plan's numbers;
- the plan's phase 16 criteria keep pointing at the same threshold the stability harness uses.
"""

# ruff: noqa: E501
import json
import re
from pathlib import Path

import pytest
from application.agent_task_renderer import render_agent_task_source
from auto_at.contracts.vision import VisualLocatorDescriptor
from test_agent_task_renderer import clicked, step, trace_of, typed

ROOT = Path(__file__).resolve().parents[1]
R2 = ROOT / ".pytest-artifacts" / "task-draft-e2e" / "r2"


# ------------------------------------------------------------------ F5: assertion text from the session


def _todo_trace(item_text, *, flagged=False):
    """`flagged` is what a session recorded after phase 17 carries for a candidate holding typed text."""
    return trace_of(
        [typed(1, "Việc mới", 12), clicked(1, "Thêm")],
        [("status", item_text, True) if flagged else ("status", item_text)],
        target_url="http://task-target:7300/todos",
    )


def test_f5_01_a_candidate_holding_the_session_typed_text_is_not_asserted_when_the_requester_value_differs():
    """F5 fixed in phase 17: the session marks a candidate that holds what the agent typed
    (`derived_from_typed`), so the renderer leaves it out and says so instead of asserting text the
    requester's value will not produce. Before the fix the old text was asserted and the run failed
    (r2 marker: draft 81267bb8, run ea7cbb7a).
    """
    marker = "ZQ4471-todo1"  # 12 chars, same length as the agent's value, as the route requires
    output = render_agent_task_source(_todo_trace("hoàn thành: Viết báo cáo", flagged=True), [marker])
    source = output.playwright_test_source
    assert f'fill("{marker}")' in source
    assert "hoàn thành" not in source and "ho\\u00e0n th\\u00e0nh" not in source  # old text not asserted
    asserted = [line for line in source.splitlines() if "toBeVisible" in line and "getByText" in line]
    assert asserted == []
    assert any("value typed in the session" in note for note in output.stop_conditions)
    assert any("not asserted" in note for note in output.stop_conditions)  # outcome gap stated
    assert not any(marker in note or "Viết" in note for note in output.stop_conditions + output.assumptions)


def test_f5_04_a_session_stored_before_phase_17_still_asserts_its_text_known_limit():
    """The flag cannot be added afterwards: the typed value was never stored, so a session recorded
    before phase 17 keeps the old behaviour (assertion kept, `failed` if the requester types another value).
    """
    output = render_agent_task_source(_todo_trace("hoàn thành: Viết báo cáo"), ["ZQ4471-todo1"])
    source = output.playwright_test_source
    assert "hoàn thành: Vi" in source or "ho\\u00e0n th\\u00e0nh: Vi" in source


def test_f5_02_same_value_as_the_session_keeps_the_assertion_valid():
    """Control for F5: when the requester types what the agent typed, the same assertion text is right."""
    output = render_agent_task_source(_todo_trace("Viết báo cáo"), ["Viết báo cáo"])
    assert output.playwright_test_source.count("Vi\\u1ebft b\\u00e1o c\\u00e1o") >= 2  # fill + assertion


def test_f5_03_rendering_is_deterministic_for_a_given_value():
    trace = _todo_trace("hoàn thành: Viết báo cáo")
    first = render_agent_task_source(trace, ["Viết báo cáo"])
    second = render_agent_task_source(trace, ["Viết báo cáo"])
    assert first.playwright_test_source == second.playwright_test_source


# ------------------------------------------------------------------ F4: search-results asserts controls only


def test_f4_01_known_debt_control_name_candidates_assert_the_controls_not_the_search_result():
    """F4 is NOT fixed in phase 17 (escalated): the result list never reaches the controller. The
    worker reads only alert/status/heading/paragraph as page text (`workers/playwright/src/vision-dom.ts:46-48`)
    and the fixture renders results as `<li>` (`benchmarks/targets/task-ui/server.mjs:176`), so
    "Balo laptop" cannot become a candidate and the quote is dropped. The renderer is correct here.
    """
    label = VisualLocatorDescriptor(strategy="label", value="Từ khoá")
    trace = trace_of(
        [step(1, "type", locator=label, text_chars=4), clicked(1, "Tìm")],
        [("control_name", "Từ khoá"), ("control_name", "Tìm")],  # what r2 `search-results` produced
        target_url="http://task-target:7300/search",
    )
    source = render_agent_task_source(trace, ["balo"]).playwright_test_source
    asserted = [line for line in source.splitlines() if "getByText" in line and "toBeVisible" in line]
    assert len(asserted) == 2
    assert all("getByLabel" in line for line in asserted)  # controls: they exist before the search too
    assert "Balo" not in source and "laptop" not in source


def test_f4_02_even_if_the_result_were_observed_a_result_holding_the_typed_term_is_not_asserted():
    """Why the F4 fix is more than the extractor: once the list is observed, "Balo laptop - 310.000 đ"
    holds the typed term "balo", so F5 leaves it out (another term gives other results).
    """
    label = VisualLocatorDescriptor(strategy="label", value="Từ khoá")
    trace = trace_of(
        [step(1, "type", locator=label, text_chars=4), clicked(1, "Tìm")],
        [("control_name", "Tìm"), ("paragraph", "Balo laptop - 310.000 đ", True)],
        target_url="http://task-target:7300/search",
    )
    output = render_agent_task_source(trace, ["ao  "])
    assert "Balo" not in output.playwright_test_source
    assert any("value typed in the session" in note for note in output.stop_conditions)


# ------------------------------------------------------------------ r2 artefacts (skipped when absent)

needs_r2 = pytest.mark.skipif(not (R2 / "summary.json").exists(), reason="r2 run artefacts absent")


@needs_r2
def test_r2_01_reruns_meet_the_plan_threshold():
    summary = json.loads((R2 / "summary.json").read_text(encoding="utf-8"))
    for name in ("pos-login", "pos-todo", "pos-search"):
        rerun = summary["reruns"][name]
        assert rerun["runs"] >= 5
        assert rerun["passed"] / rerun["runs"] >= 0.9
        assert set(rerun["statuses"]) == {"passed"}


@needs_r2
def test_r2_02_state_and_summary_agree_and_no_run_errored():
    state = json.loads((R2 / "state.json").read_text(encoding="utf-8"))
    summary = json.loads((R2 / "summary.json").read_text(encoding="utf-8"))
    for name in ("pos-login", "pos-todo", "pos-search"):
        reruns = [r for r in state["runs"][name] if r["kind"] == "rerun"]
        assert len(reruns) == summary["reruns"][name]["runs"]
        assert all(r["via"] == "POST /api/v1/runs" for r in reruns)  # F1 path, not worker /execute
    statuses = {r["status"] for runs in state["runs"].values() for r in runs}
    assert statuses <= {"passed", "failed"}  # no errored / queued left over in r2


@needs_r2
def test_r2_03_events_log_carries_no_sample_value():
    text = (R2 / "events.jsonl").read_text(encoding="utf-8")
    for value in ("Demo1234", "Viết báo cáo", "Vi\\u1ebft", "ZQ4471"):
        assert value not in text


# ------------------------------------------------------------------ plan threshold stays tied to the harness


def test_p16_01_phase_doc_threshold_matches_the_stability_harness():
    harness = (ROOT / "benchmark" / "task_ui" / "stability.py").read_text(encoding="utf-8")
    assert re.search(r"0\.9\b", harness), "the 90% stability threshold must stay in the harness"
