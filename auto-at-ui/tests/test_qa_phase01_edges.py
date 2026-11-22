"""QA phase 1 (browser-agent-loop): independent boundary cases, written without reusing dev helpers
for the contract side. Pure contract + HTTP cases only; no product code is touched."""

# ruff: noqa: F811  (pytest fixtures imported from the provider submission tests)
import json
import re

import pytest
from auto_at.contracts.codex_bridge import (
    AGENT_REF_PATTERN,
    AGENT_REQUEST_MAX_BYTES,
    AgentAction,
    AgentLoopContext,
    AgentStep,
    CodexBridgeRequest,
    agent_loop_output_schema,
    canonical_bytes,
    parse_agent_output,
)
from auto_at.contracts.vision_worker import VisualWorkerOpen
from pydantic import ValidationError
from test_codex_bridge_contracts import request
from test_vision_provider_submission import submission, submit  # noqa: F401
from vision_trace_fixtures import trace_database  # noqa: F401

pytest_plugins = ["vision_trace_fixtures"]
VI = "Đặt hàng ắằẳẵặ ếềểễệ ốồổỗộ ướừửữự ỳýỷỹỵ"  # 41 chars incl. spaces


def act(kind="click", **fields):
    if kind in ("click", "type") and "ref" not in fields:
        fields["ref"] = "1:2"
    return {"kind": kind, **fields}


def step(n=1, **over):
    base = {"evaluation_previous_goal": "ok", "memory": "", "next_goal": "go",
            "actions": [act()] * n}
    return {**base, **over}


@pytest.mark.parametrize("n,ok", [(0, False), (1, True), (10, True), (11, False)])
def test_qa_actions_count(n, ok):
    if ok:
        assert len(AgentStep.model_validate(step(n)).actions) == n
    else:
        with pytest.raises(ValidationError):
            AgentStep.model_validate(step(n))


@pytest.mark.parametrize("n,ok", [(1000, True), (1001, False)])
def test_qa_vietnamese_text_limit(n, ok):
    text = (VI * 30)[:n]
    assert len(text) == n
    if ok:
        assert AgentAction.model_validate(act("type", text=text)).text == text
    else:
        with pytest.raises(ValidationError):
            AgentAction.model_validate(act("type", text=text))


@pytest.mark.parametrize("ref", ["1:2", "0:0", "123:456"])
def test_qa_ref_ok(ref):
    assert AgentAction.model_validate(act(ref=ref)).ref == ref


@pytest.mark.parametrize("ref", ["1", "1:", ":2", "a:b", " 1:2", "1:2 ", "1:2\n", "1:2:3",
                                 "-1:2", "١:٢", "1:" + "9" * 21 + "x"])
def test_qa_ref_off_format_parses_but_fails_pattern(ref):
    # r2: the contract only bounds length (1..24); format is the domain's job.
    assert len(ref) <= 24
    assert AgentAction.model_validate(act(ref=ref)).ref == ref
    assert re.fullmatch(AGENT_REF_PATTERN, ref) is None


@pytest.mark.parametrize("ref", ["", "1:" + "9" * 23, "1:" + "9" * 30, "ế" * 25])
def test_qa_ref_empty_or_over_24_rejected(ref):
    with pytest.raises(ValidationError):
        AgentAction.model_validate(act(ref=ref))


def test_qa_ref_24_accepted_and_navigate_with_ref_still_rejected():
    ref = "1:" + "9" * 22
    assert len(ref) == 24 and AgentAction.model_validate(act(ref=ref)).ref == ref
    with pytest.raises(ValidationError):
        AgentAction.model_validate(act("navigate", ref="1:2"))


def _sized(big, pad):
    hosts = ["ế" * 255] * big + (["a" * pad] if pad else [])
    ctx = dict(task="t", allowed_hosts=hosts, snapshot_version=1, snapshot="ế" * 24000)
    return request(prompt_version="agent-loop-v1", agent_context=ctx)


def _fits(big, pad):
    try:
        _sized(big, pad)
        return True
    except ValueError:
        return False


def test_qa_request_byte_ceiling_exact_boundary():
    # Tune with 1-byte ASCII steps until the canonical size is exactly 131 072, then +1 is refused.
    big = max(h for h in range(0, 101) if _fits(h, 0))
    assert big < 100  # layout must be able to hit the ceiling
    pad = max(p for p in range(0, 256) if _fits(big, p))
    assert pad < 255
    assert len(canonical_bytes(_sized(big, pad))) == AGENT_REQUEST_MAX_BYTES == 131_072
    with pytest.raises(ValueError, match="byte limit"):
        _sized(big, pad + 1)


@pytest.mark.parametrize("fields,ok", [
    ({"delta_y": 2000}, True), ({"delta_y": -2000}, True), ({"delta_y": 2001}, False),
    ({"delta_y": -2001}, False), ({"delta_y": 0}, True), ({"delta_y": 1.5}, False),
])
def test_qa_scroll(fields, ok):
    if ok:
        AgentAction.model_validate(act("scroll", **fields))
    else:
        with pytest.raises(ValidationError):
            AgentAction.model_validate(act("scroll", **fields))


@pytest.mark.parametrize("d,ok", [(99, False), (100, True), (10000, True), (10001, False),
                                  (0, False), (-5, False)])
def test_qa_wait(d, ok):
    if ok:
        AgentAction.model_validate(act("wait", duration_ms=d))
    else:
        with pytest.raises(ValidationError):
            AgentAction.model_validate(act("wait", duration_ms=d))


@pytest.mark.parametrize("kind", ["back", "close_popup", "navigate"])
def test_qa_no_field_kinds_reject_any_field(kind):
    AgentAction.model_validate(act(kind))
    for extra in ({"ref": "1:2"}, {"text": "x"}, {"delta_y": 1}, {"duration_ms": 100},
                  {"url": "https://evil.test"}):
        with pytest.raises(ValidationError):
            AgentAction.model_validate(act(kind, **extra))


@pytest.mark.parametrize("n,ok", [(5, True), (6, False)])
def test_qa_history_count_and_item_len(n, ok):
    base = dict(task="t", allowed_hosts=["a.test"], snapshot_version=1, snapshot="s")
    if ok:
        AgentLoopContext.model_validate(base | {"history": ["h"] * n})
    else:
        with pytest.raises(ValidationError):
            AgentLoopContext.model_validate(base | {"history": ["h"] * n})
    AgentLoopContext.model_validate(base | {"history": [VI[:1] * 600]})
    with pytest.raises(ValidationError):
        AgentLoopContext.model_validate(base | {"history": [VI[:1] * 601]})


@pytest.mark.parametrize("n,ok", [(24000, True), (24001, False)])
def test_qa_snapshot_and_memory(n, ok):
    base = dict(task="t", allowed_hosts=["a.test"], snapshot_version=1)
    if ok:
        AgentLoopContext.model_validate(base | {"snapshot": "ế" * n})
    else:
        with pytest.raises(ValidationError):
            AgentLoopContext.model_validate(base | {"snapshot": "ế" * n})
    AgentLoopContext.model_validate(base | {"snapshot": "", "memory": "ế" * 2000})
    with pytest.raises(ValidationError):
        AgentLoopContext.model_validate(base | {"snapshot": "", "memory": "ế" * 2001})


def test_qa_memory_in_step_2000_vs_2001():
    AgentStep.model_validate(step(memory="ế" * 2000))
    with pytest.raises(ValidationError):
        AgentStep.model_validate(step(memory="ế" * 2001))


def test_qa_parse_output_outcomes_and_garbage():
    raw = json.dumps({"result": {"outcome": "agent_step", **step()}}).encode()
    assert parse_agent_output(raw).outcome == "agent_step"
    assert parse_agent_output(b'{"outcome":"stop","reason":"complete"}').outcome == "stop"
    for bad in (b"", b"null", b"[]", b'{"outcome":"candidates"}', b'{"outcome":"agent_step"}',
                b'{"result":{"outcome":"stop"},"x":1}'):
        with pytest.raises((ValidationError, ValueError)):
            parse_agent_output(bad)


def test_qa_v4_request_bytes_have_no_agent_context_and_codex_prompt_forbids_it():
    req = request()
    assert b"agent_context" not in canonical_bytes(req)
    ctx = dict(task="t", allowed_hosts=["a.test"], snapshot_version=1, snapshot="s")
    with pytest.raises(ValidationError):
        CodexBridgeRequest.model_validate(req.model_dump(mode="json") | {"agent_context": ctx})
    for bad in ("agent-loop-v0", "agent-loop-v01", "agent-loop-", "agent-loop-v1\n", "agent-v1"):
        with pytest.raises(ValidationError):
            CodexBridgeRequest.model_validate(
                req.model_dump(mode="json") | {"prompt_version": bad, "agent_context": ctx})


def test_qa_agent_schema_is_closed_and_deterministic():
    a, b = agent_loop_output_schema(), agent_loop_output_schema()
    assert a == b
    schema = json.loads(a)

    def walk(n):
        if isinstance(n, dict):
            if "properties" in n:
                assert n["additionalProperties"] is False
                assert sorted(n["required"]) == sorted(n["properties"])
            for c in n.values():
                walk(c)
        elif isinstance(n, list):
            for c in n:
                walk(c)
    walk(schema)
    assert "oneOf" not in a.decode() and "default" not in a.decode()


@pytest.mark.parametrize("terms,ok", [
    (["x"] * 40, True), (["x"] * 41, False), (["ế" * 40], True), (["ế" * 41], False), ([""], False),
])
def test_qa_blocked_terms_ceiling(terms, ok):
    assert (_open_with(terms) is not None) == ok


def _open_with(terms):
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4
    try:
        return VisualWorkerOpen.model_validate(dict(
            tenant_id="t", project_id=str(uuid4()), session_id=str(uuid4()), fencing_token=1,
            target_url="https://a.test/", allowed_origins=["https://a.test"],
            deadline=datetime.now(UTC) + timedelta(minutes=5), max_session_seconds=60,
            max_states=5, max_hops=3, max_screenshot_bytes=5000,
            agent_mode=True, blocked_action_terms=terms,
        ))
    except ValidationError:
        return None


def test_qa_worker_open_defaults():
    m = _open_with([])
    assert m is not None and m.agent_mode is True
    m2 = _open_with(["x"])
    assert m2.blocked_action_terms == ("x",)


# --- HTTP edges ---------------------------------------------------------------------------

@pytest.mark.parametrize("engine", [" planner", "planner ", "Planner", "agent-loop", "agent_loop\n",
                                    ["planner"], {"a": 1}, True])
def test_qa_http_engine_garbage_is_422(submission, engine):
    client, payload, *_ = submission
    assert submit(client, payload | {"engine": engine}).status_code == 422


def test_qa_http_omitted_engine_is_planner(submission):
    client, payload, *_ = submission
    r = submit(client, payload)
    assert r.status_code == 202 and r.json()["engine"] == "planner"
