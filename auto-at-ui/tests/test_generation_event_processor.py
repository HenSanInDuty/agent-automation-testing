import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

from application.generation_events import GenerationEventProcessor
from auto_at.contracts.generation import request_hash
from config import Settings
from domain.runs import OutboxEvent


class Repository:
    def __init__(self, request, policy) -> None:
        self.request = request
        self.policy = policy
        self.draft = None

    def claim_queued_request(self, tenant_id, request_id):
        if self.request.state != "queued":
            return None
        self.request.state = "generating"
        return self.request

    def get_request(self, tenant_id, request_id):
        return self.request

    def get_policy(self, tenant_id, project_id):
        return self.policy

    def get_draft_for_request(self, tenant_id, request_id):
        return self.draft

    def add_draft(self, draft):
        self.draft = draft


class Audits:
    def __init__(self) -> None:
        self.events = []

    def append(self, event) -> None:
        self.events.append(event)


class Configurations:
    def get(self, tenant_id, key):
        return None


class Model:
    def __init__(self, source: str) -> None:
        self.source = source

    async def ainvoke(self, payload, **kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "title": "Home page",
                                "playwright_test_source": self.source,
                                "assumptions": [],
                                "stop_conditions": [],
                            }
                        )
                    }
                }
            ]
        }


def event(request) -> OutboxEvent:
    return OutboxEvent(
        id=uuid4(),
        tenant_id="tenant-a",
        event_type="agent.test_generation.requested.v1",
        schema_version="v1",
        correlation_id=request.correlation_id,
        causation_id=None,
        idempotency_key="generation:one",
        payload={"request_id": str(request.id)},
    )


def request():
    return SimpleNamespace(
        id=uuid4(),
        tenant_id="tenant-a",
        project_id=uuid4(),
        correlation_id=uuid4(),
        target_url="https://example.test/home",
        redacted_request="Check the home page",
        request_hash=request_hash("Check the home page"),
        state="queued",
        failure_reason=None,
    )


def test_fixture_planner_completes_one_reviewable_draft(monkeypatch) -> None:
    item = request()
    repository = Repository(item, SimpleNamespace(allowed_origins=["https://example.test"]))
    audits = Audits()
    source = """import { test, expect } from '@playwright/test';
test('checks every visible enabled button', async ({ page }) => {
  await page.goto('https://example.test/home');
  const buttons = page.getByRole('button');
  const count = await buttons.count();
  expect(count).toBeGreaterThan(0);
  for (let index = 0; index < count; index += 1) {
    const button = buttons.nth(index);
    await expect(button).toBeVisible();
    await expect(button).toBeEnabled();
    await button.click();
  }
});"""
    monkeypatch.setattr(
        "application.generation_events.create_language_model", lambda *_: Model(source)
    )
    processor = GenerationEventProcessor(repository, Configurations(), audits, Settings())

    assert asyncio.run(processor.execute(event(item))) == "completed"
    assert item.state == "completed"
    assert repository.draft.title == "Home page"
    assert repository.draft.source_hash
    assert {audit.action for audit in audits.events} == {
        "generation.claimed",
        "generation.completed",
    }
    assert asyncio.run(processor.execute(event(item))) == "already_processed"


def test_policy_violation_fails_without_a_draft(monkeypatch) -> None:
    item = request()
    repository = Repository(item, SimpleNamespace(allowed_origins=["https://example.test"]))
    audits = Audits()
    monkeypatch.setattr(
        "application.generation_events.create_language_model",
        lambda *_: Model("import { readFile } from 'node:fs';"),
    )

    outcome = asyncio.run(
        GenerationEventProcessor(repository, Configurations(), audits, Settings()).execute(
            event(item)
        )
    )

    assert outcome == "failed"
    assert item.state == "failed"
    assert item.failure_reason == "generation output failed source safety validation"
    assert repository.draft is None
    assert {audit.action for audit in audits.events} == {"generation.claimed", "generation.failed"}


def test_malformed_model_output_reports_a_safe_structure_failure(monkeypatch) -> None:
    item = request()
    repository = Repository(item, SimpleNamespace(allowed_origins=["https://example.test"]))
    audits = Audits()
    class MalformedModel:
        async def ainvoke(self, payload, **kwargs):
            return {"choices": [{"message": {"content": "not JSON"}}]}

    monkeypatch.setattr(
        "application.generation_events.create_language_model", lambda *_: MalformedModel()
    )

    outcome = asyncio.run(
        GenerationEventProcessor(repository, Configurations(), audits, Settings()).execute(
            event(item)
        )
    )

    assert outcome == "failed"
    assert item.failure_reason == "generation output did not match the required structured format"
