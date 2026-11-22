"""Agent-loop contracts: closed action model, bounded context, strict schema, v4 identity."""

import hashlib
import json
import re
from datetime import timedelta
from pathlib import Path
from uuid import UUID

import pytest
from agents.prompts.codex_exploration import PROMPT_VERSION, build_prompt, with_response_schema
from agents.vision.codex_service import output_schema, task_context
from auto_at.contracts.codex_bridge import (
    AGENT_REF_PATTERN,
    AGENT_REQUEST_MAX_BYTES,
    AGENT_SNAPSHOT_MAX_CHARS,
    AgentAction,
    AgentLoopContext,
    AgentLoopOutput,
    AgentStep,
    CodexNeedScreenshot,
    CodexOutput,
    CodexStop,
    agent_loop_output_schema,
    canonical_bytes,
    content_hash,
    parse_agent_output,
    parse_codex_output,
)
from auto_at.contracts.vision_worker import VisualWorkerOpen
from infrastructure.codex_bridge.claude_process import enforceable_schema
from pydantic import TypeAdapter, ValidationError
from test_codex_bridge_contracts import NOW, observation, request, response

IDENTITY = json.loads(
    (Path(__file__).parent / "fixtures" / "v4_identity.json").read_text(encoding="utf-8")
)
# content_hash of the phase-0 sample request, measured before `agent_context` existed.
V4_REQUEST_HASH = "7d124f62ef381607ccb68fb5dac8fcbdefa59efc4ecfb3c125a4365a2b5e3f5e"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def context(**changes):
    return {
        "task": "Click every control", "allowed_hosts": ["fixture.test"],
        "snapshot_version": 3, "snapshot": "[3:1] button 'Continue'", **changes,
    }


def agent_request(**changes):
    return request(prompt_version="agent-loop-v1", agent_context=context(), **changes)


def action(kind, **fields):
    return AgentAction(kind=kind, **fields)


def step(actions=None, **changes):
    return AgentStep.model_validate({
        "evaluation_previous_goal": "Success: page opened",
        "memory": "Seen 2 of 5 controls", "next_goal": "Click Continue",
        "actions": actions if actions is not None else [{"kind": "click", "ref": "3:1"}],
    } | changes)


# --- AgentAction -----------------------------------------------------------------------

@pytest.mark.parametrize("kind,fields", [
    ("click", {"ref": "3:1"}),
    ("click", {"ref": "12:345", "expected_outcome": "Dialog opens"}),
    ("type", {"ref": "3:2", "text": "hello"}),
    ("scroll", {"delta_y": 400}),
    ("scroll", {"delta_y": -2000}),
    ("wait", {"duration_ms": 100}),
    ("wait", {"duration_ms": 10_000}),
    ("back", {}),
    ("close_popup", {}),
    ("navigate", {}),
])
def test_agent_action_accepts_each_kind_with_exactly_its_fields(kind, fields):
    assert action(kind, **fields).kind == kind


@pytest.mark.parametrize("kind,fields", [
    ("click", {}),
    ("click", {"ref": "3:1", "text": "x"}),
    ("click", {"ref": "3:1", "delta_y": 5}),
    ("type", {"ref": "3:2"}),
    ("type", {"text": "hello"}),
    ("scroll", {}),
    ("scroll", {"delta_y": 5, "ref": "3:1"}),
    ("wait", {}),
    ("wait", {"duration_ms": 100, "delta_y": 5}),
    ("back", {"ref": "3:1"}),
    ("close_popup", {"duration_ms": 100}),
    ("navigate", {"ref": "3:1"}),
    ("navigate", {"text": "https://elsewhere.test"}),
])
def test_agent_action_rejects_field_combinations_that_do_not_match_kind(kind, fields):
    with pytest.raises(ValidationError, match="do not match kind"):
        action(kind, **fields)


@pytest.mark.parametrize("ref", ["3", "3:", ":1", "a:1", "3:b", "3:1:2", "03:1 ", " 3:1", "3:1\n",
                                 "-1:2", "3.0:1", "e_" + "a" * 21])
def test_agent_action_parses_off_format_refs_within_length_and_leaves_format_to_the_domain(ref):
    # The contract only bounds length; `invalid_ref` is decided by AGENT_REF_PATTERN in the domain.
    assert len(ref) <= 24
    assert action("click", ref=ref).ref == ref
    assert re.fullmatch(AGENT_REF_PATTERN, ref) is None


@pytest.mark.parametrize("ref", ["1" * 12 + ":" + "2" * 12, "e_" + "a" * 32, "1" * 30, ""])
def test_agent_action_rejects_refs_longer_than_24_or_empty(ref):
    with pytest.raises(ValidationError):
        action("click", ref=ref)


def test_agent_action_ref_exactly_24_characters_is_accepted():
    ref = "1" * 11 + ":" + "2" * 12
    assert len(ref) == 24 and action("click", ref=ref).ref == ref


@pytest.mark.parametrize("ref", ["3:1", "12:345", "0:0"])
def test_agent_ref_pattern_accepts_version_colon_number_refs(ref):
    assert re.fullmatch(AGENT_REF_PATTERN, ref) is not None


def test_agent_action_rejects_unknown_kind_and_unknown_field():
    with pytest.raises(ValidationError):
        AgentAction(kind="hover", ref="3:1")
    with pytest.raises(ValidationError):
        AgentAction.model_validate({"kind": "navigate", "url": "https://elsewhere.test"})


@pytest.mark.parametrize("delta_y", [-2001, 2001, 10**9])
def test_agent_action_bounds_scroll(delta_y):
    with pytest.raises(ValidationError):
        action("scroll", delta_y=delta_y)


@pytest.mark.parametrize("duration_ms", [-1, 0, 99, 10_001])
def test_agent_action_bounds_wait(duration_ms):
    with pytest.raises(ValidationError):
        action("wait", duration_ms=duration_ms)


def test_agent_action_text_vietnamese_limit_is_one_thousand_characters():
    text = ("Tiếng Việt có dấu: ế ở ữ đ. " * 100)[:1000]
    assert len(text) == 1000 and not text.isascii()
    assert action("type", ref="3:2", text=text).text == text
    with pytest.raises(ValidationError):
        action("type", ref="3:2", text=text + "ế")
    with pytest.raises(ValidationError):
        action("type", ref="3:2", text="")


def test_agent_action_expected_outcome_is_bounded_and_non_empty():
    assert action("back", expected_outcome="x" * 300)
    for bad in ("", "x" * 301):
        with pytest.raises(ValidationError):
            action("back", expected_outcome=bad)


# --- AgentStep / parse ---------------------------------------------------------------

@pytest.mark.parametrize("count,valid", [(0, False), (1, True), (10, True), (11, False)])
def test_agent_step_requires_one_to_ten_actions(count, valid):
    actions = [{"kind": "wait", "duration_ms": 100}] * count
    if valid:
        assert len(step(actions).actions) == count
    else:
        with pytest.raises(ValidationError):
            step(actions)


@pytest.mark.parametrize("size,valid", [(0, True), (2000, True), (2001, False)])
def test_agent_step_memory_limit(size, valid):
    if valid:
        assert len(step(memory="m" * size).memory) == size
    else:
        with pytest.raises(ValidationError):
            step(memory="m" * size)


@pytest.mark.parametrize("field", ["evaluation_previous_goal", "next_goal"])
def test_agent_step_goal_fields_are_required_and_bounded(field):
    assert step(**{field: "g" * 500})
    for bad in ("", "g" * 501):
        with pytest.raises(ValidationError):
            step(**{field: bad})


def test_parse_agent_output_accepts_the_three_outcomes_and_unwraps_the_envelope():
    body = {"outcome": "agent_step", "evaluation_previous_goal": "ok", "memory": "",
            "next_goal": "go", "actions": [{"kind": "back"}]}
    parsed = parse_agent_output(json.dumps({"result": body}).encode())
    assert isinstance(parsed, AgentStep) and parsed.actions[0].kind == "back"
    assert isinstance(parse_agent_output(json.dumps(body).encode()), AgentStep)
    shot = parse_agent_output(b'{"outcome":"need_screenshot","reason":"visual_target"}')
    assert isinstance(shot, CodexNeedScreenshot)
    stop = parse_agent_output(b'{"result":{"outcome":"stop","reason":"complete"}}')
    assert isinstance(stop, CodexStop)


@pytest.mark.parametrize("data", [
    b'{"result":{"outcome":"candidates","candidates":[]},"extra":1}',
    b'{"outcome":"candidates","candidates":[{"kind":"wait","duration_ms":100,'
    b'"confidence":1,"expected_outcome":"x"}]}',
    b'{"outcome":"agent_step","evaluation_previous_goal":"ok","memory":"","next_goal":"g",'
    b'"actions":[{"kind":"click"}]}',
    b'{"outcome":"agent_step","extra":1,"evaluation_previous_goal":"ok","memory":"",'
    b'"next_goal":"g","actions":[{"kind":"back"}]}',
    b'{"outcome":"unknown"}',
    b"not json",
])
def test_parse_agent_output_rejects_invalid_or_foreign_output(data):
    with pytest.raises(ValueError):
        parse_agent_output(data)


def test_agent_output_is_not_a_codex_output_and_codex_parser_rejects_it():
    body = {"outcome": "agent_step", "evaluation_previous_goal": "ok", "memory": "",
            "next_goal": "go", "actions": [{"kind": "back"}]}
    with pytest.raises(ValidationError):
        TypeAdapter(CodexOutput).validate_python(body)
    with pytest.raises(ValueError):
        parse_codex_output(json.dumps(body).encode())


# --- AgentLoopContext and request ---------------------------------------------------

def test_agent_context_bounds():
    assert AgentLoopContext.model_validate(context(memory="m" * 2000))
    with pytest.raises(ValidationError):
        AgentLoopContext.model_validate(context(memory="m" * 2001))
    assert AgentLoopContext.model_validate(context(history=["h" * 600] * 5)).history
    with pytest.raises(ValidationError):
        AgentLoopContext.model_validate(context(history=["h"] * 6))
    with pytest.raises(ValidationError):
        AgentLoopContext.model_validate(context(history=["h" * 601]))
    assert AgentLoopContext.model_validate(context(snapshot="s" * 24_000))
    with pytest.raises(ValidationError):
        AgentLoopContext.model_validate(context(snapshot="s" * 24_001))
    for bad in ({"snapshot_version": 0}, {"task": ""}, {"extra": 1}):
        with pytest.raises(ValidationError):
            AgentLoopContext.model_validate(context(**bad))


def test_agent_prompt_request_requires_context_and_context_requires_agent_prompt():
    assert agent_request().agent_context.snapshot_version == 3
    with pytest.raises(ValueError, match="must occur together"):
        request(prompt_version="agent-loop-v1")
    with pytest.raises(ValueError, match="must occur together"):
        request(prompt_version="codex-dom-v11", context={"task_intent": "x"},
                agent_context=context())
    for version in ("agent-loop-v0", "agent-loop-1", "agent-loop-v1x", "agent-v1"):
        with pytest.raises(ValidationError):
            request(prompt_version=version, agent_context=context())
    assert request(prompt_version="agent-loop-v12", agent_context=context())


def test_v4_request_remains_valid_and_its_canonical_bytes_do_not_mention_agent_context():
    legacy = request(prompt_version="codex-dom-v11", context={"task_intent": "Open fixture"})
    assert legacy.agent_context is None
    assert b"agent_context" not in canonical_bytes(legacy)
    assert "agent_context" not in legacy.model_dump(mode="json")
    assert request(prompt_version="codex-dom-v1")
    assert b"agent_context" in canonical_bytes(agent_request())


def test_agent_request_with_24000_vietnamese_snapshot_chars_is_within_the_byte_ceiling():
    # 'ế' is 3 UTF-8 bytes on the canonical wire form (ensure_ascii=False): 72 000 bytes here.
    req = request(prompt_version="agent-loop-v1", agent_context=context(
        snapshot="ế" * AGENT_SNAPSHOT_MAX_CHARS,
    ))
    size = len(canonical_bytes(req))
    assert 72_000 < size <= AGENT_REQUEST_MAX_BYTES


def test_agent_request_is_refused_when_its_canonical_bytes_exceed_the_ceiling():
    # 24 000 snapshot chars (72 000 bytes) plus 100 hosts of 255 'ế' (76 500 bytes) > 131 072.
    hosts = ["ế" * 255] * 100
    with pytest.raises(ValueError, match="byte limit"):
        request(prompt_version="agent-loop-v1", agent_context=context(
            snapshot="ế" * AGENT_SNAPSHOT_MAX_CHARS, allowed_hosts=hosts,
        ))
    # The same request with ASCII hosts, far fewer bytes, is accepted: the limit counts bytes.
    ok = request(prompt_version="agent-loop-v1", agent_context=context(
        snapshot="ế" * AGENT_SNAPSHOT_MAX_CHARS, allowed_hosts=["fixture.test"] * 100,
    ))
    assert len(canonical_bytes(ok)) > 72_000


def test_v4_request_is_not_subject_to_the_agent_byte_ceiling():
    legacy = request(prompt_version="codex-dom-v11", context={"task_intent": "ế" * 2000})
    assert len(canonical_bytes(legacy)) < AGENT_REQUEST_MAX_BYTES
    assert content_hash(legacy)


def test_agent_request_round_trips_with_a_stable_hash():
    req = agent_request()
    again = type(req).model_validate_json(req.model_dump_json())
    assert content_hash(again) == content_hash(req) and again == req


def test_response_accepts_both_output_families_and_keeps_existing_rules():
    req = agent_request()
    agent = response(req, output=step().model_dump(mode="json"))
    assert isinstance(agent.output, AgentStep)
    assert isinstance(response(req, output={"outcome": "stop", "reason": "complete"}).output,
                      CodexStop)
    v4 = request(prompt_version="codex-dom-v11", context={"task_intent": "Open fixture"})
    candidates = {"outcome": "candidates", "candidates": [{
        "kind": "click", "element_id": "e_" + "a" * 32, "confidence": 0.5,
        "expected_outcome": "opens"}]}
    assert response(v4, output=candidates).output.outcome == "candidates"
    with pytest.raises(ValidationError):
        response(req, output={"outcome": "agent_step"})


# --- worker open ---------------------------------------------------------------------

def open_payload(**changes):
    return {
        "tenant_id": "fixture", "project_id": str(UUID(int=1)), "session_id": str(UUID(int=2)),
        "fencing_token": 1, "target_url": "https://fixture.test/",
        "allowed_origins": ["https://fixture.test"], "deadline": NOW + timedelta(minutes=5),
        "max_session_seconds": 60, "max_states": 5, "max_hops": 3,
        "max_screenshot_bytes": 5000, **changes,
    }


def test_worker_open_agent_flags_default_off_and_have_a_forty_by_forty_ceiling():
    legacy = VisualWorkerOpen.model_validate(open_payload())
    assert legacy.agent_mode is False and legacy.blocked_action_terms == ()
    assert "agent_mode" in legacy.model_dump() and "blocked_action_terms" in legacy.model_dump()
    full = VisualWorkerOpen.model_validate(open_payload(
        agent_mode=True, blocked_action_terms=["x" * 40] * 40,
    ))
    assert len(full.blocked_action_terms) == 40
    with pytest.raises(ValidationError):
        VisualWorkerOpen.model_validate(open_payload(agent_mode=True,
                                                     blocked_action_terms=["a"] * 41))
    for bad in ("x" * 41, ""):
        with pytest.raises(ValidationError):
            VisualWorkerOpen.model_validate(open_payload(agent_mode=True,
                                                         blocked_action_terms=[bad]))


# --- strict schema --------------------------------------------------------------------

_ANNOTATIONS = {"title", "description", "default", "discriminator", "$defs"}


def schema_errors(schema, value, root=None, path="$"):
    """Validate the JSON Schema subset our strict agent schema uses; unknown keywords fail."""
    root = root if root is not None else schema
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/$defs/")
        return schema_errors(root["$defs"][name], value, root, path)
    errors = []
    for key, rule in schema.items():
        if key in _ANNOTATIONS:
            continue
        if key == "anyOf":
            if all(schema_errors(option, value, root, path) for option in rule):
                errors.append(f"{path}: no anyOf branch matches")
        elif key == "type":
            kinds = {"object": dict, "array": list, "string": str, "null": type(None)}
            if rule == "integer":
                if type(value) is not int:
                    errors.append(f"{path}: not an integer")
            elif rule == "boolean":
                if type(value) is not bool:
                    errors.append(f"{path}: not a boolean")
            elif not isinstance(value, kinds[rule]):
                errors.append(f"{path}: not {rule}")
        elif key == "enum":
            if value not in rule:
                errors.append(f"{path}: not in enum")
        elif key == "required":
            if isinstance(value, dict):
                errors += [f"{path}: missing {name}" for name in rule if name not in value]
        elif key == "additionalProperties":
            assert rule is False, "unsupported additionalProperties"
            if isinstance(value, dict):
                errors += [f"{path}: extra {name}" for name in value
                           if name not in schema.get("properties", {})]
        elif key == "properties":
            if isinstance(value, dict):
                for name, child in rule.items():
                    if name in value:
                        errors += schema_errors(child, value[name], root, f"{path}.{name}")
        elif key == "items":
            if isinstance(value, list):
                for index, item in enumerate(value):
                    errors += schema_errors(rule, item, root, f"{path}[{index}]")
        elif key in {"minItems", "maxItems"}:
            if isinstance(value, list) and (
                len(value) < rule if key == "minItems" else len(value) > rule
            ):
                errors.append(f"{path}: {key}")
        elif key in {"minLength", "maxLength"}:
            if isinstance(value, str) and (
                len(value) < rule if key == "minLength" else len(value) > rule
            ):
                errors.append(f"{path}: {key}")
        elif key == "pattern":
            if isinstance(value, str) and re.search(rule, value) is None:
                errors.append(f"{path}: pattern mismatch")
        elif key in {"minimum", "maximum"}:
            if type(value) is int and (value < rule if key == "minimum" else value > rule):
                errors.append(f"{path}: {key}")
        else:
            raise AssertionError(f"unsupported schema keyword {key}")
    return errors


def full(**fields):
    return {"kind": "click", "ref": None, "text": None, "delta_y": None, "duration_ms": None,
            "expected_outcome": None} | fields


def agent_payload(actions=None, **changes):
    return {"result": {
        "outcome": "agent_step", "evaluation_previous_goal": "ok", "memory": "m",
        "next_goal": "go", "actions": actions if actions is not None else [full(ref="3:1")],
    } | changes}


def test_agent_schema_is_strict_flat_and_satisfiable_by_enforceable_schema():
    raw = agent_loop_output_schema()
    schema = json.loads(raw)
    # `enforceable_schema` only rewrites objects that mix `properties` with an anyOf of
    # property variants; the flat agent schema has none, so it must pass through untouched.
    assert enforceable_schema(raw) == schema
    assert schema["required"] == ["result"] and schema["additionalProperties"] is False
    definitions = schema["$defs"]
    assert {"AgentAction", "AgentStep", "CodexNeedScreenshot", "CodexStop"} <= set(definitions)
    for name, node in definitions.items():
        if "properties" in node:
            assert set(node["required"]) == set(node["properties"]), name
            assert node["additionalProperties"] is False, name
    action_schema = definitions["AgentAction"]
    assert "anyOf" not in action_schema
    nullable = [name for name, node in action_schema["properties"].items()
                if {"type": "null"} in node.get("anyOf", [])]
    assert sorted(nullable) == sorted(
        ["ref", "text", "delta_y", "duration_ms", "expected_outcome"]
    )
    ref_schema = action_schema["properties"]["ref"]
    assert "pattern" not in json.dumps(ref_schema)
    assert {"type": "string", "minLength": 1, "maxLength": 24} in ref_schema["anyOf"]
    assert definitions["AgentStep"]["properties"]["actions"]["maxItems"] == 10
    assert definitions["AgentStep"]["properties"]["actions"]["minItems"] == 1


def test_agent_schema_accepts_what_pydantic_accepts_and_rejects_what_it_rejects():
    schema = enforceable_schema(agent_loop_output_schema())
    good = [
        agent_payload(),
        agent_payload([full(kind="type", ref="3:2", text="Việt"), full(kind="back")]),
        agent_payload([full(kind="scroll", delta_y=-300), full(kind="navigate")]),
        agent_payload([full(kind="wait", duration_ms=500, expected_outcome="loaded")]),
        # Off-format ref: schema and parser accept it, the domain answers `invalid_ref`.
        agent_payload([full(ref="not-a-ref")]),
        {"result": {"outcome": "stop", "reason": "complete"}},
        {"result": {"outcome": "need_screenshot", "reason": "visual_target"}},
    ]
    for value in good:
        assert schema_errors(schema, value) == [], value
        assert parse_agent_output(json.dumps(value).encode())
    bad = [
        agent_payload([]),
        agent_payload([full(ref="3:1")] * 11),
        agent_payload([full(ref="9" * 25)]),
        agent_payload([full(kind="hover", ref="3:1")]),
        agent_payload([full(duration_ms=5, kind="wait")]),
        agent_payload(memory="m" * 2001),
        agent_payload(evaluation_previous_goal=""),
        agent_payload([dict(full(ref="3:1"), url="https://elsewhere.test")]),
        {"result": {"outcome": "stop", "reason": "because"}},
        {"result": {"outcome": "candidates", "candidates": []}},
    ]
    for value in bad:
        assert schema_errors(schema, value) != [], value
        with pytest.raises(ValueError):
            parse_agent_output(json.dumps(value).encode())


def test_strict_schema_is_stricter_than_pydantic_about_omitted_nullable_fields():
    schema = enforceable_schema(agent_loop_output_schema())
    omitted = agent_payload([{"kind": "click", "ref": "3:1"}])
    assert schema_errors(schema, omitted) != []  # every field must be present, null if unused
    assert parse_agent_output(json.dumps(omitted).encode()).actions[0].ref == "3:1"
    bare = {"outcome": "stop", "reason": "complete"}  # the CLI schema requires the envelope
    assert schema_errors(schema, bare) != []
    assert isinstance(parse_agent_output(json.dumps(bare).encode()), CodexStop)


def test_schema_helper_would_notice_a_broken_merge():
    # Guard against a vacuous validator: a variant that lost its fields must be rejected.
    schema = enforceable_schema(agent_loop_output_schema())
    broken = json.loads(json.dumps(schema))
    broken["$defs"]["AgentAction"]["properties"].pop("ref")
    broken["$defs"]["AgentAction"]["required"].remove("ref")
    assert schema_errors(broken, agent_payload()) != []


# --- v4 identity ----------------------------------------------------------------------

def test_codex_output_schema_sha256_matches_the_phase_zero_baseline():
    canonical = json.dumps(
        TypeAdapter(CodexOutput).json_schema(), sort_keys=True, separators=(",", ":"),
    ).encode()
    baseline = IDENTITY["codex_output_schema"]
    assert sha256(canonical) == baseline["sha256"]
    assert len(canonical) == baseline["bytes"]


def test_agent_family_is_not_part_of_the_codex_output_schema():
    text = json.dumps(TypeAdapter(CodexOutput).json_schema())
    assert "agent_step" not in text and "AgentStep" not in text
    assert "agent_step" in json.dumps(TypeAdapter(AgentLoopOutput).json_schema())


def sample_request_and_dom():
    obs = observation(
        tenant_id="fixture", project_id=UUID(int=1), session_id=UUID(int=2), fencing_token=1,
        observation_id=UUID(int=3), snapshot_id=UUID(int=4),
    )
    req = request(
        obs, job_id=UUID(int=5), bridge_id=UUID(int=6), correlation_id=UUID(int=7),
        prompt_version=PROMPT_VERSION, context=task_context("Check buttons on the fixture page"),
    )
    return obs, req


def test_v4_prompt_schema_and_request_hash_match_the_phase_zero_baseline():
    obs, req = sample_request_and_dom()
    prompt = build_prompt(req, canonical_bytes(obs))
    wrapped = with_response_schema(prompt, output_schema(3))
    baseline = IDENTITY["codex_dom_v11_prompt_plus_schema"]
    assert PROMPT_VERSION == IDENTITY["prompt_version"] == "codex-dom-v11"
    assert sha256(output_schema(3)) == baseline["bridge_schema_sha256"]
    assert sha256(prompt) == baseline["prompt_sha256"]
    assert sha256(wrapped) == baseline["sha256"] and len(wrapped) == baseline["bytes"]
    # Recorded before `agent_context` existed: serializer drift would change every v4 job hash.
    assert content_hash(req) == V4_REQUEST_HASH
    assert b"agent_context" not in canonical_bytes(req)
