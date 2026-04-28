from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# Connection Manager
# ─────────────────────────────────────────────────────────────────────────────


class ConnectionManager:
    """
    Manages active WebSocket connections, grouped by run_id.

    Thread-safety note:
        All mutations happen inside the asyncio event loop (FastAPI/Starlette
        runs on a single-threaded event loop), so a plain dict is sufficient.
        The pipeline runner executes in a thread-pool executor; use
        ``broadcast_from_thread`` (which schedules a coroutine on the loop)
        from that context.
    """

    def __init__(self) -> None:
        # run_id → set of active WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        # Reference to the running event loop.
        # Set eagerly via set_loop() at app startup AND lazily in connect().
        self._loop: asyncio.AbstractEventLoop | None = None

    # ── Connection lifecycle ──────────────────────────────────────────────────

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """
        Eagerly store the event loop reference.

        Call this once at application startup (e.g. inside the lifespan
        context) so that ``broadcast_from_thread`` works even before the
        first WebSocket client connects.
        """
        self._loop = loop
        logger.debug("[WS] Event loop registered on ConnectionManager")

    async def connect(self, websocket: WebSocket, run_id: str) -> None:
        """Accept a new WebSocket connection and register it for *run_id*."""
        await websocket.accept()
        self._connections[run_id].add(websocket)
        # Keep the loop reference up-to-date (also covers the eager set_loop path)
        self._loop = asyncio.get_running_loop()
        logger.info(
            "[WS] Client connected  run_id=%r  total_for_run=%d",
            run_id,
            len(self._connections[run_id]),
        )

    def disconnect(self, websocket: WebSocket, run_id: str) -> None:
        """Remove a WebSocket connection from the registry."""
        self._connections[run_id].discard(websocket)
        if not self._connections[run_id]:
            del self._connections[run_id]
        logger.info(
            "[WS] Client disconnected  run_id=%r  remaining=%d",
            run_id,
            len(self._connections.get(run_id, set())),
        )

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    async def broadcast(self, run_id: str, message: str) -> None:
        """
        Send *message* (JSON string) to every connected client for *run_id*.
        Dead connections are silently removed.
        """
        targets = list(self._connections.get(run_id, set()))
        if not targets:
            logger.debug(
                "[WS] broadcast: no clients for run_id=%r — message dropped", run_id
            )
            return

        dead: set[WebSocket] = set()
        sent = 0
        for ws in targets:
            try:
                await ws.send_text(message)
                sent += 1
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.debug("[WS] send_text failed for run_id=%r: %s", run_id, exc)
                dead.add(ws)

        logger.debug(
            "[WS] broadcast run_id=%r  sent=%d  dead=%d", run_id, sent, len(dead)
        )

        for ws in dead:
            self._connections[run_id].discard(ws)
            logger.debug("[WS] Removed dead connection for run_id=%r", run_id)

    async def broadcast_json(self, run_id: str, payload: dict[str, Any]) -> None:
        """Convenience wrapper – serialises *payload* to JSON then broadcasts."""
        import json

        message = json.dumps(payload, default=str)
        await self.broadcast(run_id, message)

    def broadcast_from_thread(self, run_id: str, message: str) -> None:
        """
        Thread-safe broadcast: schedules :meth:`broadcast` on the event loop.

        Call this from synchronous code running inside a thread-pool executor
        (e.g. the PipelineRunner background task).
        """
        loop = self._loop
        if loop is None:
            logger.warning(
                "[WS] broadcast_from_thread: _loop is None — event dropped for run_id=%r. "
                "WebSocket manager was not initialised with an event loop before the pipeline started. "
                "Call manager.set_loop() at app startup to fix this.",
                run_id,
            )
            return
        if not loop.is_running():
            logger.warning(
                "[WS] broadcast_from_thread: event loop is NOT running — event dropped for run_id=%r.",
                run_id,
            )
            return

        clients = len(self._connections.get(run_id, set()))
        logger.debug(
            "[WS] broadcast_from_thread run_id=%r clients=%d msg_len=%d",
            run_id,
            clients,
            len(message),
        )

        future = asyncio.run_coroutine_threadsafe(self.broadcast(run_id, message), loop)

        def _on_done(fut: "asyncio.Future[None]") -> None:
            exc = fut.exception()
            if exc is not None:
                logger.warning(
                    "[WS] broadcast coroutine raised an exception for run_id=%r: %s",
                    run_id,
                    exc,
                    exc_info=exc,
                )

        future.add_done_callback(_on_done)

    # ── Introspection ─────────────────────────────────────────────────────────

    def active_run_ids(self) -> list[str]:
        """Return the list of run_ids that currently have at least one client."""
        return list(self._connections.keys())

    def connection_count(self, run_id: str) -> int:
        """Return the number of active connections for *run_id*."""
        return len(self._connections.get(run_id, set()))


# ── Global singleton ──────────────────────────────────────────────────────────
#
# Imported by pipeline.py to attach the broadcaster to background runs.
# Imported by main.py for nothing (the router is enough).

manager = ConnectionManager()


# ─────────────────────────────────────────────────────────────────────────────
# WebSocket endpoint
# ─────────────────────────────────────────────────────────────────────────────


@router.websocket("/ws/pipeline/{run_id}")
async def pipeline_ws(websocket: WebSocket, run_id: str) -> None:
    """
    Stream real-time pipeline progress events to the frontend.

    **Protocol**
    1. Client connects: ``WS /ws/pipeline/{run_id}``
    2. Server immediately sends a ``{"event": "connected", "run_id": "..."}``
       greeting so the client knows the handshake succeeded.
    3. As the pipeline runs, the server broadcasts JSON event objects
       matching the ``WSEvent`` schema (see ``schemas/pipeline.py``).
    4. The client may send a ``{"action": "ping"}`` frame at any time;
       the server replies with ``{"event": "pong"}``.
    5. When the pipeline completes (``run.completed`` or ``run.failed``)
       the server does **not** force-close the connection — the client
       should disconnect after receiving a terminal event.

    **Event shape** (see ``WSEventType`` enum for all possible values)::

        {
          "event":     "agent.started",
          "run_id":    "abc-123",
          "timestamp": "2025-01-01T10:00:01Z",
          "data": { ... }
        }
    """
    await manager.connect(websocket, run_id)

    # Send a greeting so the client knows the handshake completed
    import json
    from datetime import datetime, timezone

    greeting = json.dumps(
        {
            "event": "connected",
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"message": f"Subscribed to pipeline run {run_id}"},
        }
    )
    await websocket.send_text(greeting)

    try:
        # Keep the connection alive; handle client messages (e.g. ping)
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send a server-side keepalive ping to prevent proxy timeouts
                try:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "ping",
                                "run_id": run_id,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": {},
                            }
                        )
                    )
                except Exception:  # pylint: disable=broad-exception-caught
                    break
                continue

            # Handle client messages
            try:
                msg = json.loads(raw)
                if msg.get("action") == "ping":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "event": "pong",
                                "run_id": run_id,
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": {},
                            }
                        )
                    )
            except (json.JSONDecodeError, AttributeError):
                pass  # ignore malformed messages

    except WebSocketDisconnect:
        logger.info("[WS] WebSocketDisconnect for run_id=%r", run_id)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        logger.warning("[WS] Unexpected error for run_id=%r: %s", run_id, exc)
    finally:
        manager.disconnect(websocket, run_id)
