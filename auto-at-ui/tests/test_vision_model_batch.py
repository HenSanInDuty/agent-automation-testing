import asyncio
import json
from base64 import b64decode
from functools import partial
from uuid import uuid4

import httpx
import pytest
from agents.shared.openrouter import create_vision_language_model
from agents.shared.runtime import AgentStepGuard, StepGuardPolicy, VisionPolicy
from agents.vision.executor import policy_to_step_guard
from agents.vision.temporary_images import GoogleDriveTemporaryVisionImageStore
from application.vision_model_batch import VisionModelSession
from config import Settings
from domain.vision import VisionImageAuthorizationRequired
from infrastructure.vision.model_batch import VisionModelBatch

PNG = b"\x89PNG\r\n\x1a\nsynthetic screenshot"
REPLY = {"choices": [{"message": {"content": json.dumps({"candidates": [
    {"kind": "click", "x": 0.1, "y": 0.5, "confidence": 0.9,
     "expected_outcome": "Custom span opens menu"},
]})}}]}


def settings(**changes):
    return Settings(**{
        "_env_file": None, "gemini_api_key": "fixture-gemini-key",
        "huggingface_api_key": "fixture-hf-key",
        "huggingface_base_url": "https://hf.invalid/v1",
        "google_drive_service_account_file": None,
        "GOOGLE_DRIVE_OAUTH_CLIENT_ID": "fixture-client",
        "GOOGLE_DRIVE_OAUTH_CLIENT_SECRET": "fixture-secret",
        "GOOGLE_DRIVE_OAUTH_REFRESH_TOKEN": "expired-refresh",
        "google_drive_vision_folder_id": "fixture-folder",
        "google_drive_vision_delete_after_delivery": True,
        **changes,
    })


def options(provider="gemini", **changes):
    policy = VisionPolicy(
        enabled=True, provider=provider,
        model="gemini-3.8-flash" if provider == "gemini" else "Qwen/Qwen3.8-27B:deepinfra",
        raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider=provider,
    )
    return {
        "session": VisionModelSession("tenant-fixture", uuid4(), policy.provider, policy.model),
        "screenshot": PNG, "task_intent": "Exercise controls", "policy": policy,
        "max_candidates": 2, "guard": AgentStepGuard(policy_to_step_guard(policy)),
        "sequence": 1, "check_policy": lambda: None, "remaining_seconds": 5,
        **changes,
    }


def no_drive(**_):
    pytest.fail("Gemini must never construct a Drive store")


def test_gemini_succeeds_without_drive_and_only_uses_gemini_key():
    checks = []
    requests = []

    def handler(request):
        requests.append(request)
        assert checks == ["checked"]
        assert request.headers["authorization"] == "Bearer fixture-gemini-key"
        assert request.url.host == "generativelanguage.googleapis.com"
        body = json.loads(request.content)
        assert body["max_tokens"] == 1000
        assert body["response_format"]["type"] == "json_schema"
        schema = body["response_format"]["json_schema"]["schema"]
        candidates = schema["properties"]["candidates"]
        assert candidates["minItems"] == 1 and candidates["maxItems"] == 2
        variants = candidates["items"]["anyOf"]
        assert len(variants) == 5
        for variant in variants:
            assert "kind" in variant["required"]
            assert variant["additionalProperties"] is False
            if variant["properties"]["kind"]["enum"][0] in {"click", "type"}:
                for axis in ("x", "y"):
                    assert variant["properties"][axis]["minimum"] == 0
                    assert variant["properties"][axis]["maximum"] == 1
        assert "offscreen click" in body["messages"][0]["content"]
        uri = body["messages"][1]["content"][1]["image_url"]["url"]
        assert b64decode(uri.partition(",")[2]) == PNG
        return httpx.Response(200, json=REPLY)

    dispatch = VisionModelBatch(
        settings(huggingface_api_key=None, GOOGLE_DRIVE_OAUTH_CLIENT_ID=None),
        model_factory=partial(create_vision_language_model, transport=httpx.MockTransport(handler)),
        image_store_factory=no_drive,
    )
    outcome = asyncio.run(dispatch(**options(check_policy=lambda: checks.append("checked"))))
    assert outcome.status == "completed" and outcome.actions[0].kind == "click"
    assert checks == ["checked", "checked"] and len(requests) == 1


@pytest.mark.parametrize("y", [-0.1, 1.01, 350])
def test_gemini_offscreen_click_still_rejects_the_entire_batch(y):
    """Provider schema is guidance; never clamp or execute a partially invalid batch."""
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{
            "finish_reason": "stop", "message": {"content": json.dumps({"candidates": [
                {"kind": "click", "x": 0.3, "y": 0.4, "confidence": 0.9,
                 "expected_outcome": "Visible control opens"},
                {"kind": "click", "x": 0.3, "y": y, "confidence": 0.9,
                 "expected_outcome": "Offscreen control opens"},
            ]})},
        }]})

    dispatch = VisionModelBatch(
        settings(), image_store_factory=no_drive,
        model_factory=partial(create_vision_language_model, transport=httpx.MockTransport(handler)),
    )
    outcome = asyncio.run(dispatch(**options()))
    assert outcome.status == "unavailable" and outcome.actions is None
    assert outcome.diagnostic_code == "invalid_candidate_schema"
    assert outcome.failure_reason == "model_output_invalid"
    assert len(calls) == 1


def test_gemini_visible_click_and_scroll_are_valid_sibling_actions():
    content = {"candidates": [
        {"kind": "click", "x": 0.3, "y": 0.4, "confidence": 0.9,
         "expected_outcome": "Visible control opens"},
        {"kind": "scroll", "delta_y": 600, "confidence": 0.9,
         "expected_outcome": "More controls become visible"},
    ]}
    dispatch = VisionModelBatch(
        settings(), image_store_factory=no_drive,
        model_factory=partial(create_vision_language_model, transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"choices": [{"finish_reason": "stop",
                "message": {"content": json.dumps(content)}}]}),
        )),
    )
    outcome = asyncio.run(dispatch(**options()))
    assert outcome.status == "completed"
    assert [action.kind for action in outcome.actions] == ["click", "scroll"]


@pytest.mark.parametrize("provider", ["huggingface", "gemini"])
@pytest.mark.parametrize("condition", [
    "disabled", "no_consent", "wrong_binding", "bytes", "tokens", "steps", "candidates",
    "key", "deadline", "snapshot",
])
def test_rejects_before_any_image_or_model_network(provider, condition):
    args = options(provider)
    config = settings()
    if condition == "disabled":
        args["policy"].enabled = False
    elif condition == "no_consent":
        args["policy"].raw_screenshot_transfer_accepted = False
    elif condition == "wrong_binding":
        args["policy"].raw_screenshot_transfer_provider = None
    elif condition == "bytes":
        args["screenshot"] = b"x" * (args["policy"].max_screenshot_bytes + 1)
    elif condition == "tokens":
        args["guard"] = AgentStepGuard(StepGuardPolicy(
            max_tokens=999, max_steps_per_run=1, max_evidence_bytes_per_step=1024,
        ))
    elif condition == "steps":
        for _ in range(args["policy"].max_steps):
            assert args["guard"].allow_next_step(requested_tokens=1, evidence_bytes=1)
    elif condition == "candidates":
        args["max_candidates"] = 21
    elif condition == "key":
        config = settings(gemini_api_key=None, huggingface_api_key=None)
    elif condition == "deadline":
        args["remaining_seconds"] = 0
    elif condition == "snapshot":
        args["session"] = VisionModelSession("tenant-fixture", uuid4(), "other", "other")

    def handler(_):
        pytest.fail("guard failure must precede model request")

    dispatch = VisionModelBatch(
        config,
        model_factory=partial(create_vision_language_model, transport=httpx.MockTransport(handler)),
        image_store_factory=no_drive,
    )
    outcome = asyncio.run(dispatch(**args))
    assert outcome.status == "unavailable" and outcome.actions is None
    if condition == "key":
        assert outcome.failure_reason == "provider_not_configured"
    if condition == "deadline":
        assert outcome.failure_reason == "provider_timeout"


class PolicyChanged(RuntimeError):
    pass


@pytest.mark.parametrize("stage", ["before", "during"])
def test_provider_change_never_returns_proposals(stage):
    live = {"provider": "other" if stage == "before" else "gemini"}
    calls = []

    def check():
        if live["provider"] != "gemini":
            raise PolicyChanged("policy_changed")

    def handler(request):
        calls.append(request)
        live["provider"] = "huggingface"
        return httpx.Response(200, json=REPLY)

    dispatch = VisionModelBatch(
        settings(), image_store_factory=no_drive,
        model_factory=partial(create_vision_language_model, transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(PolicyChanged, match="policy_changed"):
        asyncio.run(dispatch(**options(check_policy=check)))
    assert len(calls) == (0 if stage == "before" else 1)


@pytest.mark.parametrize("failure", [None, "model", "policy", "oauth"])
def test_hf_keeps_drive_delivery_cleanup_and_auth_failure(failure):
    methods = []
    live = {"enabled": True}

    def check():
        if not live["enabled"]:
            raise PolicyChanged("policy_changed")

    def handler(request):
        methods.append((request.url.host, request.method))
        if request.url.host == "oauth2.googleapis.com":
            if failure == "oauth":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "fixture-oauth"})
        if request.url.host == "hf.invalid":
            assert 0 < request.extensions["timeout"]["read"] <= 5
            assert request.headers["authorization"] == "Bearer fixture-hf-key"
            uri = json.loads(request.content)["messages"][1]["content"][1]["image_url"]["url"]
            assert uri == "https://drive.usercontent.google.com/fixture.png"
            return httpx.Response(429 if failure == "model" else 200, json=REPLY)
        assert request.url.host == "www.googleapis.com"
        if request.url.path == "/upload/drive/v3/files":
            assert PNG in request.content
            return httpx.Response(200, json={"id": "fixture-image"})
        if request.method == "GET":
            if failure == "policy":
                live["enabled"] = False
            return httpx.Response(200, json={
                "webContentLink": "https://drive.usercontent.google.com/fixture.png",
            })
        return httpx.Response(204 if request.method == "DELETE" else 200, json={})

    transport = httpx.MockTransport(handler)
    dispatch = VisionModelBatch(
        settings(), model_factory=partial(create_vision_language_model, transport=transport),
        image_store_factory=partial(GoogleDriveTemporaryVisionImageStore, transport=transport),
    )
    if failure in {"policy", "oauth"}:
        error = PolicyChanged if failure == "policy" else VisionImageAuthorizationRequired
        with pytest.raises(error):
            asyncio.run(dispatch(**options("huggingface", check_policy=check)))
    else:
        result = asyncio.run(dispatch(**options("huggingface", check_policy=check)))
        assert result.status == ("unavailable" if failure else "completed")
        if failure:
            assert result.failure_reason == "provider_rate_limited"
    assert sum(host == "hf.invalid" for host, _ in methods) == (
        0 if failure in {"policy", "oauth"} else 1
    )
    if failure == "oauth":
        assert methods == [("oauth2.googleapis.com", "POST")]
    else:
        assert methods[-1] == ("www.googleapis.com", "DELETE")


def test_dispatch_cancels_on_remaining_deadline():
    cancelled = []

    async def handler(_):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    dispatch = VisionModelBatch(
        settings(), image_store_factory=no_drive,
        model_factory=partial(create_vision_language_model, transport=httpx.MockTransport(handler)),
    )
    outcome = asyncio.run(dispatch(**options(remaining_seconds=0.03)))
    assert outcome.failure_reason == "provider_timeout" and cancelled == [True]


def test_codex_cannot_fall_through_to_http_or_drive_without_dom_capability():
    from test_codex_candidate_service import codex_policy
    args = options()
    args["policy"] = codex_policy(
        raw_screenshot_transfer_accepted=True, raw_screenshot_transfer_provider="codex_cli",
    )
    args["session"] = VisionModelSession("tenant-fixture", uuid4(), "codex_cli", "gpt-6-luna")
    def forbidden(**_kwargs):
        pytest.fail("Codex must not construct a remote HTTP model or Drive store")
    result = asyncio.run(VisionModelBatch(
        settings(), model_factory=forbidden, image_store_factory=forbidden,
    )(**args))
    assert result.failure_reason == "bridge_offline"


@pytest.mark.parametrize(("remaining", "elapsed", "expected"), [
    (180, 35, "completed"),
    (60, 35, "completed"),
    (20, 35, "unavailable"),
    (180, 125, "unavailable"),
])
def test_slow_model_can_exceed_30_seconds_but_not_request_or_session_limit(
    remaining, elapsed, expected,
):
    """Advance the event-loop clock instead of waiting for real provider responses."""
    calls = []

    async def run():
        loop = asyncio.get_running_loop()
        original_time = loop.time
        offset = 0
        loop.time = lambda: original_time() + offset

        async def handler(request):
            nonlocal offset
            calls.append(request)
            budget = request.extensions["timeout"]["read"]
            assert min(120, remaining) - 1 < budget <= min(120, remaining)
            offset = elapsed
            # Let the loop process expired timers and deliver cancellation.
            for _ in range(3):
                await asyncio.sleep(0)
            return httpx.Response(200, json=REPLY)

        try:
            dispatch = VisionModelBatch(
                settings(), image_store_factory=no_drive,
                model_factory=partial(
                    create_vision_language_model, transport=httpx.MockTransport(handler),
                ),
            )
            return await dispatch(**options(remaining_seconds=remaining))
        finally:
            loop.time = original_time

    result = asyncio.run(run())
    assert result.status == expected
    assert len(calls) == 1
    if expected == "unavailable":
        assert result.failure_reason == "provider_timeout"
        assert result.actions is None
