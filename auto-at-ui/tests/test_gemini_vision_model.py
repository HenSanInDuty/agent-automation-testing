import asyncio
import json
import logging
from base64 import b64decode, b64encode

import httpx
import pytest
from agents.shared.gemini import GEMINI_CHAT_COMPLETIONS_URL, GeminiVisionLanguageModel
from agents.shared.runtime import VisionPolicy
from agents.vision.diagnostics import VisionProviderFailure
from agents.vision.executor import execute_visual_candidate_batch

MODEL = "gemini-3.8-flash"
KEY = "AIza" + "syntheticKEY_" * 3
PNG = b"\x89PNG\r\n\x1a\nsynthetic-pixels-only"
CONTENT = json.dumps({"candidates": [
    {"kind": "click", "x": 0.3, "y": 0.6, "confidence": 0.9,
     "expected_outcome": "Custom div control opens dialog"},
]})
REPLY = {"choices": [{"finish_reason": "stop", "message": {"content": CONTENT}}]}


def invoke(handler, **options):
    model = GeminiVisionLanguageModel(
        api_key=options.pop("api_key", KEY), model=MODEL,
        transport=httpx.MockTransport(handler), **options,
    )
    return asyncio.run(execute_visual_candidate_batch(
        screenshot=PNG, content_type="image/png", task_intent="Check custom controls",
        policy=VisionPolicy(
            enabled=True, provider="gemini", model=MODEL,
            raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider="gemini",
        ), model=model, max_candidates=2,
    ))


def test_gemini_request_is_exact_and_inline(caplog):
    requests = []

    def handler(request):
        requests.append(request)
        assert str(request.url) == GEMINI_CHAT_COMPLETIONS_URL
        assert request.method == "POST"
        assert request.headers["authorization"] == f"Bearer {KEY}"
        body = json.loads(request.content)
        assert set(body) == {
            "model", "messages", "max_tokens", "temperature", "response_format", "reasoning_effort",
        }
        assert body["model"] == MODEL
        assert body["response_format"] == {"type": "json_object"}
        assert body["reasoning_effort"] == "low"
        assert body["max_tokens"] == 1000 and body["temperature"] == 0
        image = body["messages"][1]["content"][1]["image_url"]["url"]
        assert image.startswith("data:image/png;base64,")
        assert b64decode(image.partition(",")[2]) == PNG
        assert "custom controls" in body["messages"][0]["content"]
        assert 0 < request.extensions["timeout"]["read"] <= 30
        return httpx.Response(200, json=REPLY)

    with caplog.at_level(logging.DEBUG):
        outcome = invoke(handler)
    assert outcome.status == "completed"
    assert outcome.actions[0].kind == "click"
    assert len(requests) == 1
    assert KEY not in caplog.text + repr(outcome)
    assert b64encode(PNG).decode() not in caplog.text + repr(outcome)


def test_untrusted_payload_and_kwargs_cannot_override_transport_or_model():
    def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == GEMINI_CHAT_COMPLETIONS_URL
        assert request.headers["authorization"] == f"Bearer {KEY}"
        assert body == {
            "model": MODEL, "messages": [], "max_tokens": 10, "temperature": 0,
            "reasoning_effort": "low", "response_format": {"type": "json_object"},
        }
        return httpx.Response(200, json=REPLY)

    model = GeminiVisionLanguageModel(
        api_key=KEY, model=MODEL, transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(model.ainvoke(
        {"model": "wrong", "messages": [], "max_tokens": 10, "tools": [{}],
         "reasoning_effort": "high", "response_format": {}, "stream": True,
         "authorization": "wrong", "url": "https://untrusted.invalid"},
        model="wrong", headers={"authorization": "wrong"}, max_tokens=99999,
        base_url="https://untrusted.invalid", reasoning_effort="none",
    ))
    assert result == REPLY


@pytest.mark.parametrize(("status", "reason"), [
    (401, "provider_auth_failed"), (403, "provider_auth_failed"),
    (402, "provider_billing_required"), (404, "provider_model_unavailable"),
    (429, "provider_rate_limited"), (500, "provider_unavailable"),
    (503, "provider_unavailable"), (400, "provider_unavailable"),
    (302, "provider_unavailable"),
])
def test_http_failures_are_safe_and_never_retried_or_redirected(status, reason, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status, text=f"private-provider-body {KEY}",
            headers={"location": "https://untrusted.invalid", "retry-after": "1"},
        )

    with caplog.at_level(logging.DEBUG):
        outcome = invoke(handler)
    assert len(requests) == 1
    assert outcome.status == "unavailable" and outcome.actions is None
    assert outcome.failure_reason == reason
    assert outcome.diagnostic_capture.provider_status == status
    assert outcome.diagnostic_capture.content is None
    assert KEY not in repr(outcome) + caplog.text
    assert "private-provider-body" not in repr(outcome) + caplog.text


@pytest.mark.parametrize(("error", "reason"), [
    (httpx.ReadTimeout("private"), "provider_timeout"),
    (httpx.ConnectError("private"), "provider_unavailable"),
])
def test_transport_errors_are_classified(error, reason):
    calls = []

    def handler(request):
        calls.append(request)
        raise error

    outcome = invoke(handler)
    assert outcome.failure_reason == reason and len(calls) == 1
    assert "private" not in repr(outcome)


@pytest.mark.parametrize(("options", "reason"), [
    ({"api_key": None}, "provider_not_configured"),
    ({"timeout_seconds": 0}, "provider_timeout"),
    ({"timeout_seconds": -1}, "provider_timeout"),
])
def test_missing_key_or_expired_deadline_never_calls_http(options, reason):
    def handler(_):
        pytest.fail("must reject before network")

    assert invoke(handler, **options).failure_reason == reason


def test_timeout_cancels_a_pending_request_once():
    cancelled = []

    async def handler(_):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    outcome = invoke(handler, timeout_seconds=0.03)
    assert outcome.failure_reason == "provider_timeout"
    assert cancelled == [True]


def test_external_cancellation_propagates():
    async def scenario():
        started = asyncio.Event()

        async def handler(_):
            started.set()
            await asyncio.Event().wait()

        model = GeminiVisionLanguageModel(
            api_key=KEY, model=MODEL, transport=httpx.MockTransport(handler),
        )
        task = asyncio.create_task(model.ainvoke({"messages": [], "max_tokens": 10}))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(scenario())


@pytest.mark.parametrize("tokens", [0, -1, 100001, True, "1000", None])
def test_adapter_rejects_invalid_token_cap(tokens):
    model = GeminiVisionLanguageModel(
        api_key=KEY, model=MODEL,
        transport=httpx.MockTransport(lambda _: pytest.fail("invalid cap reached HTTP")),
    )
    with pytest.raises(ValueError, match="token cap"):
        asyncio.run(model.ainvoke({"messages": [], "max_tokens": tokens}))


def test_malformed_http_json_is_invalid_output_without_capturing_body():
    outcome = invoke(lambda _: httpx.Response(200, text=f"not JSON {KEY}"))
    assert outcome.failure_reason == "model_output_invalid"
    assert outcome.diagnostic_capture.content is None


def test_adapter_exception_does_not_retain_http_request_or_body():
    model = GeminiVisionLanguageModel(
        api_key=KEY, model=MODEL,
        transport=httpx.MockTransport(lambda _: httpx.Response(403, text=KEY)),
    )
    with pytest.raises(VisionProviderFailure) as error:
        asyncio.run(model.ainvoke({"messages": [], "max_tokens": 10}))
    assert str(error.value) == "provider_auth_failed"
    assert not hasattr(error.value, "request") and not hasattr(error.value, "response")
    assert KEY not in repr(error.value)
