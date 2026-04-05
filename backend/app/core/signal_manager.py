from __future__ import annotations

"""
core/signal_manager.py – In-memory signal store for pipeline pause/resume/cancel.

The pipeline runner checks signals between stages. Signals are set via API endpoints.
Thread-safe via asyncio.Lock.
"""
import asyncio
import logging
from enum import Enum
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class PipelineSignal(str, Enum):
    NONE = "none"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"


class SignalManager:
    """
    In-memory signal store for pipeline runs.

    Signals are set from API handlers and read by the pipeline runner
    between stages. The asyncio.Lock ensures thread safety when signals
    are set from different coroutines.
    """

    def __init__(self) -> None:
        self._signals: dict[str, PipelineSignal] = {}
        self._resume_events: dict[str, asyncio.Event] = {}
        self._lock = asyncio.Lock()

    async def set_signal(self, run_id: str, signal: PipelineSignal) -> None:
        """Set a signal for a pipeline run."""
        async with self._lock:
            self._signals[run_id] = signal
            logger.info("[SignalManager] run_id=%r signal=%s", run_id[:8], signal)
            # If RESUME, unblock any waiting coroutine
            if signal == PipelineSignal.RESUME:
                event = self._resume_events.get(run_id)
                if event:
                    event.set()

    async def get_signal(self, run_id: str) -> PipelineSignal:
        """Get the current signal for a run."""
        async with self._lock:
            return self._signals.get(run_id, PipelineSignal.NONE)

    async def clear_signal(self, run_id: str) -> None:
        """Clear the signal and resume event for a run (cleanup after terminal state)."""
        async with self._lock:
            self._signals.pop(run_id, None)
            self._resume_events.pop(run_id, None)

    async def wait_for_resume(
        self, run_id: str, timeout: Optional[float] = None
    ) -> PipelineSignal:
        """
        Block until RESUME or CANCEL signal is received.
        Returns the signal that unblocked the wait.
        Auto-cancels if timeout is exceeded (uses PAUSE_TIMEOUT_SECONDS config).
        """
        if timeout is None:
            timeout = float(settings.PAUSE_TIMEOUT_SECONDS)

        event = asyncio.Event()
        async with self._lock:
            self._resume_events[run_id] = event
            # If a RESUME signal was already set before we started waiting
            current = self._signals.get(run_id, PipelineSignal.NONE)
            if current == PipelineSignal.RESUME:
                event.set()
            elif current == PipelineSignal.CANCEL:
                return PipelineSignal.CANCEL

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "[SignalManager] Pause timeout for run_id=%r after %.0fs — auto-cancelling",
                run_id[:8],
                timeout,
            )
            return PipelineSignal.CANCEL

        async with self._lock:
            return self._signals.get(run_id, PipelineSignal.RESUME)

    async def pop_signal(self, run_id: str) -> PipelineSignal:
        """Atomically read and remove the signal for a run."""
        async with self._lock:
            return self._signals.pop(run_id, PipelineSignal.NONE)

    async def check_cancel(self, run_id: str) -> bool:
        """Return True if a CANCEL signal is currently pending."""
        async with self._lock:
            return (
                self._signals.get(run_id, PipelineSignal.NONE) == PipelineSignal.CANCEL
            )

    async def check_pause(self, run_id: str) -> bool:
        """Return True if a PAUSE signal is currently pending."""
        async with self._lock:
            return (
                self._signals.get(run_id, PipelineSignal.NONE) == PipelineSignal.PAUSE
            )

    def pending_count(self) -> int:
        """Return the number of run IDs with a pending signal."""
        return len(self._signals)


# Module-level singleton
signal_manager = SignalManager()
