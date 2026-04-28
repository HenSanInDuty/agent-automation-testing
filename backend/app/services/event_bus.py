"""
services/event_bus.py – Fire-and-forget Kafka event producer.

All ``emit*`` calls are silently swallowed when Kafka is unavailable, so the
pipeline continues regardless of observability infrastructure state.

Topics (prefix configured via ``KAFKA_TOPIC_PREFIX``, default ``"auto_at"``):
    auto_at.pipeline_events  – run-level lifecycle (run.started / completed / …)
    auto_at.node_events      – per-node progress   (node.started / completed / …)
    auto_at.llm_calls        – every CrewAI / LLM invocation
    auto_at.api_requests     – HTTP request telemetry

Usage::

    from app.services.event_bus import event_bus

    # In async context:
    await event_bus.emit("pipeline_events", {...})

    # From sync context (e.g. inside _emit() callback):
    event_bus.emit_sync("node_events", {...})

    # Typed helpers (recommended):
    event_bus.emit_pipeline_event("run.started", run_id, template_id=...)
    event_bus.emit_node_event("node.completed", run_id, node_id=...)
    event_bus.emit_llm_call(run_id, node_id=..., model=..., latency_ms=...)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from datetime import datetime, timezone
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# ── Common debug fields injected into every message ──────────────────────────
_HOSTNAME: str = socket.gethostname()
_PID: int = os.getpid()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _base_fields() -> dict:  # type: ignore[type-arg]
    """Return the common debug/meta fields added to every Kafka message."""
    return {
        "timestamp": _now_iso(),
        "app_version": settings.APP_VERSION,
        "env": settings.APP_ENV,
        "hostname": _HOSTNAME,
        "pid": _PID,
    }


# ─────────────────────────────────────────────────────────────────────────────
# EventBus
# ─────────────────────────────────────────────────────────────────────────────


class EventBus:
    """
    Async Kafka producer with graceful degradation.

    When ``KAFKA_ENABLED=false`` or the broker is unreachable, every
    ``emit*`` method becomes a no-op — the pipeline continues unaffected.

    Lifecycle::

        await event_bus.startup()   # called from app lifespan
        ...
        await event_bus.shutdown()  # called from app lifespan
    """

    def __init__(self) -> None:
        self._producer: Optional[Any] = None
        self._available: bool = False

    # ─────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────

    async def startup(self) -> None:
        """Start the aiokafka producer. Called from the FastAPI lifespan."""
        if not settings.KAFKA_ENABLED:
            logger.info("[EventBus] Kafka disabled (KAFKA_ENABLED=false).")
            return

        try:
            from aiokafka import AIOKafkaProducer  # type: ignore[import-untyped]

            self._producer = AIOKafkaProducer(
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                linger_ms=settings.KAFKA_PRODUCER_LINGER_MS,
                max_batch_size=settings.KAFKA_PRODUCER_MAX_BATCH_SIZE,
                request_timeout_ms=5_000,
                enable_idempotence=False,
            )
            await self._producer.start()
            self._available = True
            logger.info(
                "[EventBus] Kafka producer started → %s",
                settings.KAFKA_BOOTSTRAP_SERVERS,
            )
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            self._available = False
            logger.warning(
                "[EventBus] Kafka unavailable – observability events disabled: %s", exc
            )

    async def shutdown(self) -> None:
        """Flush and close the producer. Called from the FastAPI lifespan."""
        if self._producer is not None:
            try:
                await self._producer.stop()
                logger.info("[EventBus] Kafka producer stopped.")
            except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
                logger.warning("[EventBus] Error stopping Kafka producer: %s", exc)
            finally:
                self._available = False

    # ─────────────────────────────────────────────────────────────────────
    # Core emit
    # ─────────────────────────────────────────────────────────────────────

    async def emit(self, topic_suffix: str, payload: dict) -> None:  # type: ignore[type-arg]
        """
        Publish *payload* to ``<KAFKA_TOPIC_PREFIX>.<topic_suffix>``.

        Always merges ``_base_fields()`` first (timestamp, app_version, env,
        hostname, pid). Caller fields take precedence on key collision.
        Never raises — all errors are logged at DEBUG level.
        """
        if not self._available or self._producer is None:
            return

        full_topic = f"{settings.KAFKA_TOPIC_PREFIX}.{topic_suffix}"
        # base_fields first so caller values override them
        message = {**_base_fields(), **payload}

        try:
            await self._producer.send(full_topic, value=message)
        except Exception as exc:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            logger.debug(
                "[EventBus] Failed to emit topic=%s: %s", full_topic, exc
            )

    def emit_sync(self, topic_suffix: str, payload: dict) -> None:  # type: ignore[type-arg]
        """
        Schedule an async ``emit()`` from synchronous context.

        Uses ``asyncio.ensure_future`` — safe to call from within the running
        event loop thread (e.g. ``_emit()`` in DAGPipelineRunner).
        """
        if not self._available:
            return
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                _task = asyncio.ensure_future(self.emit(topic_suffix, payload))
                # Keep a reference so the task isn't GC'd before it completes
                _task.add_done_callback(lambda _: None)
        except Exception:  # noqa: BLE001  # pylint: disable=broad-exception-caught
            pass

    # ─────────────────────────────────────────────────────────────────────
    # Typed helper — pipeline_events
    # ─────────────────────────────────────────────────────────────────────

    def emit_pipeline_event(
        self,
        event_type: str,
        run_id: str,
        *,
        template_id: str = "",
        document_name: str = "",
        total_nodes: int = 0,
        total_layers: int = 0,
        duration_seconds: float = 0.0,
        error: str = "",
        failed_node: str = "",
        extra: Optional[dict] = None,  # type: ignore[type-arg]
    ) -> None:
        """
        Emit a run-level lifecycle event to the ``pipeline_events`` topic.

        Debug fields included:
            event_type, run_id, template_id, document_name, total_nodes,
            total_layers, duration_seconds, error, failed_node, data (JSON
            dump of remaining *extra* fields), plus common base fields.
        """
        payload: dict = {  # type: ignore[type-arg]
            "event_type": event_type,
            "run_id": run_id,
            "template_id": template_id,
            "document_name": document_name,
            "total_nodes": total_nodes,
            "total_layers": total_layers,
            "duration_seconds": round(duration_seconds, 3),
            "error": error,
            "failed_node": failed_node,
            "data": json.dumps(extra or {}, default=str),
        }
        self.emit_sync("pipeline_events", payload)

    # ─────────────────────────────────────────────────────────────────────
    # Typed helper — node_events
    # ─────────────────────────────────────────────────────────────────────

    def emit_node_event(
        self,
        event_type: str,
        run_id: str,
        *,
        node_id: str = "",
        node_type: str = "",
        agent_id: str = "",
        label: str = "",
        status: str = "",
        duration_ms: int = 0,
        retry_attempt: int = 0,
        will_retry: bool = False,
        error_detail: str = "",
        output_preview: str = "",
        parent_node_ids: Optional[list] = None,  # type: ignore[type-arg]
    ) -> None:
        """
        Emit a node-level event to the ``node_events`` topic.

        Debug fields included:
            event_type, run_id, node_id, node_type, agent_id, label,
            status, duration_ms, retry_attempt, will_retry, error_detail,
            output_preview (capped at 300 chars), parent_node_ids (JSON),
            plus common base fields.
        """
        payload: dict = {  # type: ignore[type-arg]
            "event_type": event_type,
            "run_id": run_id,
            "node_id": node_id,
            "node_type": node_type,
            "agent_id": agent_id,
            "label": label,
            "status": status,
            "duration_ms": duration_ms,
            "retry_attempt": retry_attempt,
            "will_retry": int(will_retry),  # JSONEachRow needs int for UInt8
            "error_detail": error_detail,
            "output_preview": output_preview[:300] if output_preview else "",
            "parent_node_ids": json.dumps(parent_node_ids or []),
        }
        self.emit_sync("node_events", payload)

    # ─────────────────────────────────────────────────────────────────────
    # Typed helper — llm_calls
    # ─────────────────────────────────────────────────────────────────────

    def emit_llm_call(
        self,
        run_id: str,
        *,
        node_id: str = "",
        agent_id: str = "",
        model: str = "",
        latency_ms: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
        success: bool = True,
        error_type: str = "",
        error_message: str = "",
        task_description_len: int = 0,
        task_description_preview: str = "",
    ) -> None:
        """
        Emit one LLM call record to the ``llm_calls`` topic.

        Debug fields included:
            run_id, node_id, agent_id, model (e.g. "openai/gpt-4o"),
            provider (derived from model prefix), latency_ms, prompt_tokens,
            completion_tokens, total_tokens, success, error_type, error_message,
            task_description_len, task_description_preview (first 200 chars),
            plus common base fields.

        Token counts are 0 when the LLM provider doesn't expose usage.
        """
        provider = model.split("/")[0] if "/" in model else ""
        payload: dict = {  # type: ignore[type-arg]
            "run_id": run_id,
            "node_id": node_id,
            "agent_id": agent_id,
            "model": model,
            "provider": provider,
            "latency_ms": latency_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "success": int(success),
            "error_type": error_type,
            "error_message": error_message,
            "task_description_len": task_description_len,
            "task_description_preview": task_description_preview[:200],
        }
        self.emit_sync("llm_calls", payload)


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

event_bus = EventBus()
