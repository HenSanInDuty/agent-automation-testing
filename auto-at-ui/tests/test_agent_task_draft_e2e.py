"""ADR-047 phase 16: the whole chain on the disposable PostgreSQL fixture, no model, no browser.

assessment `achieved` session -> requester (contributor) asks for a draft with the typed values ->
a different reviewer approves with the disposable-account acknowledgement -> test case + queued run.
The same chain, refused one rule at a time (negative cases a, c-j of the phase; case b needs a real
browser and is measured by `scripts/run_agent_task_draft_e2e.py`). The places a value may be stored
are pinned in that script (`DECLARED_*`); this file fails if the script, the phase 14 test or the
database disagree with the pinned list. Skipped when the fixture database (127.0.0.1:55437)
is absent.
"""

# ruff: noqa: F811  (the imported `world` fixture is used as a test argument)
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from auto_at.contracts.execution import RunStatus, TestExecutionResult
from domain.authorization import Role
from infrastructure.persistence.models import (
    AuditEventModel,
    GeneratedTestDecisionModel,
    GeneratedTestDraftModel,
    ProjectExecutionPolicyModel,
    TestCaseModel,
    TestRunModel,
    VisualExplorationSessionModel,
    VisualLocatorEvidenceModel,
    VisualOperationFrameModel,
)
from sqlalchemy import func, select, update
from test_agent_task_draft_routes import (  # noqa: F401  (`world` is a pytest fixture)
    ALLOWED_AFTER_APPROVAL,
    ALLOWED_AFTER_CREATE,
    MARKERS,
    NAME,
    PASSWORD,
    REQUESTER,
    VALUES,
    Preflight,
    counts,
    decide,
    post,
    principal,
    set_session,
    where_is,
    world,
)

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import run_agent_task_draft_e2e as e2e  # noqa: E402

pytest_plugins = ["vision_trace_fixtures"]


def refused(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()["detail"]
    assert (body["code"] if isinstance(body, dict) else body) == code
    return body


def approved_chain(world):
    """Requester asks, a different reviewer approves: the draft record after approval."""
    created = post(world)
    assert created.status_code == 201, created.text
    assert decide(world, created.json()["draft_id"]).status_code == 200
    return world.client.get(
        f"/api/v1/test-generations/drafts/{created.json()['draft_id']}").json()


# ----------------------------------------------------------------------- the pinned list


def test_the_script_pins_the_same_places_as_the_phase_14_scan():
    assert e2e.DECLARED_AFTER_CREATE == ALLOWED_AFTER_CREATE == {
        ("generated_test_drafts", "playwright_test_source")}
    assert e2e.DECLARED_AFTER_APPROVAL == ALLOWED_AFTER_APPROVAL == {
        ("generated_test_drafts", "playwright_test_source"), ("test_cases", "specification"),
        ("test_runs", "request"), ("outbox_events", "payload")}


def test_tables_that_must_stay_clean_are_not_declared_places():
    assert set(e2e.MUST_BE_CLEAN_TABLES) == {
        "visual_exploration_sessions", "visual_agent_steps", "audit_events",
        "generation_requests"}
    assert not {table for table, _ in e2e.DECLARED_AFTER_APPROVAL} & set(
        e2e.MUST_BE_CLEAN_TABLES)


def test_free_text_hits_are_accepted_only_for_values_the_task_text_contains():
    # ADR-047 (phase 15c): the model copies a value from the author's task text into free text;
    # a value only the requester typed (the marker) must still not reach those columns.
    places = {("generated_test_drafts", "playwright_test_source"),
              ("visual_exploration_sessions", "task_assessment"),
              ("visual_agent_steps", "memory"), ("audit_events", "payload")}
    assert e2e.clean_table_hits(places, "pos-login") == ["audit_events"]
    assert e2e.free_text_hits(places, "pos-login") == [
        "visual_agent_steps.memory", "visual_exploration_sessions.task_assessment"]
    assert e2e.clean_table_hits(places, "marker-todo") == [
        "audit_events", "visual_agent_steps", "visual_exploration_sessions"]
    assert e2e.free_text_hits(places, "marker-todo") == []
    assert {t for t, _ in e2e.FREE_TEXT_PLACES} <= set(e2e.MUST_BE_CLEAN_TABLES)
    assert not e2e.FREE_TEXT_PLACES & e2e.DECLARED_AFTER_APPROVAL


# ----------------------------------------------------------------------- the chain


def test_the_chain_ends_in_a_test_case_and_a_queued_run_and_values_sit_only_where_declared(world):
    before = counts(world)
    draft = approved_chain(world)
    assert draft["state"] == "approved"
    assert draft["linked_test_case_id"] == f"generated-{draft['id']}" and draft["linked_run_id"]
    after = counts(world)
    assert (after["test_cases"], after["test_runs"]) == (
        before["test_cases"] + 1, before["test_runs"] + 1)
    with world.factory() as db:
        run = db.scalars(select(TestRunModel)).one()
        case = db.scalars(select(TestCaseModel)).one()
    # No verdict yet: the verdict is the deterministic runner's, after the approval (ADR-047).
    assert run.status == "queued" and run.result is None
    assert case.specification["contains_test_values"] is True
    assert run.request["runner_config"]["source_hash"] == draft["source_hash"]
    found = {}
    for value in (NAME, PASSWORD):
        found = where_is(world, value)
        assert e2e.unexpected_places(found, e2e.DECLARED_AFTER_APPROVAL) == [], value
        assert e2e.missing_places(found, e2e.DECLARED_AFTER_APPROVAL) == [], value
        assert not {table for table, _ in found} & set(e2e.MUST_BE_CLEAN_TABLES)
    assert not any(NAME in text or PASSWORD in text for text in world.seen)


def test_two_different_actors_with_different_roles_run_the_chain(world):
    created = post(world)
    draft_id = created.json()["draft_id"]
    assert decide(world, draft_id, subject="reviewer-1", roles=(Role.REVIEWER,)).status_code == 200
    with world.factory() as db:
        provenance = db.get(GeneratedTestDraftModel, draft_id).provenance
        audit = db.scalars(select(AuditEventModel)).all()
        decision = db.scalars(select(GeneratedTestDecisionModel)).one()
    assert provenance["requested_by"] == REQUESTER != "reviewer-1"
    assert decision.decided_by == "reviewer-1" and decision.approved is True
    assert REQUESTER in {event.actor for event in audit}


def test_a_value_stored_anywhere_else_makes_the_pinned_scan_fail(world):
    draft_id = post(world).json()["draft_id"]
    assert decide(world, draft_id).status_code == 200
    with world.factory.begin() as db:
        db.execute(update(AuditEventModel).values(actor=f"leak-{NAME}"))
    found = where_is(world, NAME)
    assert e2e.unexpected_places(found, e2e.DECLARED_AFTER_APPROVAL) == [("audit_events", "actor")]
    assert {"audit_events"} & {table for table, _ in found} & set(e2e.MUST_BE_CLEAN_TABLES)


# ----------------------------------------------------------------------- criterion 4b


def test_the_form_hint_is_the_length_the_requester_will_type(world):
    response = world.client.get(
        f"/api/v1/vision/explorations/{world.session_id}/test-draft/inputs")
    body = response.json()
    assert response.status_code == 200 and body["owned_test_target"] is True
    assert [step["text_chars"] for step in body["type_steps"]] == [len(v) for v in VALUES]
    assert e2e.values_for("none", body["type_steps"]) is None  # no pool, so nothing is invented
    for step in body["type_steps"]:
        assert set(step) == {"step_index", "locator_name", "text_chars"}
    assert NAME not in response.text and PASSWORD not in response.text


def test_a_project_without_the_flag_shows_no_length(world):
    with world.factory.begin() as db:
        db.execute(update(ProjectExecutionPolicyModel).values(vision_owned_test_target=False))
    body = world.client.get(
        f"/api/v1/vision/explorations/{world.session_id}/test-draft/inputs").json()
    assert body["owned_test_target"] is False and body["type_steps"] == []


# ----------------------------------------------------------------------- negative cases


def nothing_written(world, before):
    after = counts(world)
    for table in ("generation_requests", "generated_test_drafts", "test_cases", "test_runs",
                  "outbox_events"):
        assert after[table] == before[table], table


@pytest.mark.parametrize("status", ["not_achieved", "blocked", "inconclusive"])
def test_a_a_session_that_did_not_achieve_the_task_gets_no_draft(world, status):
    with world.factory() as db:
        stored = dict(db.scalar(select(VisualExplorationSessionModel.task_assessment)))
    set_session(world, task_assessment=stored | {"status": status})
    before = counts(world)
    refused(post(world), 409, "assessment_not_achieved")
    nothing_written(world, before)


def test_c_an_inconsistent_group_is_refused_with_the_report(world):
    with world.factory.begin() as db:
        source = db.scalar(select(VisualExplorationSessionModel))
        columns = {column.name: getattr(source, column.name)
                   for column in VisualExplorationSessionModel.__table__.columns}
        for _ in range(2):
            db.add(VisualExplorationSessionModel(**columns | {
                "id": uuid4(), "idempotency_key": uuid4().hex,
                "task_assessment": {"status": "not_achieved", "advisory": True}}))
    before = counts(world)
    detail = refused(post(world), 409, "assessment_inconsistent")
    assert detail["consistency"]["agreement_rate"] == 0.6667  # 2 of 3 repeat not_achieved
    assert detail["consistency"]["threshold"] == 0.9
    nothing_written(world, before)


def test_d_the_requester_cannot_approve_their_own_draft_even_with_a_reviewer_role(world):
    draft_id = post(world).json()["draft_id"]
    before = counts(world)
    response = decide(world, draft_id, subject=REQUESTER, roles=(Role.CONTRIBUTOR, Role.REVIEWER))
    assert response.status_code == 409
    assert response.json()["detail"] == "reviewer_must_differ_from_requester"
    nothing_written(world, before)


def test_e_a_contributor_cannot_approve(world):
    draft_id = post(world).json()["draft_id"]
    before = counts(world)
    response = decide(world, draft_id, subject="contributor-2", roles=(Role.CONTRIBUTOR,))
    assert response.status_code == 404 and "reviewer" not in response.text
    nothing_written(world, before)
    with world.factory() as db:
        assert db.get(GeneratedTestDraftModel, draft_id).state == "pending_review"


def test_f_approval_without_the_disposable_account_acknowledgement_is_refused(world):
    draft_id = post(world).json()["draft_id"]
    before = counts(world)
    world.principal = principal({Role.REVIEWER}, "reviewer-1", world.tenant)
    for body in ({"approved": True},
                 {"approved": True, "acknowledge_disposable_credentials": False}):
        response = world.client.post(
            f"/api/v1/test-generations/drafts/{draft_id}/decision", json=body)
        assert response.status_code == 409
        assert response.json()["detail"] == "disposable_credentials_ack_required"
    nothing_written(world, before)


def test_g_a_project_without_the_flag_is_refused_for_a_session_with_type_steps(world):
    with world.factory.begin() as db:
        db.execute(update(ProjectExecutionPolicyModel).values(vision_owned_test_target=False))
    before = counts(world)
    refused(post(world), 409, "input_value_not_allowed")
    nothing_written(world, before)


def test_g_switching_the_flag_off_between_request_and_approval_is_refused(world):
    draft_id = post(world).json()["draft_id"]
    with world.factory.begin() as db:
        db.execute(update(ProjectExecutionPolicyModel).values(vision_owned_test_target=False))
    before = counts(world)
    response = decide(world, draft_id)
    assert response.status_code == 409 and response.json()["detail"] == "owned_test_target_disabled"
    nothing_written(world, before)


def test_h_evidence_that_expired_is_refused(world):
    with world.factory.begin() as db:
        db.execute(update(VisualOperationFrameModel).values(deleted_at=func.now()))
    before = counts(world)
    refused(post(world), 409, "evidence_expired")
    nothing_written(world, before)


def test_i_a_step_whose_locator_was_redacted_is_refused_locator_unavailable(world):
    # The worker withholds the descriptor of a field labelled "Password" (Q4: status `redacted`).
    # The real stack shows the session ending `blocked` earlier (see the report), so this is the
    # only place the mapping is proven.
    with world.factory.begin() as db:
        for row in db.scalars(select(VisualLocatorEvidenceModel)).all():
            row.status = "redacted"
            row.payload = dict(row.payload) | {
                "status": "redacted", "descriptor": None, "bounding_box": None,
                "matched_count": 0, "target_match": False, "actionable": False,
                "verified_at": None, "reason_code": "redacted"}
    before = counts(world)
    detail = refused(post(world), 409, "locator_unavailable")
    assert set(detail) <= {"code", "step_index", "operation_id"}
    nothing_written(world, before)


def test_j_revised_draft_of_an_approved_values_test_is_refused_and_queues_nothing(world):
    draft = approved_chain(world)
    run_id = draft["linked_run_id"]
    failed = TestExecutionResult(
        run_id=run_id, correlation_id=draft["correlation_id"], status=RunStatus.FAILED,
        started_at="2026-11-28T00:00:00Z", completed_at="2026-11-28T00:00:01Z",
        summary="Assertion failed.")
    with world.factory.begin() as db:
        db.execute(update(TestRunModel).where(TestRunModel.id == run_id).values(
            status="failed", result=failed.model_dump(mode="json")))
    world.principal = principal({Role.CONTRIBUTOR}, tenant=world.tenant)
    before = counts(world)
    response = world.client.post(f"/api/v1/runs/{run_id}/revised-draft",
                                 headers={"Idempotency-Key": uuid4().hex})
    assert response.status_code == 409 and response.json()["detail"] == "credentials_in_source"
    assert counts(world)["generation_requests"] == before["generation_requests"]
    assert NAME not in response.text and PASSWORD not in response.text


def test_j_a_failed_preflight_of_a_values_draft_queues_no_repair_request(world):
    draft_id = post(world).json()["draft_id"]
    Preflight.fail = True
    before = counts(world)
    response = decide(world, draft_id)
    assert response.status_code == 409 and response.json()["detail"] == "credentials_in_source"
    assert counts(world)["generation_requests"] == before["generation_requests"]


# ----------------------------------------------------------------------- the harness helpers


def test_the_marker_never_equals_a_value_the_task_text_could_contain():
    assert all(marker not in e2e.MARKER for marker in MARKERS)
    assert len(e2e.MARKER) == len("Viết báo cáo")  # the todo text the agent typed: same length


def test_needle_variants_cover_the_json_and_script_spellings_of_a_value():
    variants = e2e.needle_variants("Viết \"x\"")
    assert variants == ['Viết "x"', r'Vi\u1ebft \"x\"', r'Vi\\u1ebft \\"x\\"']
    assert e2e.needle_variants("plain") == ["plain"]


def test_values_are_used_only_when_every_length_matches():
    steps = [{"text_chars": 4}, {"text_chars": 8}]
    assert e2e.values_for("pos-login", steps) == ["demo", "Demo1234"]
    assert e2e.values_for("pos-login", [{"text_chars": 4}, {"text_chars": 9}]) is None
    assert e2e.values_for("pos-login", steps[:1]) is None
    assert e2e.values_for("pos-todo", [{"text_chars": 12}]) == ["Viết báo cáo"]


def test_artifact_places_split_expected_failure_only_and_unexpected():
    hits = {"t.unzipped/0-trace.trace": 2, "t.unzipped/test.trace": 1,
            "t.unzipped/resources/src@ab.txt": 1, "t.unzipped/resources/ab.html": 1,
            "t.unzipped/0-trace.network": 1, "t.unzipped/resources/cd.dat": 1,
            "t.unzipped/0-trace.stacks": 1, "playwright-output-1": 1}
    expected, on_failure, unexpected = e2e.artifact_verdict(hits)
    # Place 9 (ADR-047, phase 15c): a page that sends a request leaves the value in the network
    # log and in the request body files as well; only the stacks (or anything new) is unexpected.
    assert expected == ["t.unzipped/0-trace.network", "t.unzipped/0-trace.trace",
                        "t.unzipped/resources/ab.html", "t.unzipped/resources/cd.dat",
                        "t.unzipped/resources/src@ab.txt", "t.unzipped/test.trace"]
    assert on_failure == ["playwright-output-1"]
    assert unexpected == ["t.unzipped/0-trace.stacks"]


def test_files_containing_finds_each_spelling(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "one.txt").write_bytes("x Viết y".encode())
    (tmp_path / "two.bin").write_bytes(b"Vi\\u1ebft")
    (tmp_path / "three.txt").write_bytes(b"nothing here")
    found = e2e.files_containing(tmp_path, e2e.needle_variants("Viết"))
    assert found == {"a/one.txt": 1, "two.bin": 1}


def test_unexpected_and_missing_places_are_sorted_set_differences():
    declared = {("a", "x"), ("b", "y")}
    found = {("b", "y"), ("c", "z"), ("a", "w")}
    assert e2e.unexpected_places(found, declared) == [("a", "w"), ("c", "z")]
    assert e2e.missing_places(found, declared) == [("a", "x")]


def test_the_second_fixture_is_the_repo_fixture_plus_a_mode_switch_and_fails_on_a_changed_anchor():
    source = (ROOT / "benchmarks/targets/task-ui/server.mjs").read_text("utf-8")
    patched = e2e.patch_fixture_source(source)
    for needle in ('case "POST /__mode"', "mode.broken ?", "mode.pw ?", "Chào mừng trở lại"):
        assert needle in patched and needle not in source
    assert source.count("Xin chào") >= 1 and "__mode" not in source  # repo file is untouched
    with pytest.raises(ValueError, match="anchor"):
        e2e.patch_fixture_source(source.replace("Xin chào, ${esc(user)}", "Hi ${esc(user)}"))
    assert e2e.mode_command("c", broken=1)[-1].endswith("/__mode?broken=1&pw=0")


def test_every_session_plan_names_a_suite_task_and_a_known_project():
    suite = {item["id"] for item in e2e.stability.load_suite(e2e.rts.DEFAULT_SUITE)}
    projects = {e2e.FIXTURE_PROJECT, e2e.E2E_PROJECT, e2e.PASSWORD_PROJECT}
    for name, plan in e2e.SESSIONS.items():
        assert plan["task"] in suite and plan["project"] in projects, name
    assert {"pos-login", "pos-todo", "pos-search"} <= set(e2e.SESSIONS)
    assert {e2e.SESSIONS[n]["task"] for n in ("neg-a-save", "neg-a-counter")} == {
        "broken-save", "broken-counter"}


def test_project_suffix_renames_only_the_two_scratch_projects(monkeypatch):
    monkeypatch.setattr(e2e, "SESSIONS", {k: dict(v) for k, v in e2e.SESSIONS.items()})
    fixture_sessions = {n for n, p in e2e.SESSIONS.items() if p["project"] == e2e.FIXTURE_PROJECT}
    monkeypatch.setattr(e2e, "E2E_PROJECT", e2e.E2E_PROJECT)
    monkeypatch.setattr(e2e, "PASSWORD_PROJECT", e2e.PASSWORD_PROJECT)
    old_e2e, old_pw = e2e.E2E_PROJECT, e2e.PASSWORD_PROJECT
    e2e.apply_project_suffix(" r9")
    assert (e2e.E2E_PROJECT, e2e.PASSWORD_PROJECT) == (old_e2e + " r9", old_pw + " r9")
    assert e2e.SESSIONS["e2e-1"]["project"] == old_e2e + " r9"
    assert e2e.SESSIONS["pw-label"]["project"] == old_pw + " r9"
    assert {n for n, p in e2e.SESSIONS.items() if p["project"] == e2e.FIXTURE_PROJECT} == (
        fixture_sessions)


def test_api_rerun_posts_the_stored_request_without_traceparent_and_waits(monkeypatch):
    stored = {"project_id": "p", "test_case_id": "t", "target_type": "web_ui",
              "target_url": "http://x/login", "artifact_policy": {"retain_days": 30},
              "runner_config": {"mode": "m", "traceparent": "00-aa-bb-01", "source_hash": "h"}}
    monkeypatch.setattr(e2e, "psql", lambda sql: [e2e.json.dumps(stored)])
    monkeypatch.setattr(e2e, "wait_run", lambda client, run_id: {"status": "passed"})
    sent = {}

    class Client:
        def post(self, url, json, headers):
            sent.update(url=url, body=json, key=headers["Idempotency-Key"])
            return type("R", (), {"status_code": 201, "json": lambda self: {"id": "run-1"}})()

    result = e2e.api_rerun(None, Client(), "first")
    assert sent["url"] == "/api/v1/runs" and sent["key"]
    assert sent["body"]["runner_config"] == {"mode": "m", "source_hash": "h"}
    assert sent["body"]["test_case_id"] == "t" and "run_id" not in sent["body"]
    assert result["run_id"] == "run-1" and result["status"] == "passed"
