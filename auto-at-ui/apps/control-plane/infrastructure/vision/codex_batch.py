"""Durable registration precedes file publication; no API-key or image-store fallback."""

import asyncio
import hashlib
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from agents.prompts.codex_exploration import PROMPT_VERSION
from agents.shared.runtime import VisionPolicy
from agents.vision.codex_service import output_schema
from application.codex_candidates import CodexImage, CodexUnavailable, require_dom_policy
from application.vision_model_batch import VisionModelSession
from auto_at.contracts.codex_bridge import (
    CodexBoundObservation,
    CodexBridgeRequest,
    CodexBridgeResponse,
    CodexConsentSnapshot,
    CodexTaskContext,
    canonical_bytes,
    content_hash,
)
from domain.codex_bridge import validate_response
from domain.ports import CodexBridgeReadinessPort, CodexBridgeSpool, CodexJobGateway


class CodexModelBatch:
    def __init__(
        self, *, bridge_id, spool: CodexBridgeSpool, gateway: CodexJobGateway,
        readiness: CodexBridgeReadinessPort, poll_seconds: float = 0.2,
    ):
        if not 0 < poll_seconds <= 2:
            raise ValueError("invalid bridge poll interval")
        self.bridge_id, self.spool, self.gateway = bridge_id, spool, gateway
        self.readiness, self.poll_seconds = readiness, poll_seconds

    async def __call__(
        self, *, session: VisionModelSession, bound: CodexBoundObservation,
        context: CodexTaskContext, policy: VisionPolicy, sequence: int, deadline: datetime,
        max_candidates: int, image: CodexImage | None,
        check_policy: Callable[[], VisionPolicy],
    ) -> CodexBridgeResponse:
        require_dom_policy(policy)
        observation = bound.observation
        if (not session.correlation_id or not session.project_id or not session.fencing_token
                or session.tenant_id != observation.tenant_id
                or session.id != observation.session_id
                or session.project_id != observation.project_id
                or session.fencing_token != observation.fencing_token
                or (session.provider, session.model) != (policy.provider, policy.model)):
            raise CodexUnavailable("bridge_stale_result")
        dom = canonical_bytes(observation)
        schema = output_schema(max_candidates)
        if image:
            image.validate(bound, policy.max_screenshot_bytes)
        consent = CodexConsentSnapshot(
            **policy.codex.model_dump(),
            raw_screenshot_transfer_accepted=policy.raw_screenshot_transfer_accepted,
            raw_screenshot_transfer_provider=policy.raw_screenshot_transfer_provider,
        )
        request = CodexBridgeRequest(
            **{key: getattr(observation, key) for key in (
                "tenant_id", "project_id", "session_id", "fencing_token", "observation_id",
                "snapshot_id", "state_fingerprint",
            )}, job_id=uuid4(), bridge_id=self.bridge_id, correlation_id=session.correlation_id,
            request_sequence=sequence, prompt_version=PROMPT_VERSION,
            stage="image" if image else "dom",
            created_at=datetime.now(UTC), deadline=deadline, consent=consent,
            consent_hash=content_hash(consent), candidate_limit=max_candidates, context=context,
            dom_element_count=len(observation.elements),
            inputs={
                "dom_sha256": hashlib.sha256(dom).hexdigest(), "dom_bytes": len(dom),
                "schema_sha256": hashlib.sha256(schema).hexdigest(), "schema_bytes": len(schema),
                "screenshot_sha256": image.sha256 if image else None,
                "screenshot_bytes": len(image.data) if image else None,
            },
        )

        def check():
            live = check_policy()
            require_dom_policy(live)
            if (live.model != session.model or sequence > live.max_steps
                    or len(dom) > live.codex.max_dom_bytes
                    or len(observation.elements) > live.codex.max_dom_elements
                    or image and (not live.raw_screenshot_transfer_accepted
                                  or live.raw_screenshot_transfer_provider != "codex_cli"
                                  or len(image.data) > live.max_screenshot_bytes)):
                raise CodexUnavailable("policy_changed")
            if datetime.now(UTC) >= deadline:
                raise CodexUnavailable("provider_timeout")
            if not self.readiness.read(session.tenant_id, datetime.now(UTC)).ready:
                raise CodexUnavailable("bridge_offline")

        check()
        registered = published = finished = False
        try:
            async with asyncio.timeout((deadline - datetime.now(UTC)).total_seconds()):
                await self.gateway.register(request)
                registered = True
                check()
                self.spool.publish(request, dom, schema, image.data if image else None)
                published = True
                last_authorization = None
                while True:
                    check()
                    await self.gateway.poll(request, self.spool.stages(request))
                    now = datetime.now(UTC)
                    if (last_authorization is None
                            or (now - last_authorization).total_seconds() >= 2):
                        self.spool.authorize(request, min(now + timedelta(seconds=8), deadline))
                        last_authorization = now
                    response = self.spool.result(request)
                    if response is not None:
                        validate_response(request, response, now=datetime.now(UTC))
                        check()
                        await self.gateway.finish(request, response)
                        finished = True
                        self.spool.acknowledge(request)
                        return response
                    await asyncio.sleep(self.poll_seconds)
        except (asyncio.CancelledError, TimeoutError):
            await self._cancel(request, published, registered and not finished, "bridge_cancelled")
            raise
        except Exception as exc:
            await self._cancel(request, published, registered and not finished,
                               "bridge_policy_revoked")
            if isinstance(exc, CodexUnavailable):
                raise
            raise CodexUnavailable(
                "bridge_malformed_output" if isinstance(exc, ValueError) else "bridge_io_error",
            ) from exc

    async def _cancel(self, request, published, registered, reason):
        try:
            if published:
                self.spool.cancel(request)
        finally:
            if registered:
                await self.gateway.cancel(request, reason)
        if published:
            # A short shutdown allowance does not authorize any additional model/browser work.
            try:
                async with asyncio.timeout(5):
                    while not self.spool.cancellation_acknowledged(request):
                        await asyncio.sleep(self.poll_seconds)
            except TimeoutError:
                # Authorization expires independently; durable cancellation fences late results.
                await self.gateway.cleanup_pending(request)
