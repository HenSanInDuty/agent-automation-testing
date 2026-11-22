"""One generation job at a time, under the existing bridge consumer lifetime lock."""

from datetime import UTC, datetime

from auto_at.contracts.codex_bridge import content_hash
from auto_at.contracts.codex_generation import CodexGenerationResponse
from domain.codex_bridge import BridgeProcessResult


class GenerationBridgeService:
    def __init__(self, spool, process):
        self.spool, self.process = spool, process

    async def run_once(self):
        try:
            self.spool.reconcile(datetime.now(UTC))
        except BlockingIOError:
            return
        for job_id in self.spool.jobs():
            request = self.spool.load(job_id)
            if self.spool.has_file(request, "response.json"):
                continue
            reason = self.spool.stop_reason(request, datetime.now(UTC))
            if self.spool.has_file(request, "claim.json"):
                result = BridgeProcessResult(failure_code="bridge_interrupted")
            elif reason == "bridge_policy_revoked":
                continue
            elif reason:
                result = BridgeProcessResult(failure_code=reason)
            else:
                data = self.spool.payload(request)
                self.spool.claim(request)
                result = await self.process.run(
                    request, self.spool.path(job_id), data,
                    lambda req=request: self.spool.stop_reason(req, datetime.now(UTC)),
                )
            reason = self.spool.stop_reason(request, datetime.now(UTC))
            if reason:
                result = BridgeProcessResult(failure_code=reason)
            self.spool.complete(request, CodexGenerationResponse(
                request_hash=content_hash(request), output=result.output,
                failure_code=result.failure_code, usage=result.usage,
            ))
            self.spool.purge_inputs(request)
