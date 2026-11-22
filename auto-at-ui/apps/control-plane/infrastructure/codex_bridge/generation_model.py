"""Bounded, consent-checked text model client; credentials stay inside the bridge."""

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from agents.prompts.generation import GENERATION_PLANNER_SYSTEM_PROMPT
from agents.prompts.vision_generation import SYSTEM_PROMPT
from agents.shared.redaction import redact_value
from agents.shared.runtime import AGENT_RUNTIME_CONFIG_KEY, resolve_agent_runtime
from auto_at.contracts.codex_bridge import content_hash
from auto_at.contracts.codex_generation import CodexGenerationJob
from domain.runs import AuditEvent
from sqlalchemy.exc import IntegrityError

from infrastructure.codex_bridge.doctor import FileReadiness
from infrastructure.codex_bridge.generation_spool import GenerationSpool
from infrastructure.persistence.models import ConfigurationModel
from infrastructure.persistence.repositories import (
    SqlAlchemyAuditEventRepository,
    SqlAlchemyConfigurationRepository,
)


class GenerationBridgeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class CodexGenerationModel:
    def __init__(self, *, settings, request, policy, read_policy, on_event=lambda *_: None,
                 reserve_call, spool=None, readiness=None, poll_seconds=0.2):
        self.settings, self.request, self.policy = settings, request, policy
        self.read_policy, self.on_event, self.poll_seconds = read_policy, on_event, poll_seconds
        self.readiness = readiness or FileReadiness(settings)
        self.spool = spool
        self.reserve_call = reserve_call

    def check(self):
        s, req = self.settings, self.request
        if (not s.codex_bridge_enabled or req.tenant_id != s.codex_bridge_allowed_tenant
                or self.policy.provider != "codex_cli" or not self.policy.text_transfer_accepted):
            raise GenerationBridgeError("bridge_policy_revoked")
        current = self.read_policy()
        if content_hash(current) != content_hash(self.policy):
            raise GenerationBridgeError("bridge_policy_revoked")
        if not self.readiness.read(req.tenant_id, datetime.now(UTC)).ready:
            raise GenerationBridgeError("bridge_offline")

    async def ainvoke(self, payload, **_kwargs):
        self.check()
        messages = payload["messages"]
        if len(messages) != 2 or messages[0]["role"] != "system" or messages[1]["role"] != "user":
            raise GenerationBridgeError("bridge_malformed_output")
        system = messages[0]["content"]
        if system not in {SYSTEM_PROMPT, GENERATION_PLANNER_SYSTEM_PROMPT}:
            raise GenerationBridgeError("bridge_malformed_output")
        context = json.loads(messages[1]["content"])
        if "target_url" in context:
            url = urlsplit(context["target_url"])
            context["target_url"] = urlunsplit((url.scheme, url.netloc, url.path, "", ""))
        context["redacted_request"] = redact_value(context["redacted_request"])
        data = json.dumps(context, separators=(",", ":"), ensure_ascii=False).encode()
        if len(data) > 100_000:
            raise GenerationBridgeError("bridge_output_limit")
        now = datetime.now(UTC)
        job = CodexGenerationJob(
            job_id=self.request.id, bridge_id=self.settings.codex_bridge_id,
            tenant_id=self.request.tenant_id, project_id=self.request.project_id,
            correlation_id=self.request.correlation_id,
            kind="vision" if system == SYSTEM_PROMPT else "text",
            input_hash=hashlib.sha256(data).hexdigest(), input_bytes=len(data),
            policy_hash=content_hash(self.policy), created_at=now,
            deadline=now + timedelta(seconds=self.policy.max_seconds),
        )
        spool = self.spool or GenerationSpool(
            Path(self.settings.codex_bridge_container_spool) / ".generation",
            job.bridge_id, job.tenant_id, owner_uid=self.settings.codex_bridge_spool_owner_uid,
        )
        published = False
        try:
            # A recovered request must never silently launch a second CLI call.
            if spool.path(job.job_id).exists():
                raise GenerationBridgeError("bridge_interrupted")
            self.reserve_call(job)
            spool.publish(job, data)
            published = True
            self.on_event("queued", {"job_id": str(job.job_id), "provider": "codex_cli"})
            last_lease = None
            started = False
            async with asyncio.timeout(self.policy.max_seconds):
                while True:
                    self.check()
                    now = datetime.now(UTC)
                    if now >= job.deadline:
                        raise TimeoutError
                    if last_lease is None or (now - last_lease).total_seconds() >= 2:
                        spool.authorize(job, min(job.deadline, now + timedelta(seconds=8)))
                        last_lease = now
                    if not started and spool.has_file(job, "claim.json"):
                        started = True
                        self.on_event("started", {"job_id": str(job.job_id)})
                    result = spool.result(job)
                    if result is not None:
                        if result.failure_code:
                            raise GenerationBridgeError(result.failure_code)
                        self.check()
                        output = result.output.model_dump_json()
                        self.on_event("completed", {
                            "job_id": str(job.job_id), "provider": "codex_cli",
                            "model": job.model,
                            "usage": ({key.replace("tokens", "count"): value
                                       for key, value in result.usage.model_dump().items()}
                                      if result.usage else None),
                        })
                        # Retain the claimed request until expiry, so a transaction rollback
                        # cannot repeat model execution. The bridge purges input immediately.
                        return {"choices": [{"message": {"content": output}}]}
                    await asyncio.sleep(self.poll_seconds)
        except TimeoutError:
            if published:
                spool.cancel(job)
            raise GenerationBridgeError("bridge_deadline_exceeded") from None
        except BaseException:
            if published:
                spool.cancel(job)
            raise


def generation_model_factory(settings, session_factory):
    def create(request, policy, on_event):
        def read_policy():
            with session_factory() as session:
                stored = SqlAlchemyConfigurationRepository(session).get(
                    request.tenant_id, AGENT_RUNTIME_CONFIG_KEY,
                )
                return resolve_agent_runtime(settings, stored).generation_policy()
        def reserve_call(job):
            # This short independent transaction commits before CLI publication.
            # The unique tenant/key reservation survives worker rollback, restart
            # and spool expiry. A new human request is required to retry.
            from uuid import uuid4
            with session_factory() as session:
                session.add(ConfigurationModel(
                    tenant_id=job.tenant_id, key=f"generation.codex.call.v1.{job.job_id}",
                    value={"job_id": str(job.job_id), "policy_hash": job.policy_hash,
                           "input_hash": job.input_hash, "model": job.model,
                           "correlation_id": str(job.correlation_id),
                           "created_at": job.created_at.isoformat()},
                ))
                try:
                    session.flush()
                    SqlAlchemyAuditEventRepository(session).append(AuditEvent(
                        id=uuid4(), tenant_id=job.tenant_id, actor="test-generation-planner",
                        action="generation.codex.reserved", entity_type="generation_request",
                        entity_id=job.job_id, correlation_id=job.correlation_id,
                    ))
                    session.commit()
                except IntegrityError:
                    session.rollback()
                    raise GenerationBridgeError("bridge_interrupted") from None
        return CodexGenerationModel(settings=settings, request=request, policy=policy,
                                    read_policy=read_policy, reserve_call=reserve_call,
                                    on_event=on_event)
    return create
