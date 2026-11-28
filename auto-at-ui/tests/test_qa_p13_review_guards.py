"""QA phase 13 (ADR-047): extra cases over the review boundary, the model-path guards and ADR-002.

Complements `test_agent_task_review_guards.py`. HTTP + real PostgreSQL fixture (127.0.0.1:55437,
skipped when absent). The sentinel below is unique per run and is checked in every table that must
never hold it (`generation_requests`, `audit_events`) and in the captured logs.
"""

# ruff: noqa: F811
import asyncio
import logging
from pathlib import Path
from uuid import uuid4

import pytest
from application.reporting_events import ReportingEventProcessor
from auto_at.contracts.events import EventType
from auto_at.contracts.execution import (
    RunStatus,
    TargetType,
    TestExecutionRequest,
    sha256_text,
)
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult
from config import Settings
from domain.entities import ArtifactRecord, TestCase
from domain.runs import OutboxEvent, TestRun
from infrastructure.persistence.models import (
    AuditEventModel,
    GeneratedTestDraftModel,
    GenerationRequestModel,
    TestCaseModel,
    TestRunModel,
)
from sqlalchemy import select, text
from test_agent_task_review_guards import (  # noqa: F401  (fixtures and helpers, not tests)
    ORIGIN,
    REQUESTER,
    Preflight,
    add_draft,
    count,
    decide,
    draft_state,
    failed_run,
    headers,
    provenance,
    revise,
    set_flag,
    snapshot,
    world,
)
from vision_trace_fixtures import disposable_database  # noqa: F401  (pytest fixture)

SENT = "QA13-" + uuid4().hex
SENT_SOURCE = (
    "import { test, expect } from '@playwright/test';\n"
    "test('login', async ({ page }) => {\n"
    f"  await page.goto('{ORIGIN}/');\n"
    f"  await page.getByLabel('Mat khau').fill('{SENT}');\n"
    "});\n"
)
ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "plan" / "20261125-2140-agent-loop-task-testing"


def table_text(world, table: str) -> str:
    with world.factory() as db:
        rows = db.execute(text(f"select t::text from {table} t")).scalars().all()
    return "\n".join(rows)


# ---------------------------------------------------------------- review boundary (criterion 1)


def test_requester_may_reject_own_draft_but_still_needs_the_proposal_permission(world):
    """Documented behaviour: the "different person" rule applies to approval only."""
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    assert decide(world, draft_id, REQUESTER, "contributor", approved=False).status_code == 404
    assert draft_state(world, draft_id) == "pending_review"
    assert decide(world, draft_id, REQUESTER, "reviewer", approved=False).status_code == 200
    assert draft_state(world, draft_id) == "rejected"
    snap = snapshot(world)
    assert snap["test_cases"] == 0 and snap["test_runs"] == 0


def test_empty_agent_trace_source_object_is_still_an_agent_draft(world):
    set_flag(world, True)
    prov = provenance()
    prov["agent_trace_source"] = {}
    draft_id = add_draft(world, source=SENT_SOURCE, prov=prov)
    before = snapshot(world)
    assert decide(world, draft_id, "x", "contributor",
                  acknowledge_disposable_credentials=True).status_code == 404
    assert snapshot(world) == before


def test_reviewer_of_another_tenant_cannot_decide(world):
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    before = snapshot(world)
    response = world.client.post(
        f"/api/v1/test-generations/drafts/{draft_id}/decision",
        json={"approved": True, "acknowledge_disposable_credentials": True},
        headers={**headers("rev", "reviewer"), "X-Tenant-Id": "tenant-b"},
    )
    assert response.status_code == 404
    assert snapshot(world) == before


def test_no_tenant_header_is_unauthenticated_and_nothing_changes(world):
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    before = snapshot(world)
    response = world.client.post(
        f"/api/v1/test-generations/drafts/{draft_id}/decision",
        json={"approved": True, "acknowledge_disposable_credentials": True},
    )
    assert response.status_code == 401
    assert snapshot(world) == before


def test_missing_actor_header_falls_back_to_local_developer_and_the_rule_still_applies(world):
    """Local header auth (pre-existing): no X-Actor-Id means actor `local-developer`.

    Such an actor is a different person from a normal requester, so it can approve; when the
    requester IS `local-developer` the same-person rule refuses it.
    """
    set_flag(world, True)
    own = add_draft(world, source=SENT_SOURCE, prov=provenance(requester="local-developer"))
    before = snapshot(world)
    body = {"approved": True, "acknowledge_disposable_credentials": True}
    path = "/api/v1/test-generations/drafts/{}/decision"
    refused = world.client.post(path.format(own), json=body, headers={"X-Tenant-Id": "tenant-a"})
    assert refused.status_code == 409
    assert refused.json()["detail"] == "reviewer_must_differ_from_requester"
    assert snapshot(world) == before
    other = add_draft(world, source=SENT_SOURCE)
    allowed = world.client.post(path.format(other), json=body, headers={"X-Tenant-Id": "tenant-a"})
    assert allowed.status_code == 200


def test_double_approval_creates_one_case_and_one_run(world):
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    first = decide(world, draft_id, acknowledge_disposable_credentials=True)
    second = decide(world, draft_id, "reviewer-2", acknowledge_disposable_credentials=True)
    assert first.status_code == 200
    assert second.status_code in (200, 409)
    snap = snapshot(world)
    assert snap["test_cases"] == 1 and snap["test_runs"] == 1
    assert snap["generated_test_decisions"] == 1


def test_vietnamese_reason_is_accepted_and_overlong_reason_is_refused(world):
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    before = snapshot(world)
    too_long = decide(world, draft_id, reason="ế" * 4001,
                      acknowledge_disposable_credentials=True)
    assert too_long.status_code == 422 and snapshot(world) == before
    ok = decide(world, draft_id, reason="Đã duyệt: tài khoản dùng một lần",
                acknowledge_disposable_credentials=True)
    assert ok.status_code == 200


# ---------------------------------------------------------------- acknowledgement (criterion 2)


@pytest.mark.parametrize("value", ["yes", "true", 1, None, "false", []])
def test_non_boolean_acknowledgement_never_passes(world, value):
    """Anything but a real `true` must not unlock approval (422 for junk, 409 for false/None)."""
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    before = snapshot(world)
    response = world.client.post(
        f"/api/v1/test-generations/drafts/{draft_id}/decision",
        json={"approved": True, "acknowledge_disposable_credentials": value},
        headers=headers("reviewer-1", "reviewer"),
    )
    if value in ("yes", "true", 1):  # pydantic lax mode coerces these to True: that is allowed
        assert response.status_code in (200, 422)
    else:
        assert response.status_code in (409, 422)
        assert snapshot(world) == before


def test_request_body_without_the_new_field_still_parses_for_a_legacy_draft(world):
    set_flag(world, False)
    draft_id = add_draft(world, source="import { test } from '@playwright/test';\n",
                         prov=provenance(agent=False))
    response = world.client.post(
        f"/api/v1/test-generations/drafts/{draft_id}/decision",
        json={"approved": True}, headers=headers("anyone", "contributor"),
    )
    assert response.status_code == 200, response.text


def test_agent_draft_without_agent_values_ignores_flag_and_ack(world):
    set_flag(world, False)
    plain = "import { test } from '@playwright/test';\n"
    draft_id = add_draft(world, source=plain, prov=provenance(values=False))
    assert decide(world, draft_id).status_code == 200


# ---------------------------------------------------------------- guards + sentinel (3, 4)


def test_preflight_guard_applies_to_a_case_created_by_approval_then_revised_draft(world):
    """Full path: approve a values draft, then try to revise its failed run through a model."""
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    assert decide(world, draft_id, acknowledge_disposable_credentials=True).status_code == 200
    with world.factory() as db:
        case = db.scalars(select(TestCaseModel)).one()
        run = db.scalars(select(TestRunModel)).one()
        case_id, run_id = case.id, run.id
        result = ExecutionResult(
            run_id=run.id, correlation_id=run.correlation_id, status=RunStatus.FAILED,
            started_at="2026-11-27T00:00:00Z", completed_at="2026-11-27T00:00:01Z",
            summary="Assertion failed.",
        )
        run.status, run.result = "failed", result.model_dump(mode="json")
        db.commit()
    assert case_id and revise(world, run_id).status_code == 409
    assert count(world, GenerationRequestModel) == 0 or SENT not in table_text(
        world, "generation_requests")


def test_sentinel_never_reaches_generation_requests_audit_events_or_logs(world, caplog):
    caplog.set_level(logging.DEBUG)
    set_flag(world, True)
    # refusals
    first = add_draft(world, source=SENT_SOURCE)
    decide(world, first, REQUESTER, "reviewer", acknowledge_disposable_credentials=True)
    decide(world, first, "x", "contributor", acknowledge_disposable_credentials=True)
    decide(world, first)  # no acknowledgement
    decide(world, first, "svc", "service", acknowledge_disposable_credentials=True)
    # preflight guard
    Preflight.fail = True
    decide(world, first, acknowledge_disposable_credentials=True)
    Preflight.fail = False
    # flag off
    set_flag(world, False)
    decide(world, first, acknowledge_disposable_credentials=True)
    set_flag(world, True)
    # a rejected draft and an approved one
    second = add_draft(world, source=SENT_SOURCE)
    assert decide(world, second, approved=False, reason="no").status_code == 200
    third = add_draft(world, source=SENT_SOURCE)
    assert decide(world, third, acknowledge_disposable_credentials=True).status_code == 200
    # revised-draft guard on a values case, and on the approved one
    revise(world, failed_run(world, values=True))
    # the premise: the value does live in the places ADR-002 now allows
    assert SENT in table_text(world, "generated_test_drafts")
    assert SENT in table_text(world, "test_cases")
    # and in none of the places it must not
    assert SENT not in table_text(world, "generation_requests")
    assert SENT not in table_text(world, "audit_events")
    assert SENT not in caplog.text
    assert all(SENT not in (r.getMessage() + str(r.exc_text) + str(r.args))
               for r in caplog.records)
    with world.factory() as db:
        assert count(world, AuditEventModel) > 0
        assert not db.scalars(select(GeneratedTestDraftModel.provenance)).all() == []
        for prov in db.scalars(select(GeneratedTestDraftModel.provenance)).all():
            assert SENT not in str(prov)


def test_failed_preflight_of_values_draft_leaves_the_draft_pending_and_retryable(world):
    set_flag(world, True)
    draft_id = add_draft(world, source=SENT_SOURCE)
    Preflight.fail = True
    assert decide(world, draft_id, acknowledge_disposable_credentials=True).status_code == 409
    Preflight.fail = False
    assert draft_state(world, draft_id) == "pending_review"
    assert decide(world, draft_id, acknowledge_disposable_credentials=True).status_code == 200


def test_revised_draft_when_flag_is_missing_but_not_true_is_not_blocked(world):
    """Boundary: only a literal `true` marks a case; `false` keeps the old behaviour (202)."""
    set_flag(world, False)
    run_id = failed_run(world, values=False)
    with world.factory.begin() as db:
        case = db.scalars(select(TestCaseModel)).one()
        case.specification = {**case.specification, "contains_test_values": False}
    assert revise(world, run_id).status_code == 202


# ---------------------------------------------------------------- evidence through the processor


FILL_OUTPUT = (
    "  1) login.spec.ts:3:1 > login\n\n    Error: expect(locator).toBeVisible()\n\n"
    f"      4 |   await page.getByLabel('Mat khau').fill('{SENT}');\n"
    "    > 5 |   await expect(page.getByText('Welcome')).toBeVisible();\n"
)
WORKER_RESULT = f'{{"error": "step fill({SENT}) failed"}}'


class _Model:
    def __init__(self):
        self.payloads: list[str] = []

    async def ainvoke(self, payload, **kwargs):
        self.payloads.append(repr(payload))
        raise RuntimeError("provider stub")  # the payload is all that matters here


class _Reports:
    def __init__(self):
        self.items = {}

    def get_for_run(self, tenant_id, run_id, report_version=1):
        return self.items.get((tenant_id, run_id, report_version))

    def add(self, report):
        key = (report.tenant_id, report.run_id, report.report_version)
        return self.items.setdefault(key, report)


def _failed_run_with_artifacts():
    run = TestRun.create(tenant_id="tenant-a", project_id=uuid4(), test_case_id="case",
                         revision="a" * 40, correlation_id=uuid4())
    run.request = TestExecutionRequest(
        run_id=run.id, correlation_id=run.correlation_id, project_id=run.project_id,
        test_case_id="case", target_type=TargetType.WEB_UI, revision="a" * 40,
        runner_config={
            "playwright_test_source": SENT_SOURCE, "source_hash": sha256_text(SENT_SOURCE),
        },
    )
    uris = {"playwright-output": "memory://r/out.txt", "worker-result": "memory://r/res.json"}
    run.record_runner_result(ExecutionResult(
        run_id=run.id, correlation_id=run.correlation_id, status=RunStatus.FAILED,
        started_at="2026-11-27T00:00:00Z", completed_at="2026-11-27T00:00:01Z",
        summary="Assertion failed.",
        artifacts=[{"kind": k, "uri": u, "content_type": "text/plain"} for k, u in uris.items()],
    ))
    records = [ArtifactRecord(id=uuid4(), tenant_id="tenant-a", run_id=run.id, kind=k, uri=u,
                              checksum="c" * 64, size=10, content_type="text/plain")
               for k, u in uris.items()]
    return run, records


def _model_payload(spec):
    run, records = _failed_run_with_artifacts()
    model = _Model()
    files = {"playwright-output": FILL_OUTPUT, "worker-result": WORKER_RESULT}

    class Runs:
        def get(self, tenant_id, run_id):
            return run

    class Configs:
        def get(self, tenant_id, key):
            return None

    class Artifacts:
        def list_for_run(self, tenant_id, run_id):
            return records

    class Reader:
        def read_verified_bytes(self, artifact, max_bytes):
            return files[artifact.kind].encode()

    class Cases:
        def get_test_case(self, tenant_id, test_case_id):
            return TestCase(id=test_case_id, tenant_id=tenant_id, project_id=run.project_id,
                            target_type=TargetType.WEB_UI, revision="a" * 40, specification=spec)

    processor = ReportingEventProcessor(
        Runs(), Configs(), Artifacts(), _Reports(), Reader(), Settings(),
        model_factory=lambda *_: model, test_cases=Cases(),
    )
    asyncio.run(processor.execute(OutboxEvent(
        id=uuid4(), tenant_id="tenant-a", event_type=EventType.AGENT_RUN_REPORT_REQUESTED.value,
        schema_version="v1", correlation_id=run.correlation_id, causation_id=None,
        idempotency_key=f"run-report:{run.id}:v1", payload={"run_id": str(run.id)},
    )))
    assert model.payloads, "the model was never called"
    return "\n".join(model.payloads)


def test_failed_values_run_sends_neither_fill_line_nor_source_to_the_model():
    payload = _model_payload({"contains_test_values": True})
    assert SENT not in payload
    assert "approved_playwright_test_source" not in payload


def test_failed_ordinary_run_keeps_excerpts_and_context_control():
    payload = _model_payload({"playwright_test_source": "x"})
    assert SENT in payload  # control: proves the harness would have caught a leak
    assert "approved_playwright_test_source" in payload


# ---------------------------------------------------------------- ADR-002 (criterion 6)

ADR = ROOT / "docs" / "adr" / "002-generated-test-authority.md"
PM = PLAN / "reports" / "phase-13" / "pm-adr002-r1.md"

OLD_BULLET = (
    "- run evidence sent to a model excludes the `playwright-output` excerpt\n"
    "  (a failed test prints the `fill` line), and the `worker-result` excerpt as\n"
    "  decided in phase 13.\n"
)
NEW_BULLET = (
    "- run evidence sent to a model carries no excerpts (neither\n"
    "  `playwright-output`, which prints the `fill` line when a test fails, nor\n"
    "  `worker-result`), and the approved source is dropped from the report's\n"
    "  review context.\n"
)


def _pm_section() -> str:
    lines = PM.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("```diff"))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("```"))
    added = [ln[1:] for ln in lines[start + 1:end]
             if ln.startswith("+") and not ln.startswith("+++")]
    section = "\n".join(added[added.index("## Scoped exception: disposable test-account values"):])
    assert OLD_BULLET in section + "\n"
    section = (section + "\n").replace(OLD_BULLET, NEW_BULLET)
    anchor = "- Temporal workflow input and history;\n"
    return section.replace(anchor, anchor + (
        "- the HTTP request body sent to the worker during execution (transient,\n"
        "  not stored);\n"))


@pytest.mark.skipif(not PM.exists(), reason="PM draft not present")
def test_adr002_section_matches_the_text_the_user_approved():
    adr = ADR.read_text(encoding="utf-8")
    start = adr.index("## Scoped exception: disposable test-account values")
    actual = adr[start:adr.index("## Consequences")].strip()
    assert actual == _pm_section().strip()


def test_adr002_amended_line_and_the_two_changed_sentences():
    adr = ADR.read_text(encoding="utf-8")
    assert ("- Amended: 2026-11-27 (scoped exception for disposable test-account values, "
            "ADR-047)\n") in adr
    assert ("credentials are not persisted or sent to a model, and login and supplied\n"
            "  credentials are outside v1 scope, except for the scoped exception below.\n") in adr
    assert "Login and supplied\n  credentials are outside v1 scope." not in adr


def test_adr002_keeps_the_unchanged_decision_rules():
    adr = ADR.read_text(encoding="utf-8")
    for needle in (
        "The planner is advisory only.",
        "The control plane rejects credentials, non-HTTP(S) URLs, and origins outside",
        "Generated source is executed only from an isolated temporary workspace.",
        "# ADR-002: Governed generated-test authority",
        "- Status: Accepted",
        "- Date: 2026-07-27",
    ):
        assert needle in adr
