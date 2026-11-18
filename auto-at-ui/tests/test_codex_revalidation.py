"""A delayed DOM reply may survive drift only with trusted fresh target bindings."""

import json
from uuid import uuid4

import pytest
from auto_at.contracts.codex_bridge import parse_codex_output
from test_codex_candidate_service import Fixture, parsed


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["benign", "rejected", "scope", "still_stale", "policy"])
async def test_delayed_reply_revalidates_without_another_model_call(change):
    fixture = Fixture([parsed("dom_click")])
    original = fixture.exchange
    old_snapshot = fixture.bound.observation.snapshot_id
    refreshed = []

    async def exchange(**kwargs):
        result = await original(**kwargs)
        fixture.state_ok = False
        return result

    async def revalidate(ids):
        refreshed.append(ids)
        if change == "rejected":
            return None
        obs = fixture.bound.observation.model_copy(update={
            "snapshot_id": uuid4(), "observation_id": uuid4(), "state_fingerprint": "b" * 64,
            **({"session_id": uuid4()} if change == "scope" else {}),
        })
        binding = fixture.bound.bindings[0]
        fixture.bound = fixture.bound.model_copy(update={"observation": obs, "bindings": (
            binding.model_copy(update={"bounds": binding.bounds.model_copy(update={"x": 0.4})}),
        )})
        fixture.state_ok = change != "still_stale"
        if change == "policy":
            fixture.policy.enabled = False
        return fixture.bound

    fixture.exchange = exchange
    result = await fixture.run(revalidate_targets=revalidate)
    assert len(fixture.calls) == 1 and result.calls_used == 1
    assert len(refreshed) == 1 and fixture.captures == 0
    if change == "benign":
        assert result.status == "completed"
        assert result.actions[0].x == pytest.approx(0.45)
        assert result.target_bindings[0].snapshot_id != old_snapshot
        assert result.target_bindings[0].state_fingerprint == "b" * 64
    else:
        assert result.actions is None
        assert result.failure_reason == ("policy_changed" if change == "policy"
                                         else "bridge_stale_result")


@pytest.mark.asyncio
@pytest.mark.parametrize("output", ["stop", "image_request"])
async def test_non_target_decisions_cannot_be_revalidated(output, caplog):
    caplog.set_level("INFO", logger="application.codex_candidates")
    fixture = Fixture([parsed(output)])
    original = fixture.exchange

    async def exchange(**kwargs):
        result = await original(**kwargs)
        fixture.state_ok = False
        return result

    async def forbidden(_):
        pytest.fail("Only bound DOM actions may be revalidated")

    fixture.exchange = exchange
    result = await fixture.run(revalidate_targets=forbidden)
    assert result.failure_reason == "bridge_stale_result" and result.actions is None
    assert len(fixture.calls) == 1
    record = next(r for r in caplog.records
                  if getattr(r, "event", None) == "vision.codex.stale_response")
    assert record.stage == "dom" and record.call_sequence == 1
    assert record.response_outcome == parsed(output).outcome
    assert record.candidate_kinds == []
    assert record.revalidation_available and not record.response_failed
    assert "Page changed while waiting" in record.getMessage()


@pytest.mark.asyncio
async def test_state_changed_during_rate_wait_does_not_consume_a_call():
    fixture = Fixture([parsed("dom_click")])
    fixture.budget.last_call = 0
    original = fixture.budget.sleep

    async def sleep(delay):
        await original(delay)
        fixture.state_ok = False

    fixture.budget.sleep = sleep
    result = await fixture.run()
    assert result.failure_reason == "bridge_stale_result"
    assert result.calls_used == fixture.budget.calls == 0
    assert fixture.calls == []


@pytest.mark.asyncio
async def test_image_reply_never_uses_dom_revalidation():
    fixture = Fixture([parsed("image_request"), parsed("dom_click")],
                      raw_screenshot_transfer_accepted=True,
                      raw_screenshot_transfer_provider="codex_cli")
    original = fixture.exchange

    async def exchange(**kwargs):
        result = await original(**kwargs)
        if kwargs["image"] is not None:
            fixture.state_ok = False
        return result

    async def forbidden(_):
        pytest.fail("Image evidence cannot be rebound to a fresh DOM")

    fixture.exchange = exchange
    result = await fixture.run(revalidate_targets=forbidden)
    assert result.failure_reason == "bridge_stale_result" and result.actions is None
    assert len(fixture.calls) == 2 and fixture.captures == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
@pytest.mark.parametrize("kind", ["abstain", "scroll", "mixed", "complete"])
async def test_viewport_abstention_never_accepts_model_scroll_parameters(kind, stale):
    scroll = {"kind": "scroll", "delta_y": -1700, "confidence": .9,
              "expected_outcome": "Untrusted model distance"}
    value = ({"outcome": "stop", "reason": "no_safe_action" if kind == "abstain" else "complete"}
             if kind in {"abstain", "complete"} else
             {"outcome": "candidates", "candidates": [scroll] + (
                 [parsed("dom_click").candidates[0].model_dump(mode="json")]
                 if kind == "mixed" else [])})
    fixture = Fixture([parse_codex_output(json.dumps(value).encode())])
    exchange = fixture.exchange

    async def respond(**kwargs):
        reply = await exchange(**kwargs)
        fixture.state_ok = not stale
        return reply

    fixture.exchange = respond
    result = await fixture.run(deterministic_viewports=True)
    assert result.calls_used == len(fixture.calls) == 1
    assert fixture.captures == 0
    assert result.viewport_scan_requested == (kind in {"abstain", "scroll"})
    if result.viewport_scan_requested:
        assert result.actions == [] and result.target_bindings == ()
    elif stale:
        assert result.actions is None and result.failure_reason == "bridge_stale_result"
