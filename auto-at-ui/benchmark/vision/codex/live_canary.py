"""Explicit one-call DOM canary against only the bundled synthetic browser fixture.

Requires the qualified credential-mounted canary container. No application DB,
tenant-policy changes, screenshots to the model, fallback or retry.
"""

import argparse
import asyncio
import hashlib
import json
import tempfile
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
from agents.prompts.codex_exploration import PROMPT_VERSION, build_prompt
from agents.vision.codex_service import output_schema, task_context, validate_candidates
from application.codex_bridge import BridgeService
from auto_at.contracts.codex_bridge import (
    CodexBridgeRequest,
    CodexConsentSnapshot,
    canonical_bytes,
    content_hash,
)
from auto_at.contracts.vision_worker import (
    VisualWorkerAck,
    VisualWorkerAction,
    VisualWorkerExecute,
    VisualWorkerIdentity,
    VisualWorkerObserveDom,
    VisualWorkerOpen,
    VisualWorkerPrepare,
)
from config import Settings
from domain.codex_bridge import CLI_VERSION, validate_response
from infrastructure.codex_bridge.doctor import doctor
from infrastructure.codex_bridge.process import (
    DISABLED_CODE_MODE_WARNING,
    CodexProcess,
    EventReader,
)
from infrastructure.codex_bridge.spool import FileSpool
from infrastructure.vision_worker import HttpVisualWorker


@contextmanager
def safe_event_types(report):
    """Retain closed protocol categories only, never CLI messages or payloads."""
    original = EventReader.event
    categories = set()
    known = {"agent_message", "reasoning", "command_execution", "mcp_tool_call",
             "web_search", "file_change", "todo_list", "error"}

    def event(reader, line):
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict) and isinstance(parsed.get("item"), dict):
                category = parsed["item"].get("type")
                categories.add(category if isinstance(category, str) and category in known
                               else "unknown")
                report["event_item_types"] = sorted(categories)
                if category == "error":
                    if parsed["item"].get("message") == DISABLED_CODE_MODE_WARNING:
                        report["startup_warning"] = "disabled_code_mode_host"
                        return original(reader, line)
                    message = str(parsed["item"].get("message", "")).lower()
                    for label, fragments in (
                        ("response_schema_rejected", ("invalid schema", "response_format",
                                                      "text.format")),
                        ("model_unavailable", ("not supported", "model_not_found",
                                               "does not exist", "unsupported_model")),
                        ("usage_limited", ("usage limit", "quota", "rate limit", "429")),
                        ("login_required", ("refresh", "401", "unauthorized", "authentication")),
                        ("access_denied", ("not have access", "403", "permission")),
                        ("provider_transport_error", ("certificate", "connection", "network",
                                                      "stream disconnected", "timeout")),
                    ):
                        if any(fragment in message for fragment in fragments):
                            report["error_category"] = label
                            break
                    else:
                        report["error_category"] = "unclassified_provider_error"
        except (ValueError, TypeError):
            pass
        return original(reader, line)

    EventReader.event = event
    try:
        yield
    finally:
        EventReader.event = original


async def canary(root: Path, settings: Settings, readiness, report):
    deadline = datetime.now(UTC) + timedelta(seconds=120)
    identity = VisualWorkerIdentity(
        tenant_id="synthetic-canary", project_id=uuid4(), session_id=uuid4(), fencing_token=1,
    )
    browser = await asyncio.create_subprocess_exec(
        "node", "--import", "tsx", "src/fixtures/vision-integration-server.ts",
        cwd="/app/workers/playwright", stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        metadata = json.loads(await asyncio.wait_for(browser.stdout.readline(), 20))
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            worker = HttpVisualWorker(client, metadata["worker"], "integration-fixture-only")

            async def perform(command):
                prepared = await worker.prepare(command)
                if prepared.operation.status == "rejected":
                    raise ValueError("worker rejected canary action")

                async def retain(result):
                    for frame in result.frames:
                        content = await worker.frame(identity, frame)
                        if hashlib.sha256(content).hexdigest() != frame.checksum:
                            raise ValueError("canary evidence checksum")
                        (root / f"{frame.id}.png").write_bytes(content)

                await retain(prepared)
                before = next(f for f in prepared.frames if f.role == "before")
                result = await worker.execute(VisualWorkerExecute(
                    **identity.model_dump(), operation_id=command.operation_id,
                    prepared_handle=prepared.prepared_handle, before_frame_id=before.id,
                    before_checksum=before.checksum, before_persisted=True,
                ))
                await retain(result)
                await worker.acknowledge(VisualWorkerAck(
                    **identity.model_dump(), operation_id=command.operation_id,
                    persisted_frame_ids=tuple(f.id for f in result.frames),
                ))
                return result

            fingerprint = await worker.open(VisualWorkerOpen(
                **identity.model_dump(), target_url=metadata["target"],
                allowed_origins=(metadata["target"],), deadline=deadline,
                max_session_seconds=120, max_states=2, max_hops=1,
                max_screenshot_bytes=1_000_000, required_capabilities=("dom-observation-v1",),
            ))
            try:
                state_id = uuid4()
                opened = await perform(VisualWorkerPrepare(
                    **identity.model_dump(), operation_id=uuid4(), purpose="setup",
                    action=VisualWorkerAction(kind="navigate"),
                    expected_state_fingerprint=fingerprint,
                    checkpoint_id=uuid4(), checkpoint_state_id=state_id,
                ))
                bound = (await worker.observe_dom(VisualWorkerObserveDom(
                    **identity.model_dump(), snapshot_id=uuid4(),
                    expected_state_fingerprint=opened.state_fingerprint,
                ))).data
                obs = bound.observation
                dom, schema = canonical_bytes(obs), output_schema(1)
                consent = CodexConsentSnapshot(
                    dom_transfer_accepted=True, dom_transfer_provider="codex_cli",
                    raw_screenshot_transfer_accepted=False,
                )
                request = CodexBridgeRequest(
                    **{key: getattr(obs, key) for key in (
                        "tenant_id", "project_id", "session_id", "fencing_token", "observation_id",
                        "snapshot_id", "state_fingerprint",
                    )},
                    job_id=uuid4(), bridge_id=settings.codex_bridge_id, correlation_id=uuid4(),
                    request_sequence=1, stage="dom", prompt_version=PROMPT_VERSION,
                    created_at=datetime.now(UTC), deadline=deadline,
                    context=task_context(
                        "Click Toggle modal once on this synthetic controls page."
                    ),
                    consent=consent, consent_hash=content_hash(consent), candidate_limit=1,
                    dom_element_count=len(obs.elements), inputs={
                        "dom_sha256": hashlib.sha256(dom).hexdigest(), "dom_bytes": len(dom),
                        "schema_sha256": hashlib.sha256(schema).hexdigest(),
                        "schema_bytes": len(schema),
                    },
                )
                spool = FileSpool(Path(settings.codex_bridge_container_spool),
                                  settings.codex_bridge_id, identity.tenant_id)
                spool.publish(request, dom, schema)
                assert not spool.has_file(request, "screenshot.png")

                async def authorize():
                    while True:
                        spool.authorize(request, min(datetime.now(UTC) + timedelta(seconds=8),
                                                     deadline))
                        await asyncio.sleep(2)

                spool.authorize(request, min(datetime.now(UTC) + timedelta(seconds=8), deadline))
                renewal = asyncio.create_task(authorize())
                service = BridgeService(settings, spool, CodexProcess("/usr/local/bin/codex"),
                                        build_prompt, readiness.model_copy(update={"online": True}))
                report["cli_calls"] = 1
                try:
                    with safe_event_types(report):
                        await service.run_once()
                finally:
                    renewal.cancel()
                    await asyncio.gather(renewal, return_exceptions=True)
                response = spool.result(request)
                validate_response(request, response, now=datetime.now(UTC))
                report.update(
                    actual_model=response.actual_model,
                    usage=response.usage.model_dump() if response.usage else None,
                    failure_code=response.failure_code,
                )
                if response.failure_code:
                    return
                report["model_access"] = "available"
                report["proposal_outcome"] = response.output.outcome
                if response.output.outcome == "stop":
                    report["stop_reason"] = response.output.reason
                    report["failure_code"] = "canary_expected_target_not_proposed"
                    return
                if response.output.outcome == "need_screenshot":
                    report["failure_code"] = "image_consent_required"
                    return
                batch = validate_candidates(response.output, bound, stage="dom", max_candidates=1)
                binding = batch.target_bindings[0]
                if binding is None or binding.expected_descriptor.value != "Toggle modal":
                    report["failure_code"] = "canary_expected_target_not_proposed"
                    return
                action = batch.actions[0]
                result = await perform(VisualWorkerPrepare(
                    **identity.model_dump(), operation_id=uuid4(), purpose="explore",
                    action=VisualWorkerAction.model_validate(action.model_dump(
                        exclude={"confidence", "expected_outcome"})),
                    expected_state_fingerprint=obs.state_fingerprint, state_id=state_id,
                    proposal_id=uuid4(), expected_locator=binding.expected_descriptor,
                    dom_snapshot_id=binding.snapshot_id, dom_element_id=binding.element_id,
                ))
                visits = (await client.get(metadata["worker"] + "/fixture-visits")).json()
                if (result.operation.status != "completed" or result.locator.status != "verified"
                        or not result.operation.executed_click
                        or result.state_fingerprint == obs.state_fingerprint
                        or visits.get("/a", 0) != 0 or visits.get("/b", 0) != 0):
                    raise ValueError("canary action verification failed")
                report.update(verified_actions=1, status="passed")
                spool.acknowledge(request)
                spool.reconcile(datetime.now(UTC))
            finally:
                await worker.close(identity)
    finally:
        if browser.returncode is None:
            browser.terminate()
            await asyncio.wait_for(browser.wait(), 10)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-dom", action="store_true", required=True)
    parser.parse_args()
    report = {"classification": "synthetic_live_dom", "status": "blocked",
              "cli_version": CLI_VERSION, "cli_mode": "yolo_container",
              "prompt_version": PROMPT_VERSION,
              "synthetic_task": "toggle_modal",
              "requested_model": "gpt-6-luna", "model_access": "unverified",
              "cli_calls": 0, "image_calls": 0, "verified_actions": 0, "failure_code": None}
    began = monotonic()
    with tempfile.TemporaryDirectory(prefix="codex-live-") as temporary:
        root = Path(temporary)
        settings = Settings(
            _env_file=None, codex_bridge_enabled=True, codex_bridge_id=uuid4(),
            codex_bridge_allowed_tenant="synthetic-canary",
            codex_bridge_host_spool=str(root / "jobs"),
            codex_bridge_container_spool=str(root / "jobs"),
            codex_bridge_executable="/usr/local/bin/codex",
        )
        readiness = doctor(settings)
        if not readiness.capabilities_qualified or not readiness.authenticated:
            report["failure_code"] = readiness.failure_code
        else:
            async def bounded():
                async with asyncio.timeout(120):
                    await canary(root, settings, readiness, report)
            try:
                asyncio.run(bounded())
            except TimeoutError:
                report["failure_code"] = "bridge_deadline_exceeded"
            except Exception:
                report["failure_code"] = "canary_validation_failed"
    report["elapsed_seconds"] = round(monotonic() - began, 3)
    Path("/tmp/codex-live-canary.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report), flush=True)
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
