"""One consumer orchestrates scoped file jobs; it never contacts application storage."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

from agents.prompts.codex_exploration import with_response_schema
from auto_at.contracts.codex_bridge import (
    CodexBridgeReadiness,
    CodexBridgeRequest,
    CodexBridgeResponse,
    content_hash,
)
from config import Settings
from domain.codex_bridge import CLI_VERSION, BridgeProcessResult
from domain.ports import CodexBridgeHostSpool, CodexBridgeProcessPort


class BridgeService:
    def __init__(
        self, settings: Settings, spool: CodexBridgeHostSpool, process: CodexBridgeProcessPort,
        prompt: Callable[[CodexBridgeRequest, bytes], bytes], readiness: CodexBridgeReadiness,
    ):
        self.settings, self.spool, self.process = settings, spool, process
        self.prompt, self.readiness = prompt, readiness

    async def run_once(self) -> int:
        if not self.settings.codex_bridge_enabled or not self.readiness.ready:
            return 0
        with self.spool.lock(consumer=True):
            return await self._run_locked()

    async def _run_locked(self) -> int:
        self.spool.reconcile(datetime.now(UTC))
        processed = 0
        for job_id in self.spool.jobs():
            request = self.spool.load(job_id)
            if self.spool.has_file(request, "response.json"):
                continue
            started = datetime.now(UTC)
            stop = self.spool.stop_reason(request, started)
            if self.spool.has_file(request, "claim.json"):
                result = BridgeProcessResult(failure_code="bridge_interrupted")
            elif stop == "bridge_policy_revoked":
                # Producer publishes then authorizes; do not race that handoff.
                continue
            elif stop:
                result = BridgeProcessResult(failure_code=stop)
            else:
                dom, schema = self.spool.verify_inputs(request)
                prompt = with_response_schema(self.prompt(request, dom), schema)
                self.spool.claim(request)
                self.spool.record_stage(request, "claimed")
                self.spool.record_stage(request, "running")
                self.readiness = self.readiness.model_copy(update={"busy": True})
                try:
                    result = await self.process.run(
                        request, self.spool.path(job_id), prompt,
                        lambda req=request: self.spool.stop_reason(req, datetime.now(UTC)),
                    )
                finally:
                    self.readiness = self.readiness.model_copy(update={"busy": False})
            stopped = self.spool.stop_reason(request, datetime.now(UTC))
            if stopped:
                result = BridgeProcessResult(failure_code=stopped)
            identity = {key: getattr(request, key) for key in (
                "tenant_id", "project_id", "session_id", "fencing_token", "job_id",
                "bridge_id", "correlation_id", "request_sequence", "observation_id",
                "snapshot_id", "state_fingerprint", "stage",
            )}
            envelope = dict(
                **identity, request_hash=content_hash(request),
                cli_version=CLI_VERSION, started_at=started, completed_at=datetime.now(UTC),
            )
            try:
                response = CodexBridgeResponse(
                    **envelope, output=result.output, failure_code=result.failure_code,
                    usage=result.usage, actual_model=result.actual_model,
                )
                self.spool.complete(request, response)
            except ValueError:
                response = CodexBridgeResponse(
                    **envelope, actual_model=None,
                    failure_code=self.spool.stop_reason(request, datetime.now(UTC))
                    or "bridge_malformed_output",
                )
                self.spool.complete(request, response)
            if response.failure_code:
                self.spool.purge_inputs(request)
            self.spool.record_stage(
                request, "failed" if response.failure_code else "completed", response.usage,
            )
            processed += 1
        return processed

    async def serve(self, stopped: asyncio.Event):
        async def heartbeat():
            while not stopped.is_set():
                self.spool.heartbeat(self.readiness.model_dump(mode="json"))
                await asyncio.sleep(self.settings.codex_bridge_heartbeat_seconds)

        async def jobs():
            while not stopped.is_set():
                await self._run_locked()
                await asyncio.sleep(self.settings.codex_bridge_cancel_poll_seconds)

        if not self.settings.codex_bridge_enabled or not self.readiness.ready:
            return
        # Own the lock for the whole service lifetime, including idle heartbeats.
        with self.spool.lock(consumer=True):
            tasks = [asyncio.create_task(heartbeat()), asyncio.create_task(jobs())]
            try:
                done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                self.spool.heartbeat(CodexBridgeReadiness().model_dump(mode="json"))
