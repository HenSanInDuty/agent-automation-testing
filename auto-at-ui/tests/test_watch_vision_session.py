"""Quiet polling must not submit work, leak responses or turn a timeout into success."""

import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "watch_vision_session", Path(__file__).parents[1] / "scripts/watch_vision_session.py",
)
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


def run_watch(states, *, changes=False, timeout=30, status=200, invalid=False):
    session = str(uuid4())
    calls, output, ticks = [], [], [0]
    states = iter(states)

    def handle(request):
        calls.append(request)
        return httpx.Response(status, json={
            "id": str(uuid4()) if invalid else session, "state": next(states),
            "safe_failure_reason": "private-data", "intent": "private-data",
        })

    def sleep(seconds):
        ticks[0] += seconds

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(handle)) as client:
        code = watcher.watch(client, session, interval=10, timeout=timeout, changes=changes,
                             emit=output.append, clock=lambda: ticks[0], sleep=sleep)
    assert all(r.method == "GET" and r.url.path.endswith(session) for r in calls)
    assert "private-data" not in json.dumps(output)
    return code, output, calls


@pytest.mark.parametrize("terminal", ["completed", "cancelled", "unavailable"])
def test_default_emits_only_terminal_without_masking_state(terminal):
    code, output, calls = run_watch(["queued", "running", terminal])
    assert code == 0 and len(calls) == 3
    assert len(output) == 1
    assert output[0]["event"] == "terminal" and output[0]["state"] == terminal


def test_changes_suppresses_duplicate_polls():
    code, output, _ = run_watch(["queued", "queued", "running", "running", "completed"],
                                changes=True, timeout=60)
    assert code == 0
    assert [row["state"] for row in output] == ["queued", "running", "completed"]


def test_deadline_does_not_cancel_or_report_success():
    code, output, calls = run_watch(["running"] * 3, timeout=25)
    assert code == 2 and len(calls) == 3
    assert len(output) == 1 and output[0]["event"] == "monitor_timeout"


@pytest.mark.parametrize("status", [401, 403, 429, 500])
def test_http_failure_is_redacted_and_not_retried(status):
    code, output, calls = run_watch(["running"], status=status)
    assert code == 1 and len(calls) == 1
    assert output[0]["event"] == "http_failure" and output[0]["status"] == status


def test_wrong_session_is_rejected():
    code, output, calls = run_watch(["completed"], invalid=True)
    assert code == 1 and len(calls) == 1
    assert output[0]["event"] == "invalid_response"


def test_unknown_state_is_rejected():
    code, output, _ = run_watch(["unexpected"])
    assert code == 1 and output[0]["event"] == "invalid_response"


def test_transport_timeout_is_redacted_and_not_retried():
    calls, output = [], []

    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout("private-provider-detail", request=request)

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(fail)) as client:
        code = watcher.watch(client, uuid4(), emit=output.append)
    assert code == 1 and len(calls) == 1
    assert output[0]["event"] == "http_failure"
    assert "private-provider-detail" not in json.dumps(output)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_invalid_interval_is_rejected_before_network_io(value):
    with pytest.raises(ValueError):
        watcher.watch(None, uuid4(), interval=value)
