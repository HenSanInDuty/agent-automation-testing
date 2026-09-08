"""Bounded private v4 transport. No worker path or diagnostic crosses this boundary."""

from hashlib import sha256
from uuid import UUID

import httpx
from auto_at.contracts.vision import VisualCheckpoint, VisualOperationFrame
from auto_at.contracts.vision_worker import (
    VisualWorkerAck,
    VisualWorkerExecute,
    VisualWorkerIdentity,
    VisualWorkerOpen,
    VisualWorkerOperationResult,
    VisualWorkerPrepare,
)


class VisualWorkerUnavailable(RuntimeError):
    pass


class HttpVisualWorker:
    def __init__(self, client: httpx.AsyncClient, base_url: str, secret: str) -> None:
        self._client, self._base, self._secret = client, base_url.rstrip("/"), secret

    def _headers(self, identity: VisualWorkerIdentity) -> dict[str, str]:
        return {
            "X-Auto-At-Vision-Worker-Secret": self._secret,
            "X-Auto-At-Vision-Tenant-Id": identity.tenant_id,
            "X-Auto-At-Vision-Project-Id": str(identity.project_id),
            "X-Auto-At-Vision-Fencing-Token": str(identity.fencing_token),
        }

    async def _request(self, method, path, identity, payload=None, *, cap=128_000):
        try:
            async with self._client.stream(
                method,
                self._base + path,
                headers=self._headers(identity),
                json=payload.model_dump(mode="json") if payload is not None else None,
            ) as response:
                response.raise_for_status()
                data = bytearray()
                async for chunk in response.aiter_bytes(chunk_size=64_000):
                    if len(data) + len(chunk) > cap:
                        raise VisualWorkerUnavailable("worker response exceeds cap")
                    data.extend(chunk)
                return bytes(data), response.headers.get("content-type", "").split(";")[0]
        except httpx.HTTPError:
            raise VisualWorkerUnavailable("visual worker transport unavailable") from None

    async def open(self, request: VisualWorkerOpen) -> str:
        import json

        data, _ = await self._request("POST", "/visual-explorations", request, request)
        value = json.loads(data)
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
