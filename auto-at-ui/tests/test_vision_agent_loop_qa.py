"""QA phase 4: gap-filling tests for the agent loop (renderer, safety, budget, fence).

Reuses the developer fakes (`FakeWorker`, `FakeExchange`, `run_agent`); only adds cases.
"""

import unicodedata
from types import SimpleNamespace
from uuid import uuid4

import pytest
import test_vision_agent_loop as base
from application.vision_agent_loop import render_snapshot, stop_cause
from auto_at.contracts.codex_bridge import AgentAction, CodexNeedScreenshot
from domain.vision_agent_safety import BLOCKED_ACTION_TERMS, check_action
from infrastructure.persistence.models import VisualExplorationSessionModel
from sqlalchemy import update
from test_codex_candidate_service import codex_policy
from test_vision_agent_loop import (
    DONE,
    FakeWorker,
    Outcome,
    bound_for,
    click,
    dom_element,
    run_agent,
    step,
    typed,
    wait,
)

pytest_plugins = ["vision_trace_fixtures"]


# --------------------------------------------------------------------------- pure: stop_cause

def result(status="completed", url="unchanged", before="p", after="p", code="observed", fp="f"):
    return SimpleNamespace(
        operation=SimpleNamespace(status=status, url_change=url, before_page_id=before,
                                  after_page_id=after, outcome_code=code),
        state_fingerprint=fp)


@pytest.mark.parametrize(("case", "expected"), [
    (result(), None),
    (result(url="changed"), "url_change"),
    (result(after="other"), "popup"),
    (result(code="download_started"), "download"),
    (result(fp="g"), "state_changed"),
    (result(status="failed"), "operation_failed"),
    (result(status="rejected"), "operation_rejected"),
    (result(status="unknown"), "operation_unknown"),
])
def test_stop_cause_table(case, expected):
    assert stop_cause(case, "f") == expected


def test_stop_cause_tolerates_a_missing_result_fingerprint():
    assert stop_cause(result(fp=None), "f") is None


# --------------------------------------------------------------------------- pure: renderer

@pytest.mark.parametrize("cap", [300, 500, 1000, 4000, 12000])
def test_renderer_never_exceeds_the_cap_and_marker_matches_what_was_cut(cap):
    bound = bound_for([dom_element(i, f"Mục {i:03d} " + "ệ" * 110) for i in range(1, 101)],
                      skipped=200)
    rendered = render_snapshot(bound, 12, cap, "https://app.test/x")
    assert len(rendered.text) <= cap
    shown = len(rendered.refs)
    assert set(rendered.refs) == {f"12:{n}" for n in range(1, shown + 1)}
    if shown < 100:
        assert f"[refs 12:{shown + 1}-12:100 trimmed]" in rendered.text
        assert "200 control ngoài snapshot" in rendered.text
        # Refs that were cut are not in the map, so they resolve to stale_ref later.
        assert f"12:{shown + 1}" not in rendered.refs
    else:
        assert "trimmed" not in rendered.text


def test_renderer_cap_boundary_is_exact():
    bound = bound_for([dom_element(i, "Open") for i in range(1, 6)])
    full = render_snapshot(bound, 1, 10_000, "https://app.test/")
    assert full.trimmed is None
    exact = render_snapshot(bound, 1, len(full.text), "https://app.test/")
    assert exact.text == full.text and exact.trimmed is None
    one_short = render_snapshot(bound, 1, len(full.text) - 1, "https://app.test/")
    assert one_short.trimmed is not None and len(one_short.text) <= len(full.text) - 1


def test_renderer_without_skipped_controls_has_no_outside_snapshot_line():
    rendered = render_snapshot(bound_for([dom_element(1, "A")]), 1, 1000)
    assert "ngoài snapshot" not in rendered.text


# --------------------------------------------------------------------------- pure: safety

def element(name, **extra):
    return dom_element(1, name, **extra)


def test_blocked_terms_fit_the_contract_and_accented_forms_have_unaccented_twins():
    assert 0 < len(BLOCKED_ACTION_TERMS) <= 40
    assert len(set(BLOCKED_ACTION_TERMS)) == len(BLOCKED_ACTION_TERMS)
    assert not {"đăng ký", "dang ky", "nạp thẻ", "nap the"} & set(BLOCKED_ACTION_TERMS)
    for term in BLOCKED_ACTION_TERMS:
        plain = "".join(c for c in unicodedata.normalize("NFD", term.replace("đ", "d"))
                        if not unicodedata.combining(c))
        # The worker does not strip diacritics: "gửi" is the one reviewed exception ("gui di").
        if plain != term and term != "gửi":
            assert plain in BLOCKED_ACTION_TERMS, term


@pytest.mark.parametrize("term", BLOCKED_ACTION_TERMS)
@pytest.mark.parametrize("form", ["NFC", "NFD", "upper"])
def test_every_blocked_term_blocks_a_click_in_every_spelling(term, form):
    name = {"NFC": f"Nút {term} ngay", "NFD": unicodedata.normalize("NFD", f"Nút {term}"),
            "upper": f"NÚT {term.upper()}"}[form]
    decision = check_action(click("1:1"), element(name), "https://app.test", ["https://app.test"])
    assert decision.allowed is False and decision.reason == "sensitive_action_blocked"


@pytest.mark.parametrize("name", ["Đăng ký", "ĐĂNG KÝ", "dang ky", "Nạp thẻ", "NẠP THẺ", "nap the",
                                  "Chi tiết", "Mongchiton"])
def test_benchmark_actions_are_not_blocked(name):
    assert check_action(click("1:1"), element(name), "https://app.test", ["https://app.test"]).allowed


def test_a_type_of_secret_like_text_is_blocked_before_the_worker():
    for text in ("a@b.com", "1234567", " lead", "password=hunter2", "x\ry"):
        decision = check_action(typed("1:1", text), element("Name", editable=True),
                                "https://app.test", ["https://app.test"])
        assert decision.allowed is False, text


# --------------------------------------------------------------------------- loop: safety

WORKER_ELEMENTS = [
    ("button", "Xoa tai khoan", None, True, False),
    ("button", "XÓA", None, True, False),
    ("button", unicodedata.normalize("NFD", "Xóa"), None, True, False),
    ("button", "THANH TOÁN", None, True, False),
    ("button", "Thanh toan", None, True, False),
    ("button", "Đặt hàng", None, True, False),
    ("button", "Log Out", None, True, False),
    ("button", "Continue", "submit", True, False),
    ("button", "Clear", "reset", True, False),
    ("button", "Nạp thẻ", None, True, False),
    ("button", "Đăng ký", None, True, False),
    ("button", "Chi tiết", None, True, False),
]


def test_loop_blocks_sensitive_controls_in_both_spellings_with_zero_worker_requests(
    disposable_database, monkeypatch,
):
    worker = FakeWorker(None, None, elements=WORKER_ELEMENTS)
    refs = [f"1:{i}" for i in range(1, 10)]
    run = run_agent(disposable_database, monkeypatch,
                    [step(*[click(ref) for ref in refs]), DONE], worker=worker)
    assert [a["skipped_reason"] for a in run.steps[0].actions] == ["sensitive_action_blocked"] * 9
    assert run.worker.explore_kinds() == []
    assert run.steps[0].operation_ids == []
    # The model is told why, so it can change course on the next step.
    assert "sensitive_action_blocked" in run.exchange.calls[1]["agent_context"].history[0]


def test_loop_runs_the_benchmark_actions_that_look_close_to_blocked_ones(
    disposable_database, monkeypatch,
):
    worker = FakeWorker(None, None, elements=WORKER_ELEMENTS)
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:10")), step(click("2:11")), step(click("3:12")), DONE],
                    worker=worker)
    assert run.worker.explore_kinds() == ["click"] * 3
    assert all(a.get("skipped_reason") is None for s in run.steps for a in s.actions)


def test_loop_blocks_secret_text_and_never_logs_the_typed_value(disposable_database, monkeypatch):
    run = run_agent(disposable_database, monkeypatch,
                    [step(typed("1:2", "mail@example.com"), typed("1:2", "ok value")), DONE])
    assert [a.get("skipped_reason") for a in run.steps[0].actions] == [
        "sensitive_action_blocked", None]
    assert run.worker.explore_kinds() == ["type"]
    assert "mail@example.com" not in str([s.actions for s in run.steps])
    assert "ok value" not in str([s.actions for s in run.steps])


def test_a_planner_session_is_refused_by_the_agent_processor_without_touching_the_worker(
    disposable_database, monkeypatch,
):
    def make_planner(seeded):
        with seeded.factory.begin() as db:
            db.execute(update(VisualExplorationSessionModel).where(
                VisualExplorationSessionModel.id == seeded.scope.session_id,
            ).values(exploration_engine="planner"))

    run = run_agent(disposable_database, monkeypatch, [DONE], on_seed=make_planner)
    assert isinstance(run.error, ValueError) and run.worker.calls == []
    assert run.exchange.calls == [] and run.steps == []


def test_a_session_with_no_engine_column_value_defaults_to_the_planner():
    column = VisualExplorationSessionModel.__table__.c.exploration_engine
    assert column.default.arg == "planner" and column.server_default.arg == "planner"
    assert column.nullable is False


# --------------------------------------------------------------------------- loop: snapshot cap

def test_loop_caps_the_snapshot_and_a_trimmed_ref_is_stale_without_a_worker_call(
    disposable_database, monkeypatch,
):
    original = base.bound_for
    monkeypatch.setattr(base, "bound_for",
                        lambda elements, *, skipped=0, request=None: original(
                            elements, skipped=150, request=request))
    elements = [("button", f"N{i:03d} " + "x" * 100, None, True, False) for i in range(1, 101)]
    worker = FakeWorker(None, None, elements=elements)
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:100"), click("1:1")), DONE], worker=worker, chars=4000)
    snapshot = run.exchange.calls[0]["agent_context"].snapshot
    assert len(snapshot) <= 4000
    assert "150 control ngoài snapshot" in snapshot and "trimmed]" in snapshot
    assert [a.get("skipped_reason") for a in run.steps[0].actions] == ["stale_ref", None]
    assert run.worker.explore_kinds() == ["click"]


# --------------------------------------------------------------------------- loop: budget

def test_a_policy_above_twenty_calls_is_rejected_by_the_contract_and_twenty_is_the_ceiling(
    disposable_database, monkeypatch,
):
    with pytest.raises(ValueError):
        codex_policy(max_steps=21, max_requests_per_minute=10_000)
    run = run_agent(disposable_database, monkeypatch, [step(wait())],
                    policy=codex_policy(max_steps=20, max_requests_per_minute=10_000))
    assert len(run.exchange.calls) == 20  # call 20 runs, call 21 never does
    assert run.record.safe_failure_reason == "agent_step_limit"


def test_retry_and_screenshot_calls_share_one_ceiling(disposable_database, monkeypatch):
    policy = codex_policy(max_steps=4, max_requests_per_minute=10_000,
                          raw_screenshot_transfer_accepted=True,
                          raw_screenshot_transfer_provider="codex_cli")
    outputs = ["bridge_malformed_output", CodexNeedScreenshot(reason="visual_target"),
               step(wait()), step(wait()), step(wait())]
    run = run_agent(disposable_database, monkeypatch, outputs, policy=policy)
    assert len(run.exchange.calls) == 4  # malformed, need_screenshot, image answer, next step
    assert [c["image"] is not None for c in run.exchange.calls] == [False, False, True, False]
    assert len(run.steps) == 2 and run.record.safe_failure_reason == "agent_step_limit"


def test_need_screenshot_on_the_last_allowed_call_ends_at_the_limit(
    disposable_database, monkeypatch,
):
    policy = codex_policy(max_steps=1, max_requests_per_minute=10_000,
                          raw_screenshot_transfer_accepted=True,
                          raw_screenshot_transfer_provider="codex_cli")
    run = run_agent(disposable_database, monkeypatch,
                    [CodexNeedScreenshot(reason="visual_target"), DONE], policy=policy)
    assert len(run.exchange.calls) == 1 and run.exchange.calls[0]["image"] is None
    assert run.record.safe_failure_reason == "agent_step_limit"


def test_every_agent_step_has_a_distinct_job_and_monotonic_sequence(
    disposable_database, monkeypatch,
):
    run = run_agent(disposable_database, monkeypatch, [step(wait()), step(wait()), DONE])
    assert [c["sequence"] for c in run.exchange.calls] == [1, 2, 3]
    assert [s.step_index for s in run.steps] == [1, 2, 3]
    assert len({s.job_id for s in run.steps}) == 3


# --------------------------------------------------------------------------- loop: lease

def test_lease_lost_while_an_action_runs_stops_and_never_writes_that_step(
    disposable_database, monkeypatch,
):
    holder = {}
    worker = FakeWorker(None, None)

    def plan(request, n):
        if n == 1:
            with holder["seeded"].factory.begin() as db:
                db.execute(update(VisualExplorationSessionModel).where(
                    VisualExplorationSessionModel.id == holder["seeded"].scope.session_id,
                ).values(lease_owner=uuid4()))
        return Outcome()

    worker.plan = plan
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1"), click("1:1")), step(wait()), DONE], worker=worker,
                    on_seed=lambda seeded: holder.update(seeded=seeded))
    assert isinstance(run.error, ValueError)
    assert run.steps == [] and len(run.exchange.calls) == 1
    assert run.worker.calls.count("prepare") <= 2  # setup + at most the in-flight click


def test_lease_lost_before_the_next_observation_never_writes_another_step(
    disposable_database, monkeypatch,
):
    holder = {}
    worker = FakeWorker(None, None)
    original = worker.observe_dom

    async def observe(request):
        if len(worker.observes) == 1:
            with holder["seeded"].factory.begin() as db:
                db.execute(update(VisualExplorationSessionModel).where(
                    VisualExplorationSessionModel.id == holder["seeded"].scope.session_id,
                ).values(lease_owner=uuid4()))
        return await original(request)

    worker.observe_dom = observe
    run = run_agent(disposable_database, monkeypatch, [step(wait()), step(wait()), DONE],
                    worker=worker, on_seed=lambda seeded: holder.update(seeded=seeded))
    assert isinstance(run.error, ValueError)
    assert [s.step_index for s in run.steps] == [1]  # the fenced write of step 2 is refused


# --------------------------------------------------------------------------- loop: batch

def test_type_then_type_then_click_on_one_form_all_run(disposable_database, monkeypatch):
    run = run_agent(disposable_database, monkeypatch,
                    [step(typed("1:2", "alpha"), typed("1:3", "beta"), click("1:1")), DONE])
    assert run.worker.explore_kinds() == ["type", "type", "click"]
    assert run.steps[0].stop_reason is None


def test_a_popup_blocks_the_rest_of_the_batch_including_close_popup(
    disposable_database, monkeypatch,
):
    worker = FakeWorker(None, None)
    worker.plan = lambda request, n: Outcome(popup=True, page_url="https://app.test/p") if n == 1 \
        else Outcome()
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1"), AgentAction(kind="close_popup")), DONE], worker=worker)
    assert run.worker.explore_kinds() == ["click"]
    assert run.steps[0].actions[1]["skipped_reason"] == "batch_stopped"
    assert run.steps[0].actions[1]["stop_cause"] == "popup"
