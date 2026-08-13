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


def test_transport_posts_an_idempotent_cancellation_command(monkeypatch) -> None:
    observed: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def request(url, data, headers):
        observed["url"] = url
        observed["data"] = data
        observed["headers"] = headers
        return object()

    def opened(value, timeout):
        observed["request"] = value
        observed["timeout"] = timeout
        return Response()

    monkeypatch.setattr("infrastructure.runners.Request", request)
    monkeypatch.setattr("infrastructure.runners.urlopen", opened)

    HttpPlaywrightTransport("http://worker", timeout_seconds=12).cancel("run-1")

    assert observed["url"] == "http://worker/cancel"
    assert observed["data"] == b'{"run_id": "run-1"}'
    assert observed["timeout"] == 12


def test_transport_keeps_progress_metadata_outside_the_execution_contract(monkeypatch) -> None:
    request = ExecutionRequest(
        run_id=uuid4(), correlation_id=uuid4(), project_id=uuid4(), test_case_id="generated",
        target_type=TargetType.WEB_UI, revision="a" * 40,
        runner_config={"mode": "playwright_test_source"},
    )
    observed: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return (
                b'{"contract_version":"v1","run_id":"'
                + str(request.run_id).encode()
                + b'","correlation_id":"'
                + str(request.correlation_id).encode()
                + b'","status":"passed","started_at":"now","completed_at":"now",'
                + b'"summary":"ok","artifacts":[],"runner_metadata":{}}'
            )

    def build_request(url, data, headers):
        observed.update(url=url, data=data, headers=headers)
        return object()

    monkeypatch.setattr("infrastructure.runners.Request", build_request)
    monkeypatch.setattr("infrastructure.runners.urlopen", lambda *_args, **_kwargs: Response())

    HttpPlaywrightTransport("http://worker", progress_tenant_id="tenant-a").execute(request)

    assert observed["headers"] == {
        "Content-Type": "application/json",
        "X-Auto-AT-Progress-Tenant-ID": "tenant-a",
    }
    assert b"internal_progress_tenant_id" not in observed["data"]
