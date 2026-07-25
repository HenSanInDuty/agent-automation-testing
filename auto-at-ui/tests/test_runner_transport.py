from uuid import uuid4

import pytest
from auto_at.contracts.execution import TargetType
from auto_at.contracts.execution import TestExecutionRequest as ExecutionRequest
from infrastructure.runners import HttpPlaywrightTransport, RunnerUnavailableError


def test_transport_logs_correlation_data_when_the_worker_times_out(monkeypatch, caplog) -> None:
    request = ExecutionRequest(
        run_id=uuid4(),
        correlation_id=uuid4(),
        project_id=uuid4(),
        test_case_id="timeout-check",
        target_type=TargetType.WEB_UI,
        revision="a" * 40,
    )

    def timed_out(*args, **kwargs):
        raise TimeoutError("worker timed out")

    monkeypatch.setattr("infrastructure.runners.urlopen", timed_out)

    with pytest.raises(RunnerUnavailableError, match="timed out"):
        HttpPlaywrightTransport("http://worker", timeout_seconds=12).execute(request)

    assert f"run_id={request.run_id}" in caplog.text
    assert f"correlation_id={request.correlation_id}" in caplog.text
    assert "timeout_seconds=12" in caplog.text
