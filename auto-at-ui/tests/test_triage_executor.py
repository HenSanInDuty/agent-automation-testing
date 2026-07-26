import asyncio
from uuid import uuid4

from agents.shared.runtime import AgentRuntimeConfig, StepGuardPolicy
from agents.triage.executor import execute_triage
from auto_at.contracts.execution import RunStatus
from auto_at.contracts.execution import TestExecutionResult as ExecutionResult


class FakeModel:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = 0

    async def ainvoke(self, payload: object, **kwargs: object) -> object:
        self.calls += 1
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def failed_result() -> ExecutionResult:
    return ExecutionResult(
        run_id=uuid4(),
        correlation_id=uuid4(),
        status=RunStatus.FAILED,
        started_at="2026-07-26T00:00:00Z",
        completed_at="2026-07-26T00:00:01Z",
        summary="Save button was not found.",
    )


def runtime(*, fallback: bool = False) -> AgentRuntimeConfig:
    values: dict[str, object] = {
        "provider": "openrouter",
        "model": "openai/gpt-5-mini",
        "guard": StepGuardPolicy(
            max_tokens=100,
            max_steps_per_run=2,
            max_evidence_bytes_per_step=10_000,
        ).model_dump(),
    }
    if fallback:
        values["fallback"] = {"provider": "openrouter", "model": "google/gemini-flash"}
    return AgentRuntimeConfig.model_validate(values)


def test_triage_executor_produces_only_an_advisory_proposal() -> None:
    model = FakeModel(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"category":"test","confidence":0.8,'
                            '"rationale":"Locator changed."}'
                        )
                    }
                }
            ]
        }
    )

    outcome = asyncio.run(execute_triage(failed_result(), runtime(), model))

    assert outcome.status == "proposed"
    assert outcome.proposal is not None
    assert outcome.proposal.proposed_change is None
    assert outcome.triage is not None
    assert outcome.triage.category == "test"


def test_triage_executor_uses_configured_fallback_then_reports_unavailable() -> None:
    primary = FakeModel(RuntimeError("gateway down"))
    fallback = FakeModel(RuntimeError("fallback down"))

    outcome = asyncio.run(
        execute_triage(failed_result(), runtime(fallback=True), primary, fallback)
    )

    assert outcome.status == "unavailable"
    assert outcome.proposal is None
    assert primary.calls == 1
    assert fallback.calls == 1
