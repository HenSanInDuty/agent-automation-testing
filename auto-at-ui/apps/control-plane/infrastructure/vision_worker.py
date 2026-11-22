"""Bounded private v4 transport. No worker path or diagnostic crosses this boundary."""

import json
import logging
from hashlib import sha256
from time import monotonic
from uuid import UUID

import httpx
from auto_at.contracts.codex_bridge import canonical_bytes
from auto_at.contracts.vision import VisualCheckpoint, VisualOperationFrame
from auto_at.contracts.vision_worker import (
    VisualWorkerAck,
    VisualWorkerCheckTarget,
    VisualWorkerDomObservation,
    VisualWorkerExecute,
    VisualWorkerIdentity,
    VisualWorkerObserveDom,
    VisualWorkerOpen,
    VisualWorkerOperationResult,
    VisualWorkerOriginObservations,
    VisualWorkerPrepare,
    VisualWorkerTargetCheck,
)
from domain.vision import VisionObservationUnavailable
from pydantic import ValidationError

from infrastructure.observability.logging import log_event
from infrastructure.observability.telemetry import current_trace_context

_LOGGER = logging.getLogger(__name__)
# Closed operational vocabulary. Never log arbitrary worker bodies/diagnostics.
_WORKER_CODES = frozenset({
    "session_unavailable", "stale_fencing_token", "scope_mismatch", "invalid_contract",
    "capture_failed", "screenshot_byte_limit", "session_timeout", "step_timeout",
    "worker_idle_timeout", "session_busy", "payload_too_large", "visual_request_rejected",
    "operation_unavailable", "frame_unavailable", "frame_checksum_mismatch",
    "checkpoint_unavailable", "state_mismatch", "state_changed_during_observation",
    "stale_dom_context", "stale_dom_target", "stale_dom_snapshot",
})


def _worker_code(data: bytes) -> str:
    try:
        value = json.loads(data)
        code = value.get("detail") if isinstance(value, dict) else None
    except (ValueError, TypeError):
        code = None
    return code if isinstance(code, str) and code in _WORKER_CODES else "worker_request_rejected"


class VisualWorkerUnavailable(RuntimeError):
    pass


class HttpVisualWorker:
    def __init__(self, client: httpx.AsyncClient, base_url: str, secret: str) -> None:
        self._client, self._base, self._secret = client, base_url.rstrip("/"), secret

    def _headers(self, identity: VisualWorkerIdentity) -> dict[str, str]:
        context = current_trace_context()
        return {
            "X-Auto-At-Vision-Worker-Secret": self._secret,
            "X-Auto-At-Vision-Tenant-Id": identity.tenant_id,
            "X-Auto-At-Vision-Project-Id": str(identity.project_id),
            "X-Auto-At-Vision-Fencing-Token": str(identity.fencing_token),
            **({"X-Correlation-Id": str(context.correlation_id),
                "traceparent": context.traceparent()} if context else {}),
        }

    async def _request(self, method, path, identity, payload=None, *, cap=128_000):
        started = monotonic()
        # The path is private transport metadata; emit only a bounded route stage.
        suffix = path.rsplit("/", 1)[-1]
        stage = suffix if suffix in {
            "screen", "dom", "origins", "prepare", "execute", "ack", "visual-explorations",
        } else "scoped_resource"
        fields = {"session_id": str(identity.session_id), "project_id": str(identity.project_id),
                  "method": method, "stage": stage}
        operation_id = getattr(payload, "operation_id", None)
        if operation_id is not None:
            fields["operation_id"] = str(operation_id)
        try:
            async with self._client.stream(
                method,
                self._base + path,
                headers=self._headers(identity),
                json=payload.model_dump(mode="json") if payload is not None else None,
            ) as response:
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64_000):
                    if len(data) + len(chunk) > cap:
                        raise VisualWorkerUnavailable("worker response exceeds cap")
                    data.extend(chunk)
                if response.is_error:
                    log_event(_LOGGER, logging.WARNING, "vision.worker.rejected",
                              "Visual worker rejected an internal request.", **fields,
                              status_code=response.status_code, code=_worker_code(bytes(data)),
                              duration_ms=round((monotonic() - started) * 1000))
                if response.status_code == 422 and path.endswith("/observations/dom"):
                    try:
                        value = json.loads(data)
                        code = value.get("detail") if isinstance(value, dict) else None
                    except (ValueError, TypeError):
                        code = None
                    raise VisionObservationUnavailable(code if isinstance(code, str) else "")
                response.raise_for_status()
                return bytes(data), response.headers.get("content-type", "").split(";")[0]
        except httpx.HTTPStatusError:
            raise VisualWorkerUnavailable("visual worker transport unavailable") from None
        except httpx.HTTPError as error:
            log_event(_LOGGER, logging.WARNING, "vision.worker.transport_failed",
                      "Visual worker transport unavailable.", **fields,
                      error_type="timeout" if isinstance(error, httpx.TimeoutException)
                      else "connection_error", duration_ms=round((monotonic() - started) * 1000))
            raise VisualWorkerUnavailable("visual worker transport unavailable") from None

    async def open(self, request: VisualWorkerOpen) -> str:
        import json

        data, _ = await self._request("POST", "/visual-explorations", request, request)
        value = json.loads(data)
        if not set(request.required_capabilities) <= set(value.get("capabilities", [])):
            raise VisualWorkerUnavailable("worker DOM capability unavailable")
        fingerprint = value.get("state_fingerprint", "")
        if (
            value.get("session_id") != str(request.session_id)
            or value.get("contract_version") != "v4"
            or value.get("operation_budget") != 1 + request.max_states * (2 * request.max_hops + 3)
            or len(fingerprint) != 64
            or any(c not in "0123456789abcdef" for c in fingerprint)
        ):
            raise VisualWorkerUnavailable("worker capability response invalid")
        return fingerprint

    async def check_target(self, request: VisualWorkerCheckTarget) -> VisualWorkerTargetCheck:
        data, content_type = await self._request(
            "POST", f"/visual-explorations/{request.session_id}/observations/target", request,
            request, cap=4096,
        )
        try:
            result = VisualWorkerTargetCheck.model_validate_json(data)
        except ValidationError:
            raise VisualWorkerUnavailable("worker target check invalid") from None
        if (content_type != "application/json" or any(
            getattr(result, key) != value for key, value in request.model_dump().items()
        ) or (result.matches_current and (not result.context_matches
            or (not result.same_document and not request.allow_restored_document)))):
            raise VisualWorkerUnavailable("worker target check scope mismatch")
        return result

    async def observe_dom(self, request: VisualWorkerObserveDom) -> VisualWorkerDomObservation:
        data, content_type = await self._request(
            "POST", f"/visual-explorations/{request.session_id}/observations/dom", request,
            request, cap=256_000,
        )
        try:
            result = VisualWorkerDomObservation.model_validate_json(data)
        except ValidationError:
            raise VisualWorkerUnavailable("worker DOM observation invalid") from None
        obs = result.data.observation
        if (content_type != "application/json"
                or any(getattr(result, key) != getattr(request, key) for key in (
                    "tenant_id", "project_id", "session_id", "fencing_token", "capability",
                ))
                or obs.snapshot_id != request.snapshot_id
                or obs.state_fingerprint != request.expected_state_fingerprint
                or len(obs.elements) > request.max_elements
                or len(canonical_bytes(obs)) > request.max_bytes):
            raise VisualWorkerUnavailable("worker DOM observation scope or limit mismatch")
        return result

    async def screen(self, identity: VisualWorkerIdentity) -> bytes:
        data, content_type = await self._request(
            "GET", f"/visual-explorations/{identity.session_id}/screen", identity, cap=2_000_000,
        )
        if content_type != "image/png" or not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise VisualWorkerUnavailable("worker screen invalid")
        return data

    async def origins(self, identity: VisualWorkerIdentity) -> VisualWorkerOriginObservations:
        data, _ = await self._request(
            "GET", f"/visual-explorations/{identity.session_id}/origins", identity,
        )
        result = VisualWorkerOriginObservations.model_validate_json(data)
        if any(getattr(result, key) != value for key, value in identity.model_dump().items()):
            raise VisualWorkerUnavailable("worker origin observations scope mismatch")
        return result

    async def _result(self, method, path, identity, payload=None):
        data, _ = await self._request(method, path, identity, payload)
        result = VisualWorkerOperationResult.model_validate_json(data)
        op = result.operation
        if (op.tenant_id, op.project_id, op.session_id) != (
            identity.tenant_id,
            identity.project_id,
            identity.session_id,
        ):
            raise VisualWorkerUnavailable("worker result scope mismatch")
        expected_id = getattr(payload, "operation_id", None)
        if expected_id is None and method == "GET":
            expected_id = UUID(path.rsplit("/", 1)[-1])
        if expected_id is not None and op.id != expected_id:
            raise VisualWorkerUnavailable("worker result operation mismatch")
        return result

    async def prepare(self, request: VisualWorkerPrepare) -> VisualWorkerOperationResult:
        return await self._result(
            "POST",
            f"/visual-explorations/{request.session_id}/operations/prepare",
            request,
            request,
        )

    async def execute(self, request: VisualWorkerExecute) -> VisualWorkerOperationResult:
        return await self._result(
            "POST",
            f"/visual-explorations/{request.session_id}/operations/{request.operation_id}/execute",
            request,
            request,
        )

    async def read(self, identity: VisualWorkerIdentity, operation_id: UUID):
        return await self._result(
            "GET",
            f"/visual-explorations/{identity.session_id}/operations/{operation_id}",
            identity,
        )

    async def frame(self, identity: VisualWorkerIdentity, frame: VisualOperationFrame) -> bytes:
        if (frame.tenant_id, frame.project_id, frame.session_id) != (
            identity.tenant_id,
            identity.project_id,
            identity.session_id,
        ):
            raise VisualWorkerUnavailable("worker frame scope mismatch")
        data, content_type = await self._request(
            "GET",
            f"/visual-explorations/{identity.session_id}/operations/"
            f"{frame.operation_id}/frames/{frame.id}",
            identity,
            cap=frame.byte_count,
        )
        signature = b"\x89PNG\r\n\x1a\n" if frame.content_type == "image/png" else b"\xff\xd8\xff"
        if (
            content_type != frame.content_type
            or not data.startswith(signature)
            or len(data) != frame.byte_count
            or sha256(data).hexdigest() != frame.checksum
        ):
            raise VisualWorkerUnavailable("worker frame verification failed")
        return data

    async def acknowledge(self, request: VisualWorkerAck):
        return await self._result(
            "POST",
            f"/visual-explorations/{request.session_id}/operations/{request.operation_id}/ack",
            request,
            request,
        )

    async def checkpoint(self, identity: VisualWorkerIdentity, checkpoint_id: UUID):
        import json

        data, _ = await self._request(
            "GET",
            f"/visual-explorations/{identity.session_id}/checkpoints/{checkpoint_id}",
            identity,
        )
        value = json.loads(data)
        checkpoint = VisualCheckpoint.model_validate(value["checkpoint"])
        if checkpoint.id != checkpoint_id or type(value.get("matches_current")) is not bool:
            raise VisualWorkerUnavailable("worker checkpoint response invalid")
        return checkpoint, value["matches_current"]

    async def close(self, identity: VisualWorkerIdentity):
        await self._request("DELETE", f"/visual-explorations/{identity.session_id}", identity)
