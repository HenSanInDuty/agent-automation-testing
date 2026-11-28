"""QA phase 15c (cook step B3, round 1): independent checks of F1, F2 and F3.

F1  the runner_config `POST /api/v1/runs` builds (with the middleware traceparent) is accepted by the
    REAL worker contract (`workers/playwright/src/contract.ts`, run through the worker's own `tsx`).
F2  `ObservedText` holds the last observation only: text only an earlier state showed is no candidate.
    The loop cases need the disposable database (skipped on the host, run in a container).
F3  ADR-047, the pinned lists in tests/test_agent_task_draft_e2e.py and scripts/run_agent_task_draft_e2e.py
    agree with each other and with the user's decision (reports/phase-16/user-answers-r1.md).
"""

# ruff: noqa: F811, E501
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import pytest
from domain.runs import TestRun as DomainRun
from fastapi.testclient import TestClient
from infrastructure.observability import trace_context
from main import app
from test_vision_agent_loop import click, ended, run_agent, step
from test_vision_agent_task_assessment import task_result
from test_vision_verified_text import ChangingPageWorker, loop_run
from vision_trace_fixtures import disposable_database  # noqa: F401  (pytest fixture)

ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "workers" / "playwright"
FIXTURE = ROOT / "packages" / "contracts" / "fixtures" / "execution-v1" / "request.playwright-test-source.json"
sys.path.insert(0, str(ROOT / "scripts"))
import run_agent_task_draft_e2e as e2e  # noqa: E402

# QA_CONTRACT_TS lets a mutation run point the probe at another copy of the contract (old code).
CONTRACT = Path(os.environ.get("QA_CONTRACT_TS", WORKER / "src" / "contract.ts"))
WORKER_TRACEPARENT = re.compile(r"^00-[0-9a-f]{32}-[0-9a-f]{16}-[0-9a-f]{2}$", re.IGNORECASE)


def _tsx() -> list[str] | None:
    node, cli = shutil.which("node"), WORKER / "node_modules" / "tsx" / "dist" / "cli.mjs"
    return [node, str(cli)] if node and cli.exists() else None


def worker_accepts(runner_config: dict, tmp_path: Path) -> tuple[bool, str]:
    """Run the real `validatePlaywrightTestSourceMode` on `runner_config`; (accepted, message)."""
    tsx = _tsx()
    if tsx is None:
        pytest.skip("worker node_modules (tsx) not installed")
    script = tmp_path / "probe.mts"
    script.write_text(
        f'import {{ validatePlaywrightTestSourceMode }} from "{CONTRACT.as_uri()}";\n'
        "const cfg = JSON.parse(process.argv[2]);\n"
        "try { const out = validatePlaywrightTestSourceMode(cfg);\n"
        "  console.log(JSON.stringify({ ok: true, keys: Object.keys(out) })); }\n"
        "catch (e) { console.log(JSON.stringify({ ok: false, message: String(e.message) })); }\n",
        encoding="utf-8",
    )
    done = subprocess.run(
        [*tsx, str(script), json.dumps(runner_config)], capture_output=True, text=True,
        timeout=120, cwd=str(WORKER), check=False, encoding="utf-8",
    )
    assert done.returncode == 0, done.stderr
    out = json.loads(done.stdout.strip().splitlines()[-1])
    return out["ok"], out.get("message", "")


def source_config() -> dict:
    return dict(json.loads(FIXTURE.read_text(encoding="utf-8"))["runner_config"])


# ------------------------------------------------------------------ F1: route -> worker contract


@pytest.fixture()
def captured_run(monkeypatch):
    """`POST /api/v1/runs` with the database layer faked; returns a list the route's command lands in."""
    from api.v1.routes import runs as routes

    commands: list = []
    test_case = type("Case", (), {"project_id": None, "revision": "a" * 40, "target_type": None,
                                  "name": "qa"})()

    class Catalog:
        def __init__(self, _session):
            pass

        def get_test_case(self, _tenant, _id):
            return test_case

    class Create:
        def __init__(self, *_repos):
            pass

        def execute(self, command):
            commands.append(command)
            return DomainRun.create(
                tenant_id=command.tenant_id, project_id=command.project_id,
                test_case_id=command.test_case_id, revision=command.revision,
                correlation_id=command.correlation_id,
            )

    @contextmanager
    def session_ctx(*_a):
        yield object()

    monkeypatch.setattr(routes, "create_session_factory", lambda _s: (lambda: session_ctx()))
    monkeypatch.setattr(routes, "transactional_session", lambda _f: session_ctx())
    monkeypatch.setattr(routes, "SqlAlchemyCatalogRepository", Catalog)
    for name in ("SqlAlchemyRunRepository", "SqlAlchemyOutboxEventRepository",
                 "SqlAlchemyAuditEventRepository", "SqlAlchemyActivityEventRepository"):
        monkeypatch.setattr(routes, name, lambda _s: object())
    monkeypatch.setattr(routes, "CreateRun", Create)
    return commands, test_case


def post_run(captured, headers=None):
    from auto_at.contracts.execution import TargetType

    commands, test_case = captured
    project_id = uuid4()
    test_case.project_id = project_id
    test_case.target_type = TargetType.WEB_UI
    response = TestClient(app).post(
        "/api/v1/runs",
        headers={"Idempotency-Key": f"qa15c:{uuid4()}", "X-Tenant-Id": "qa15c", **(headers or {})},
        json={"project_id": str(project_id), "test_case_id": "generated-x", "revision": "a" * 40,
              "runner_config": source_config()},
    )
    return response, commands


def test_f1_01_route_stamps_traceparent_and_the_worker_contract_accepts_the_whole_config(
    captured_run, tmp_path,
):
    response, commands = post_run(captured_run)
    assert response.status_code == 201, response.text
    config = commands[0].runner_config
    assert set(config) == {"mode", "playwright_test_source", "source_hash", "allowed_origins",
                           "traceparent"}
    assert WORKER_TRACEPARENT.match(config["traceparent"])
    accepted, message = worker_accepts(config, tmp_path)
    assert accepted, message


def test_f1_02_an_incoming_traceparent_header_is_propagated_and_accepted(captured_run, tmp_path):
    incoming = f"00-{'c' * 32}-{'d' * 16}-01"
    response, commands = post_run(captured_run, {"traceparent": incoming})
    assert response.status_code == 201, response.text
    config = commands[0].runner_config
    assert config["traceparent"].startswith(f"00-{'c' * 32}-")
    assert worker_accepts(config, tmp_path)[0]


def test_f1_03_the_generated_traceparent_is_always_a_shape_the_worker_accepts():
    for incoming in (None, f"00-{'a' * 32}-{'b' * 16}-00", "garbage", "00-short-bad-01"):
        context = trace_context(uuid4(), incoming)
        assert WORKER_TRACEPARENT.match(context.traceparent()), (incoming, context.traceparent())


def test_f1_04_config_without_traceparent_is_still_accepted(tmp_path):
    accepted, message = worker_accepts(source_config(), tmp_path)
    assert accepted, message


@pytest.mark.parametrize("bad", [
    "not-a-traceparent", "", 7, None, ["x"], {"a": 1},
    f"01-{'a' * 32}-{'b' * 16}-01",              # version other than 00
    f"00-{'a' * 31}-{'b' * 16}-01",              # trace id one char short
    f"00-{'a' * 32}-{'b' * 17}-01",              # parent id one char long
    f"00-{'a' * 32}-{'b' * 16}-0",               # flags one char
    f"00-{'g' * 32}-{'b' * 16}-01",              # not hex
    f"00-{'a' * 32}-{'b' * 16}-01\n",            # trailing newline must not slip past `$`
    f" 00-{'a' * 32}-{'b' * 16}-01",             # leading space
])
def test_f1_05_a_malformed_traceparent_is_rejected(bad, tmp_path):
    config = {**source_config(), "traceparent": bad}
    accepted, message = worker_accepts(config, tmp_path)
    assert not accepted and "invalid playwright_test_source runner configuration" in message


@pytest.mark.parametrize("extra", [
    {"shell": "rm -rf /"}, {"headers": {}}, {"traceparent2": "x"}, {"Traceparent": "x"},
    {"tracestate": "a=b"},
])
def test_f1_06_any_other_unknown_key_is_still_rejected_even_with_a_valid_traceparent(extra, tmp_path):
    valid = f"00-{'a' * 32}-{'b' * 16}-01"
    for config in ({**source_config(), **extra}, {**source_config(), "traceparent": valid, **extra}):
        accepted, message = worker_accepts(config, tmp_path)
        assert not accepted, extra


def test_f1_07_traceparent_does_not_excuse_a_missing_required_key_or_a_wrong_hash(tmp_path):
    valid = f"00-{'a' * 32}-{'b' * 16}-01"
    base = source_config()
    for broken in (
        {k: v for k, v in base.items() if k != "allowed_origins"},
        {**base, "source_hash": "0" * 64},
        {**base, "mode": "shell"},
    ):
        assert not worker_accepts({**broken, "traceparent": valid}, tmp_path)[0]
    # traceparent standing in for a missing key must not satisfy the key count
    swapped = {k: v for k, v in base.items() if k != "source_hash"} | {"traceparent": valid}
    assert not worker_accepts(swapped, tmp_path)[0]


def test_f1_08_the_validated_config_drops_traceparent_so_its_shape_is_unchanged(tmp_path):
    accepted, _ = worker_accepts({**source_config(), "traceparent": f"00-{'a' * 32}-{'b' * 16}-01"},
                                 tmp_path)
    assert accepted


# ------------------------------------------------------------------ F2: last observation only


def test_f2_01_observed_text_holds_the_last_observation_only_when_reset_each_step():
    # Pure unit: the loop's contract is "fresh ObservedText per observation".
    from domain.verified_text import ObservedText, verify_quotes
    from test_vision_verified_text import check, observation

    before = observation(page_text=[("status", "2 viec, 1 da xong")])
    after = observation(page_text=[("status", "3 viec, 1 da xong")])
    seen = ObservedText()
    seen.add(after)
    checks = [check('"2 viec, 1 da xong" then "3 viec, 1 da xong"')]
    result = verify_quotes(checks, seen)
    assert [item["text"] for item in result["items"]] == ["3 viec, 1 da xong"]
    assert result["dropped"] == 1
    accumulated = ObservedText()
    accumulated.add(before)
    accumulated.add(after)  # what the old code did
    assert len(verify_quotes(checks, accumulated)["items"]) == 2


def _verified(run):
    return run.record.task_assessment["verified_text"]


def test_f2_02_text_only_the_earlier_observation_showed_is_not_a_candidate(
    disposable_database, monkeypatch,
):
    worker = ChangingPageWorker([[("status", "2 viec, 1 da xong")], [("status", "3 viec, 1 da xong")]])
    result = task_result(checks=(("c", "met", 'from "2 viec, 1 da xong" to "3 viec, 1 da xong"'),))
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), result], worker=worker)
    assert ended(run) == "agent_done"
    assert _verified(run) == {
        "items": [{"kind": "status", "text": "3 viec, 1 da xong", "check_index": 0}],
        "dropped": 1, "truncated": False}


def test_f2_03_last_observation_without_page_text_leaves_no_candidate(
    disposable_database, monkeypatch,
):
    # The last observation is a bare screenshot / page with no text: nothing may be verified.
    worker = ChangingPageWorker([[("status", "2 viec, 1 da xong")], []])
    result = task_result(checks=(("c", "met", 'earlier "2 viec, 1 da xong"'),))
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), result], worker=worker)
    assert ended(run) == "agent_done"
    stored = _verified(run)
    assert [item["text"] for item in stored["items"] if item["kind"] != "control_name"] == []
    assert stored["dropped"] == 1


def test_f2_04_text_in_the_middle_observation_only_is_dropped_over_three_observations(
    disposable_database, monkeypatch,
):
    worker = ChangingPageWorker([[("status", "first")], [("status", "middle only")],
                                 [("status", "final")]])
    result = task_result(checks=(("c", "met", 'saw "first", "middle only" and "final"'),))
    run = run_agent(disposable_database, monkeypatch,
                    [step(click("1:1")), step(click("1:1")), result], worker=worker)
    assert ended(run) == "agent_done"
    assert _verified(run) == {"items": [{"kind": "status", "text": "final", "check_index": 0}],
                              "dropped": 2, "truncated": False}


def test_f2_05_text_present_in_both_first_and_last_observation_is_still_a_candidate(
    disposable_database, monkeypatch,
):
    worker = ChangingPageWorker([[("heading", "Todo list"), ("status", "2 viec")],
                                 [("heading", "Todo list"), ("status", "3 viec")]])
    result = task_result(checks=(("c", "met", 'heading "Todo list" and "3 viec"'),))
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), result], worker=worker)
    assert {item["text"] for item in _verified(run)["items"]} == {"Todo list", "3 viec"}


def test_f2_06_a_one_turn_session_verifies_against_its_only_observation(
    disposable_database, monkeypatch,
):
    run = loop_run(disposable_database, monkeypatch,
                   [task_result(checks=(("c", "met", 'page says "Xin chào, demo"'),))],
                   [("heading", "Xin chào, demo")])
    assert ended(run) == "agent_done"
    assert _verified(run)["items"] == [{"kind": "heading", "text": "Xin chào, demo", "check_index": 0}]


def test_f2_07_login_success_regression_unicode_greeting_after_the_click_is_a_candidate(
    disposable_database, monkeypatch,
):
    worker = ChangingPageWorker([[("heading", "Đăng nhập")], [("heading", "Xin chào, demo")]])
    result = task_result(checks=(
        ("Greeting", "met", 'the page shows "Xin chào, demo"'),
        ("Form gone", "met", 'no more "Đăng nhập" heading'),
    ))
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), result], worker=worker)
    stored = _verified(run)
    assert [item["text"] for item in stored["items"] if item["kind"] == "heading"] == ["Xin chào, demo"]
    assert stored["dropped"] == 1  # "Đăng nhập" belonged to the state before the last action


def test_f2_08_search_results_regression_result_text_after_the_search_is_a_candidate(
    disposable_database, monkeypatch,
):
    worker = ChangingPageWorker([[("heading", "Tìm kiếm")],
                                 [("paragraph", "Balo laptop"), ("status", "1 kết quả")]])
    result = task_result(checks=(("Result", "met", 'list has "Balo laptop"; "Áo thun cotton" is gone'),))
    run = run_agent(disposable_database, monkeypatch, [step(click("1:1")), result], worker=worker)
    stored = _verified(run)
    assert [item["text"] for item in stored["items"] if item["kind"] == "paragraph"] == ["Balo laptop"]
    assert stored["dropped"] == 1  # "Áo thun cotton" was never observed


def test_f2_09_a_not_met_check_still_makes_no_candidate_after_the_change(
    disposable_database, monkeypatch,
):
    run = loop_run(disposable_database, monkeypatch,
                   [task_result(checks=(("c", "not_met", 'wanted "final"'),))],
                   [("status", "final")])
    assert _verified(run)["items"] == []


# ------------------------------------------------------------------ F3: ADR, script, test, user decision

ADR = (ROOT / "docs" / "adr" / "047-assessment-to-playwright-draft.md").read_text(encoding="utf-8")
PHASE16 = next((ROOT / "plan").glob("*agent-loop-task-testing/phase-16-end-to-end-fixture.md")
               ).read_text(encoding="utf-8")


def test_f3_01_adr_place_9_names_every_artifact_member_the_script_expects():
    place9 = next(line for line in ADR.splitlines() if line.startswith("| 9 |"))
    for member in ("0-trace.trace", "test.trace", "resources/src@", "0-trace.network", "postData",
                   ".dat", "0-trace.stacks"):
        assert member in place9, member
    assert "trace zip" in place9 and "không thêm loại artifact mới" in place9
    for key in e2e.ARTIFACT_PLACES_EXPECTED:
        assert key in place9 or key == ".html" or key == ".trace", key
    assert "0-trace.stacks" not in " ".join(e2e.ARTIFACT_PLACES_EXPECTED)
    assert e2e.artifact_verdict({"x/0-trace.stacks": 1}) == ([], [], ["x/0-trace.stacks"])


def test_f3_02_adr_q11_and_risk_record_the_usage_condition_and_no_masking():
    assert "Cập nhật phase 15c" in ADR
    assert "điều kiện sử dụng" in ADR.lower() or "Điều kiện sử dụng" in ADR
    assert "không có code che" in ADR
    assert "Giá trị nằm trong câu task" in ADR
    for column in ("task_assessment", "memory", "evaluation_previous_goal", "next_goal"):
        assert column in ADR


def test_f3_03_script_free_text_columns_equal_the_ones_the_adr_lists():
    assert {c for _, c in e2e.FREE_TEXT_PLACES} == {
        "task_assessment", "memory", "evaluation_previous_goal", "next_goal"}
    assert {t for t, _ in e2e.FREE_TEXT_PLACES} == {"visual_exploration_sessions", "visual_agent_steps"}
    # those are NOT declared places (ADR: "ngoài danh sách"), and their tables stay in the clean set
    assert not e2e.FREE_TEXT_PLACES & e2e.DECLARED_AFTER_APPROVAL
    assert {t for t, _ in e2e.FREE_TEXT_PLACES} <= set(e2e.MUST_BE_CLEAN_TABLES)
    assert set(e2e.MUST_BE_CLEAN_TABLES) == {"visual_exploration_sessions", "visual_agent_steps",
                                             "audit_events", "generation_requests"}


def test_f3_04_value_in_task_text_names_are_exactly_the_sessions_whose_task_text_has_the_value():
    tasks = {t["id"]: t["task"] for t in json.loads(
        (ROOT / "benchmarks" / "task-ui" / "tasks.v1.json").read_text(encoding="utf-8"))["tasks"]}
    for name in e2e.VALUE_IN_TASK_TEXT:
        text = tasks[e2e.SESSIONS[name]["task"]]
        assert all(value in text for value in e2e.SCAN_VALUES[name]), name
    # the marker is typed only when asking for the draft: not in the task text, not accepted in free text
    assert "marker-todo" not in e2e.VALUE_IN_TASK_TEXT
    assert e2e.MARKER not in tasks[e2e.SESSIONS["marker-todo"]["task"]]
    assert e2e.free_text_hits({("visual_agent_steps", "memory")}, "marker-todo") == []
    assert e2e.clean_table_hits({("visual_agent_steps", "memory")}, "marker-todo") == [
        "visual_agent_steps"]
    # a value that is in the task text but sits in a clean table other than free text still fails
    for table in ("audit_events", "generation_requests"):
        assert e2e.clean_table_hits({(table, "payload")}, "pos-login") == [table]


def test_f3_05_a_declared_place_is_never_reported_as_free_text_or_clean():
    for place in e2e.DECLARED_AFTER_APPROVAL:
        assert e2e.clean_table_hits({place}, "pos-login") == []
        assert e2e.free_text_hits({place}, "pos-login") == []


def test_f3_06_case_i_expects_assessment_not_achieved_and_phase_16_says_the_same():
    source = (ROOT / "scripts" / "run_agent_task_draft_e2e.py").read_text(encoding="utf-8")
    case = source[source.index("def case_i"):source.index("CASES = {")]
    assert '409, "assessment_not_achieved"' in case
    assert not re.search(r'409,\s*"locator_unavailable"', case)
    item = PHASE16[PHASE16.index("(i) ô có nhãn"):PHASE16.index("(j)")]
    assert "assessment_not_achieved" in item and "blocked" in item
    assert "locator_unavailable" in item and "ca DB" in item  # the DB case keeps it
    test_source = (ROOT / "tests" / "test_agent_task_draft_e2e.py").read_text(encoding="utf-8")
    assert 'refused(post(world), 409, "locator_unavailable")' in test_source  # DB case kept


def test_f3_07_phase_16_criterion_4_no_longer_claims_network_and_stacks_are_absent():
    item = PHASE16[PHASE16.index("4. Quét nơi lưu giá trị"):]
    item = item.split("\n5. ", 1)[0]
    assert "0-trace.network" in item
    assert not re.search(r"0-trace\.network`?/`?0-trace\.stacks`? không có", item)


def test_f3_08_decision_file_matches_what_was_implemented():
    answers = next((ROOT / "plan").glob(
        "*agent-loop-task-testing/reports/phase-16/user-answers-r1.md")).read_text(encoding="utf-8")
    assert "chấp nhận `assessment_not_achieved`" in answers
    assert "0-trace.network" in answers and "resources/*.dat" in answers
    assert "phiên khi câu task chứa giá trị" in answers or "câu task chứa giá trị" in answers
    assert "Chưa quyết: F4" in answers  # F4 stays a debt: nothing in the script/ADR claims to fix it
