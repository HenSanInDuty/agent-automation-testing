"""Do not confuse feature flags or an empty top-level list with tool isolation."""

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
from config import Settings
from infrastructure.codex_bridge.catalogue import (
    restricted_catalogue,
    validate_catalogue,
    validate_instructions,
)
from infrastructure.codex_bridge.doctor import container_flags_qualified, doctor

spec = importlib.util.spec_from_file_location(
    "codex_bridge_wire", Path(__file__).parent / "fixtures/codex_bridge_wire.py"
)
wire = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wire)


@pytest.mark.parametrize("uid,read_only,status,expected", [
    (1000, True, "NoNewPrivs: 1\nCapEff: 00000000\nSeccomp: 2", True),
    (0, True, "NoNewPrivs: 1\nCapEff: 00000000\nSeccomp: 2", False),
    (1000, False, "NoNewPrivs: 1\nCapEff: 00000000\nSeccomp: 2", False),
    (1000, True, "NoNewPrivs: 0\nCapEff: 00000000\nSeccomp: 2", False),
    (1000, True, "NoNewPrivs: 1\nCapEff: 00000001\nSeccomp: 2", False),
    (1000, True, "NoNewPrivs: 1\nCapEff: 00000000\nSeccomp: 0", False),
    (1000, True, "NoNewPrivs: 1\nCapEff: invalid\nSeccomp: 2", False),
    (1000, True, "", False),
])
def test_yolo_requires_outer_container_protections(uid, read_only, status, expected):
    assert container_flags_qualified(uid=uid, root_read_only=read_only, status=status) == expected


def test_catalogue_removes_only_tool_capabilities_without_changing_prompts_or_model():
    model = {"slug": "gpt-6-luna", "tool_mode": "code_mode_only",
             "apply_patch_tool_type": "freeform", "experimental_supported_tools": ["clock"],
             "base_instructions": "bundled unchanged", "model_messages": {"prompt": "unchanged"}}
    result = restricted_catalogue({"models": [model, {"slug": "other-model"}]})
    assert result == {"models": [{**model, "tool_mode": None, "apply_patch_tool_type": None,
                                 "experimental_supported_tools": []}]}
    assert model["tool_mode"] == "code_mode_only"


@pytest.mark.parametrize("models", [[], [{"slug": "other"}],
                                   [{"slug": "gpt-6-luna"}, {"slug": "gpt-6-luna"}]])
def test_catalogue_rejects_missing_or_ambiguous_model(models):
    with pytest.raises(ValueError):
        restricted_catalogue({"models": models})


def test_startup_rejects_missing_or_changed_catalogue(tmp_path, monkeypatch):
    path = tmp_path / "catalogue.json"
    monkeypatch.setattr("infrastructure.codex_bridge.catalogue.CATALOGUE_PATH", path)
    monkeypatch.setattr("infrastructure.codex_bridge.catalogue.bundled_catalogue",
                        lambda _: {"models": [{"slug": "gpt-6-luna", "tool_mode": None}]})
    with pytest.raises(ValueError):
        validate_catalogue("unused")
    path.write_text('{"models": [{"slug": "other"}]}')
    with pytest.raises(ValueError):
        validate_catalogue("unused")
    path.write_text('{"models": [{"slug": "gpt-6-luna", "tool_mode": null}]}')
    validate_catalogue("unused")


def test_startup_requires_exact_centralized_instructions(tmp_path, monkeypatch):
    from agents.prompts.codex_exploration import INSTRUCTIONS
    path = tmp_path / "instructions.txt"
    monkeypatch.setattr("infrastructure.codex_bridge.catalogue.INSTRUCTIONS_PATH", path)
    with pytest.raises(ValueError):
        validate_instructions()
    path.write_text("altered role")
    with pytest.raises(ValueError):
        validate_instructions()
    path.write_text(INSTRUCTIONS)
    validate_instructions()


def test_additional_tools_and_nested_namespaces_are_counted():
    request = {"tools": [{"type": "function", "name": "exec_command"}], "input": [
        {"type": "message", "role": "user", "content": []},
        {"type": "additional_tools", "tools": [
            {"type": "namespace", "name": "functions", "tools": [
                {"type": "custom", "name": "exec"},
            ]},
            {"type": "namespace", "name": "collaboration", "tools": [
                {"type": "function", "name": "spawn_agent"},
            ]},
        ]},
    ]}
    assert wire.declared_tool_names(request) == [
        "exec_command", "functions.exec", "collaboration.spawn_agent",
    ]
    assert wire.declared_tool_names({"tools": [], "input": request["input"]})
    assert wire.declared_tool_names({"input": []}) == []


@pytest.mark.parametrize("tools", [None, {}, [None], [{}], [
    {"type": "namespace", "name": "functions"},
]])
def test_malformed_declarations_cannot_be_reported_as_empty(tools):
    with pytest.raises(ValueError):
        wire.declared_tool_names({"input": [{"type": "additional_tools", "tools": tools}]})


def test_unqualified_pin_fails_doctor_before_auth_or_process_access(monkeypatch):
    monkeypatch.setattr("infrastructure.codex_bridge.doctor.TOOL_ISOLATION_QUALIFIED_VERSIONS",
                        frozenset())
    def forbidden(*_args, **_kwargs):
        pytest.fail("unqualified CLI must not start a process or inspect login")

    monkeypatch.setattr("infrastructure.codex_bridge.doctor.subprocess.run", forbidden)
    settings = Settings(
        _env_file=None, codex_bridge_enabled=True, codex_bridge_id=uuid4(),
        codex_bridge_allowed_tenant="synthetic", codex_bridge_host_spool="/synthetic/jobs",
        codex_bridge_executable="/usr/local/bin/codex",
    )
    result = doctor(settings)
    assert result.configured and not result.ready and not result.capabilities_qualified
    assert not result.authenticated and result.model_access == "unverified"
    assert result.failure_code == "bridge_cli_unsupported"
