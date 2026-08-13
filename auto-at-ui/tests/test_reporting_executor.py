import asyncio
from uuid import uuid4

from agents.reporting.executor import execute_run_reporting
from agents.shared.evidence import build_run_report_evidence_bundle
from agents.shared.runtime import AgentRuntimeConfig, EvidencePolicy, StepGuardPolicy
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


class NoArtifacts:
    def read_verified_bytes(self, artifact: object, max_bytes: int) -> bytes:
        raise AssertionError("no artifacts should be read")


def result(status: RunStatus = RunStatus.FAILED) -> ExecutionResult:
    return ExecutionResult(
        run_id=uuid4(),
        correlation_id=uuid4(),
        status=status,
        started_at="2026-08-13T00:00:00Z",
        completed_at="2026-08-13T00:00:01Z",
        summary="Checkout assertion failed.",
    )


def runtime(max_evidence_bytes: int = 10_000) -> AgentRuntimeConfig:
    return AgentRuntimeConfig.model_validate(
        {
            "provider": "openrouter",
            "model": "openai/gpt-5-mini",
            "guard": StepGuardPolicy(
                max_tokens=100,
                max_steps_per_run=1,
                max_evidence_bytes_per_step=max_evidence_bytes,
            ).model_dump(),
        }
    )


def test_reporting_executor_preserves_the_deterministic_failure_status() -> None:
    execution = result()
    evidence = build_run_report_evidence_bundle(execution, EvidencePolicy(), [], NoArtifacts())
    model = FakeModel(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"deterministic_status":"failed","headline":"Checkout failed.",'
                            '"what_ran":"One checkout test ran.","observations":[],'
                            '"failure":{"stage":"assertion","location":"checkout.spec.ts:42:3",'
                            '"message":"Expected total.","evidence_references":[]},'
                            '"unverified_or_skipped":[],"limitations":[]}'
                        )
                    }
                }
            ]
        }
    )

    outcome = asyncio.run(execute_run_reporting(execution, evidence, runtime(), model))

    assert outcome.status == "completed"
    assert outcome.report is not None
    assert outcome.report.deterministic_status == "failed"
    assert outcome.report.failure is not None
    assert outcome.report.failure.location == "checkout.spec.ts:42:3"


def test_reporting_executor_returns_unavailable_for_invalid_output_or_guard_exhaustion() -> None:
    execution = result(RunStatus.PASSED)
    execution.summary = "x" * 4_000
    evidence = build_run_report_evidence_bundle(execution, EvidencePolicy(), [], NoArtifacts())
    invalid = FakeModel(
        {"choices": [{"message": {"content": '{"deterministic_status":"failed"}'}}]}
    )

    invalid_outcome = asyncio.run(execute_run_reporting(execution, evidence, runtime(), invalid))
    guard_outcome = asyncio.run(execute_run_reporting(execution, evidence, runtime(1_024), invalid))

    assert invalid_outcome.status == "unavailable"
    assert guard_outcome.status == "unavailable"
    assert invalid.calls == 1
