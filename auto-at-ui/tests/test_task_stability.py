"""Task suite and stability harness: schema, credential guard, summary math. No DB, no network."""

import argparse
import json
import sys
from pathlib import Path

import pytest
from auto_at.contracts.generation import redact_generation_request

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "benchmark/task_ui"))
sys.path.insert(0, str(ROOT / "scripts"))
import run_task_stability  # noqa: E402
import stability  # noqa: E402

SUITE_PATH = ROOT / "benchmarks/task-ui/tasks.v1.json"
SUITE = json.loads(SUITE_PATH.read_text("utf-8"))


def task(task_id="t", expected="achieved"):
    return {"id": task_id, "path": "/", "task": "Mở trang", "expected_status": expected}


def run(task_id, number, state="completed", status="achieved", reason=None):
    return {"task_id": task_id, "run": number, "state": state, "assessment_status": status,
            "safe_failure_reason": reason}


def test_suite_file_is_valid_with_unique_ids_and_both_outcomes():
    tasks = stability.load_suite(SUITE_PATH)
    ids = [item["id"] for item in tasks]
    assert len(ids) == len(set(ids)) >= 8
    expected = {item["expected_status"] for item in tasks}
    assert expected == {"achieved", "not_achieved"}
    assert {item["id"] for item in tasks if item["path"] == "/broken"} == {
        item["id"] for item in tasks if item["expected_status"] == "not_achieved"}


@pytest.mark.parametrize("item", SUITE["tasks"], ids=lambda item: item["id"])
def test_every_task_passes_the_credential_guard_unchanged(item):
    assert redact_generation_request(item["task"]) == item["task"]


def test_login_task_carries_the_test_account_and_still_passes_the_guard():
    login = next(item for item in SUITE["tasks"] if item["id"] == "login-success")
    assert "demo" in login["task"] and "Demo1234" in login["task"]
    # The English keyword form is what the guard rejects; the suite must not use it.
    assert redact_generation_request("password: Demo1234") != "password: Demo1234"


@pytest.mark.parametrize("mutation, message", [
    (lambda s: s.update(schema_version="v0"), "schema_version"),
    (lambda s: s.update(tasks=[]), "non-empty"),
    (lambda s: s["tasks"].append(dict(s["tasks"][0])), "duplicate"),
    (lambda s: s["tasks"][0].update(expected_status="passed"), "expected_status"),
    (lambda s: s["tasks"][0].update(path="login"), "path"),
    (lambda s: s["tasks"][0].update(path="//evil.test"), "path"),
    (lambda s: s["tasks"][0].update(id="Bad Id"), "invalid id"),
    (lambda s: s["tasks"][0].update(task="  "), "task text"),
    (lambda s: s["tasks"][0].pop("task"), "keys"),
])
def test_invalid_suites_are_rejected(mutation, message):
    suite = json.loads(json.dumps(SUITE))
    mutation(suite)
    with pytest.raises(ValueError, match=message):
        stability.validate_suite(suite)


def test_select_tasks_keeps_suite_order_and_rejects_unknown_ids():
    tasks = [task("a"), task("b"), task("c")]
    assert [t["id"] for t in stability.select_tasks(tasks, ["c", "a"])] == ["a", "c"]
    assert len(stability.select_tasks(tasks, [])) == 3
    with pytest.raises(ValueError, match="unknown"):
        stability.select_tasks(tasks, ["zzz"])


def test_plan_skips_recorded_pairs_and_is_task_major():
    tasks = [task("a"), task("b")]
    pending = stability.plan(tasks, 2, {("a", 1), ("b", 2)})
    assert [(t["id"], n) for t, n in pending] == [("a", 2), ("b", 1)]
    with pytest.raises(ValueError):
        stability.plan(tasks, 0, set())


def test_resumability_keys_come_from_recorded_lines_and_ignore_a_torn_last_line():
    text = "\n".join([json.dumps(run("a", 1)), json.dumps(run("b", 3)), '{"task_id": "a", "ru'])
    runs = stability.parse_runs(text)
    assert stability.recorded_keys(runs) == {("a", 1), ("b", 3)}


def test_idempotency_key_is_stable_per_pair_and_distinct_across_batches():
    assert stability.idempotency_key("b1", "a", 2) == stability.idempotency_key("b1", "a", 2)
    assert stability.idempotency_key("b1", "a", 2) != stability.idempotency_key("b2", "a", 2)
    assert stability.idempotency_key("b1", "a", 2) != stability.idempotency_key("b1", "a", 3)


def test_run_record_reads_assessment_and_failure_fields():
    session = {"id": "s1", "state": "completed", "safe_failure_reason": None,
               "task_assessment": {"status": "blocked", "stop_reason": "agent_stopped",
                                   "source": "controller", "facts": {"actions_completed": 2}}}
    record = stability.run_record(task("a", "blocked"), 2, session, 12.34, recorded_at="now")
    assert record["assessment_status"] == "blocked"
    assert record["stop_reason"] == "agent_stopped" and record["duration_s"] == 12.3
    unavailable = stability.run_record(
        task("a"), 1, {"id": "s2", "state": "unavailable", "safe_failure_reason": "bridge_offline"},
        1, recorded_at="now")
    assert unavailable["assessment_status"] is None
    assert unavailable["safe_failure_reason"] == "bridge_offline"


def test_summary_math_for_one_task_with_a_disagreeing_and_a_failed_run():
    tasks = [task("a", "achieved")]
    runs = [run("a", 1), run("a", 2), run("a", 3, status="not_achieved"),
            run("a", 4, state="unavailable", status=None, reason="bridge_offline")]
    summary = stability.summarise(tasks, runs)
    stats = summary["tasks"][0]
    assert stats["runs"] == 4 and stats["completed"] == 3
    assert stats["completed_rate"] == 0.75
    assert stats["modal_status"] == "achieved" and stats["agreement_rate"] == round(2 / 3, 4)
    assert stats["expected_match_rate"] == 0.5
    assert stats["unavailable_reasons"] == {"bridge_offline": 1}
    assert summary["overall"]["stable"] is False


def test_modal_tie_is_broken_alphabetically_and_not_equal_to_expected():
    stats = stability.summarise([task("a", "blocked")],
                                [run("a", 1, status="not_achieved"), run("a", 2)])["tasks"][0]
    assert stats["modal_status"] == "achieved" and stats["agreement_rate"] == 0.5
    assert stats["expected_match_rate"] == 0.0


def test_stable_verdict_needs_both_rates_at_least_ninety_percent():
    tasks = [task("a"), task("b", "not_achieved")]
    runs = [run("a", n) for n in range(1, 11)] + [run("b", n, status="not_achieved")
                                                  for n in range(1, 11)]
    assert stability.summarise(tasks, runs)["overall"]["stable"] is True
    # 18/20 completed = 0.9 is still stable; 17/20 is not.
    one_down = [dict(runs[0], state="unavailable", assessment_status=None)] + runs[1:]
    assert stability.summarise(tasks, one_down)["overall"]["stable"] is True
    two_down = [dict(r, state="unavailable", assessment_status=None) for r in runs[:3]] + runs[3:]
    assert stability.summarise(tasks, two_down)["overall"]["stable"] is False
    disagree = runs[:-2] + [run("b", 9, status="achieved"), run("b", 10, status="achieved")]
    assert stability.summarise(tasks, disagree)["overall"]["agreement_rate"] == 0.9
    assert stability.summarise(tasks, disagree)["overall"]["stable"] is True
    disagree3 = runs[:-3] + [run("b", n, status="achieved") for n in (8, 9, 10)]
    assert stability.summarise(tasks, disagree3)["overall"]["stable"] is False


def test_no_runs_is_not_stable_and_has_no_rates():
    summary = stability.summarise([task("a")], [])
    assert summary["overall"]["completed_rate"] is None and summary["overall"]["stable"] is False


def test_duplicate_run_lines_keep_the_latest():
    runs = [run("a", 1, state="unavailable", status=None, reason="x"), run("a", 1)]
    assert stability.summarise([task("a")], runs)["tasks"][0]["completed"] == 1


def test_markdown_names_verdict_tasks_and_unavailable_reasons():
    runs = [run("a", 1), run("a", 2, state="unavailable", status=None, reason="bridge_offline")]
    markdown = stability.render_markdown(stability.summarise([task("a")], runs))
    assert "NOT STABLE" in markdown and "| a | achieved | 2 |" in markdown
    assert "a: bridge_offline x1" in markdown
    clean = stability.render_markdown(stability.summarise([task("a")], [run("a", 1)]))
    assert "Verdict: **STABLE**" in clean and "- none" in clean


def test_reset_command_targets_the_fixture_container_without_a_shell():
    argv = stability.reset_command("auto-at-ui-task-target-1")
    assert argv[:3] == ["docker", "exec", "auto-at-ui-task-target-1"]
    assert argv[-1] == "http://127.0.0.1:7300/__reset"


def test_target_url_joins_without_double_slash():
    assert stability.target_url("http://task-target:7300/", {"path": "/login"}) == (
        "http://task-target:7300/login")


def test_poll_interval_below_five_seconds_is_rejected_by_the_cli():
    with pytest.raises(argparse.ArgumentTypeError):
        run_task_stability.poll_seconds("1")
    assert run_task_stability.poll_seconds("5") == 5.0
    parsed = run_task_stability.build_parser().parse_args(
        ["run", "--project", "p", "--base-url", "http://task-target:7300", "--out", "x"])
    assert parsed.poll == 5.0 and parsed.repeat == 3


class FakeClient:
    def __init__(self, states):
        self.states = list(states)

    def get(self, path):
        state = self.states.pop(0)

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {"id": "s", "state": state}

        return Response()


def test_wait_terminal_returns_on_terminal_state_and_times_out_otherwise():
    ticks = iter(range(0, 1000, 5))
    session, done = run_task_stability.wait_terminal(
        FakeClient(["queued", "running", "completed"]), "s", poll=5, timeout=100,
        sleep=lambda _: None, clock=lambda: next(ticks))
    assert done and session["state"] == "completed"
    ticks = iter(range(0, 1000, 5))
    session, done = run_task_stability.wait_terminal(
        FakeClient(["running"] * 50), "s", poll=5, timeout=20,
        sleep=lambda _: None, clock=lambda: next(ticks))
    assert not done and session["state"] == "running"
