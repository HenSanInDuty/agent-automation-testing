"""Persist bounded, origin-only observations without gating browser execution."""

import asyncio
from hashlib import sha256


class RecordVisualOrigins:
    def __init__(self, operations):
        self.operations = operations
        self.seen = set()

    async def capture(self):
        operations = self.operations
        try:
            async with asyncio.timeout(2):
                observed = await operations.worker.origins(operations.identity)
        except Exception:
            self._event("origin.observation_unavailable", "origin.observation_unavailable")
            return
        for item in observed.items:
            key = sha256(f"{item.request_kind}:{item.origin}".encode()).hexdigest()
            self._event("origin.observed", f"origin:{key}", {
                "origin": item.origin, "request_kind": item.request_kind,
            })
        if observed.truncated:
            self._event("origin.observations_limited", "origin.observations_limited")

    def _event(self, stage, key, metadata=None):
        if key in self.seen:
            return
        self.operations.uow.progress(self.operations.lease, stage, key, metadata)
        self.seen.add(key)
