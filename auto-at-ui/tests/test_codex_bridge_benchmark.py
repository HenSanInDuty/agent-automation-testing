"""Offline provenance and child-process isolation checks; never invokes a provider."""

import asyncio
import importlib.util
import json
import shutil
import socket
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from agents.prompts.codex_exploration import PROMPT_VERSION
from auto_at.contracts.codex_bridge import CodexBridgeReadiness, parse_codex_output
from config import Settings
from domain.codex_bridge import BridgeProcessResult

ROOT = Path(__file__).resolve().parents[1]


def load_harness():
    spec = importlib.util.spec_from_file_location(
        "codex_offline_harness", ROOT / "benchmark/vision/codex/run_offline.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_offline_manifest_provenance_and_explicit_live_boundary():
    manifest = json.loads((ROOT / "benchmark/vision/codex/manifest.json").read_text())
    assert manifest["classification"] == "synthetic_local_only"
    assert manifest["responses"] == "fake_cli"
    assert manifest["prompt_version"] == PROMPT_VERSION
    assert manifest["live_canary"] in {"not_run", "blocked", "passed"}
    assert manifest["playwright_version"] == "1.50.1"
    assert manifest["model"] == "gpt-6-luna"
    for path, expected in manifest["sources"].items():
        assert sha256((ROOT / path).read_text(encoding="utf-8").encode()).hexdigest() == expected
    required = {"dom_only", "image_escalation", "image_denied", "invalid_output", "stale_dom",
                "policy_revoked", "restart", "cancel", "prompt_injection", "child_network"}
    assert required <= {case["id"] for case in manifest["cases"]}
    for case in manifest["cases"]:
        assert (ROOT / case["evidence"]).is_file()


def test_offline_launcher_shares_only_an_owned_network_namespace():
    harness = load_harness()
    args = harness.suite_args("owned-db", "owned-suite", ["-q"])
    assert args[args.index("--network") + 1] == "container:owned-db"
    assert not any(value in args for value in ("--volume", "-v", "--mount", "--env-file"))
    assert not any("auth.json" in value or "docker.sock" in value for value in args)
    with pytest.raises(ValueError, match="excluded"):
        harness.suite_args("db", "suite", ["tests/test_playwright_worker_compose.py"])


@pytest.mark.skipif(
    not Path("/offline-evaluation").is_file(), reason="run in offline harness image"
)
def test_offline_namespace_blocks_python_and_node_children():
    assert shutil.which("codex") is None
    assert not (ROOT / ".env").exists()
    assert not Path("/bridge-home/.codex/auth.json").exists()
    assert {name for _, name in socket.if_nameindex()} == {"lo"}
    python = subprocess.run([
        sys.executable, "-c",
        "import socket; socket.create_connection(('198.51.100.1', 443), 1)",
    ], capture_output=True, timeout=5)
    assert python.returncode != 0
    node = subprocess.run([
        "node", "-e",
        "const s=require('net').connect(443,'198.51.100.1');"
        "s.on('connect',()=>process.exit(7));"
        "s.on('error',()=>process.exit(0));"
        "s.setTimeout(1000,()=>process.exit(8));",
    ], capture_output=True, timeout=5)
    assert node.returncode == 0


def test_opt_in_overlay_keeps_credentials_out_of_producers():
    overlay = (ROOT / "docker-compose.codex.yml").read_text()
    producers, bridge = overlay.split("  codex-bridge:", 1)
    assert "auth.json" not in producers and "CODEX_BRIDGE_AUTH_FILE" not in producers
    assert "${CODEX_BRIDGE_ENABLED:-false}" in producers
    assert "${VISION_TRACE_V4_ENABLED:-false}" in producers
    assert "profiles: [codex]" in bridge and "read_only: true" in bridge
    assert "cap_drop: [ALL]" in bridge and "no-new-privileges:true" in bridge
    assert "networks: [codex-egress]" in bridge
    assert "docker.sock" not in overlay and "privileged:" not in overlay


def test_canary_launcher_and_diagnostics_preserve_the_private_boundary():
    modules = []
    for filename in ("run_live.py", "live_canary.py"):
        spec = importlib.util.spec_from_file_location(
            "canary_" + filename, ROOT / "benchmark/vision/codex" / filename
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    launcher, canary = modules
    args = launcher.canary_args("owned-canary", Path("/private/auth.json"))
    assert args.count("--mount") == 1 and "--env-file" not in args and "--publish" not in args
    assert args[args.index("--mount") + 1].endswith("/auth.json,readonly")
    assert "/bridge-home/.codex:rw,nosuid,nodev,uid=1001,gid=1001,mode=700,size=32m" in args
    assert args[args.index("--network") + 1] == "bridge"
    report = {}
    from infrastructure.codex_bridge.process import EventReader, ProcessRejected
    original = EventReader.event
    with canary.safe_event_types(report), pytest.raises(ProcessRejected):
        EventReader().event(b'{"type":"item.completed","item":{"type":"error",'
                            b'"message":"SENSITIVE_VALUE_MUST_NOT_SURVIVE"}}')
    assert report == {"event_item_types": ["error"],
                      "error_category": "unclassified_provider_error"}
    assert EventReader.event is original


@pytest.mark.parametrize("provider", ["huggingface", "gemini", "codex_cli"])
def test_rollback_preparation_preserves_other_overrides_and_the_source(provider):
    spec = importlib.util.spec_from_file_location(
        "codex_rollback", ROOT / "docker/codex-bridge/rollback_policy.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    original = {"generation": {"max_steps": 2}, "vision": {
        "provider": provider, "model": "fixture", "enabled": True, "max_steps": 3,
        "codex": {"dom_transfer_accepted": True}, "raw_screenshot_transfer_accepted": True,
        "raw_screenshot_transfer_provider": provider,
    }}
    snapshot = json.dumps(original, sort_keys=True)
    transformed = module.rollback_override(original, "huggingface", "previous/hf-model")
    assert transformed["generation"] == original["generation"]
    assert transformed["vision"]["max_steps"] == 3
    assert transformed["vision"]["provider"] == "huggingface"
    assert transformed["vision"]["model"] == "previous/hf-model"
    assert transformed["vision"]["enabled"] is False
    assert transformed["vision"]["raw_screenshot_transfer_accepted"] is False
    assert transformed["vision"]["raw_screenshot_transfer_provider"] is None
    assert "codex" not in transformed["vision"]
    assert json.dumps(original, sort_keys=True) == snapshot


@pytest.mark.skipif(
    not Path("/offline-evaluation").is_file(), reason="run in offline harness image"
)
@pytest.mark.parametrize("needs_image", [False, True])
def test_live_canary_path_with_fake_process_and_no_credentials(tmp_path, monkeypatch, needs_image):
    spec = importlib.util.spec_from_file_location(
        "codex_live_canary", ROOT / "benchmark/vision/codex/live_canary.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    calls = []

    class FakeProcess:
        def __init__(self, _executable):
            pass

        async def run(self, request, directory, prompt, stop):
            calls.append(request)
            assert request.stage == "dom" and request.candidate_limit == 1
            assert not request.consent.raw_screenshot_transfer_accepted
            assert not (directory / "screenshot.png").exists()
            observation = json.loads((directory / "dom.json").read_text())
            element = next(e for e in observation["elements"] if e["name"] == "Toggle modal")
            output = {
                "outcome": "candidates", "candidates": [{
                    "kind": "click", "element_id": element["element_id"], "confidence": 0.9,
                    "expected_outcome": "Open synthetic branch",
                }],
            }
            if needs_image:
                output = {"outcome": "need_screenshot", "reason": "visual_target"}
            return BridgeProcessResult(output=parse_codex_output(json.dumps(output).encode()))

    monkeypatch.setattr(module, "CodexProcess", FakeProcess)
    settings = Settings(
        _env_file=None, codex_bridge_enabled=True, codex_bridge_id=uuid4(),
        codex_bridge_allowed_tenant="synthetic-canary",
        codex_bridge_host_spool=str(tmp_path / "jobs"),
        codex_bridge_container_spool=str(tmp_path / "jobs"),
        codex_bridge_executable="/usr/local/bin/codex",
    )
    readiness = CodexBridgeReadiness(configured=True, online=True, authenticated=True,
                                    capabilities_qualified=True)
    report = {"status": "blocked", "image_calls": 0, "verified_actions": 0}
    asyncio.run(module.canary(tmp_path, settings, readiness, report))
    assert len(calls) == report["cli_calls"] == 1
    assert report["image_calls"] == 0
    assert report["verified_actions"] == (0 if needs_image else 1)
    assert report["status"] == ("blocked" if needs_image else "passed")
    assert report["failure_code"] == ("image_consent_required" if needs_image else None)
