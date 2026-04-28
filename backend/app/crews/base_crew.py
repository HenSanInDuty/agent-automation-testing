"""
crews/base_crew.py
──────────────────
Abstract base class for all pipeline crews.

Provides:
  - Uniform constructor signature (run_id, run_profile_id, progress_callback,
    mock_mode) — the legacy ``db`` parameter has been removed in V2 since all
    DB access now goes through async Beanie/Motor rather than SQLAlchemy.
  - Progress-event emission helpers (_emit, _emit_agent_started, …)
  - JSON output parsing with graceful fallback (_parse_json_output)
  - Mock-mode detection (_is_mock_mode)
  - Async DB helper (_load_agents_from_db) for fetching agent configs

Every concrete crew (IngestionCrew, TestcaseCrew, ExecutionCrew, ReportingCrew)
inherits from BaseCrew and implements the single abstract method ``run()``.

Usage::

    from app.crews.base_crew import BaseCrew, ProgressCallback

    class MyCrew(BaseCrew):
        stage = "my_stage"
        agent_ids = ["agent_a", "agent_b"]

        def run(self, input_data):
            self._emit_stage_started(agent_count=2)
            # ... do work ...
            self._emit_stage_completed()
            return {"result": "..."}
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from app.config import settings

logger = logging.getLogger(__name__)

# Type alias for the progress callback:
#   callback(event_type: str, data: dict) -> None
ProgressCallback = Callable[[str, dict[str, Any]], None]


class BaseCrew(ABC):
    """
    Abstract base class for all Auto-AT pipeline crews.

    Subclasses must set two class-level attributes:
        stage      – pipeline stage name (e.g. "testcase", "execution")
        agent_ids  – list of agent_id strings managed by this crew

    And must implement:
        run(input_data) -> dict

    V2 Changes
    ----------
    * The ``db`` (SQLAlchemy session) parameter has been removed. All database
      access now goes through async Beanie CRUD helpers. Subclasses should use
      ``await self._load_agents_from_db()`` or import ``app.db.crud`` directly.
    * ``run_profile_id`` type changed from ``int`` to ``str`` (MongoDB ObjectId
      string representation).
    """

    # ── Override in subclasses ────────────────────────────────────────────────
    stage: str = "unknown"
    agent_ids: list[str] = []

    # ─────────────────────────────────────────────────────────────────────────
    # Constructor
    # ─────────────────────────────────────────────────────────────────────────

    def __init__(
        self,
        run_id: str,
        run_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        **_kwargs: Any,  # absorb legacy keyword args (e.g. db=) from V1 subclasses
    ) -> None:
        """
        Initialise the crew.

        Args:
            run_id:            UUID of the current pipeline run (used in events).
            run_profile_id:    Optional MongoDB ObjectId string of the run-level
                               LLM profile override.
            progress_callback: Optional callable that receives (event_type, data)
                               for real-time progress streaming.  When None, events
                               are only logged at DEBUG level.
            mock_mode:         When True, the crew produces deterministic mock output
                               without calling any LLM.  When None, falls back to
                               the MOCK_CREWS environment variable / settings flag.
            **_kwargs:         Silently absorbs unknown keyword arguments for
                               backward compatibility with V1 subclasses that
                               pass ``db=<session>``.
        """
        self._run_id = run_id
        self._run_profile_id = run_profile_id
        self._progress_callback = progress_callback

        # Resolve mock_mode: explicit arg > settings > False
        if mock_mode is None:
            self._mock_mode: bool = bool(getattr(settings, "MOCK_CREWS", False))
        else:
            self._mock_mode = mock_mode

        # Event loop reference — set by the pipeline runner before spawning
        # asyncio.to_thread so that _run_async_from_thread can use it.
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

    # ─────────────────────────────────────────────────────────────────────────
    # Abstract interface
    # ─────────────────────────────────────────────────────────────────────────

    @abstractmethod
    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute this crew and return structured output.

        Args:
            input_data: Stage-specific input dict.  See each subclass for
                        the required keys.

        Returns:
            Stage-specific output dict that conforms to the relevant
            ``schemas.pipeline_io`` model (e.g. IngestionOutput, TestCaseOutput).
        """
        raise NotImplementedError

    # ─────────────────────────────────────────────────────────────────────────
    # Async DB helpers (V2)
    # ─────────────────────────────────────────────────────────────────────────

    async def _load_agents_from_db(self) -> list:
        """Load enabled agents for this stage from MongoDB.

        Uses the Beanie-backed CRUD layer to query
        :class:`~app.db.models.AgentConfigDocument` objects for the current
        stage.  Only enabled agents are returned.

        Returns:
            List of :class:`~app.db.models.AgentConfigDocument` instances
            whose ``stage`` matches :attr:`stage` and whose ``enabled`` flag
            is ``True``.
        """
        from app.db import crud

        return await crud.get_agent_configs_for_stage(
            stage=self.stage,
            enabled_only=True,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Progress event helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """
        Emit a progress event via the registered callback.

        The ``run_id`` is automatically injected into *data* so callers don't
        need to pass it each time.

        Args:
            event_type: Dot-separated event name (e.g. "agent.started").
            data:       Event payload dict.
        """
        payload = {"run_id": self._run_id, "stage": self.stage, **data}
        logger.debug("[%s] event=%r  data=%r", self._run_id[:8], event_type, payload)

        if self._progress_callback is not None:
            try:
                self._progress_callback(event_type, payload)
            except Exception as exc:  # pragma: no cover  # pylint: disable=broad-exception-caught
                logger.warning(
                    "Progress callback raised an exception (ignored): %s", exc
                )

    def _emit_stage_started(self, agent_count: Optional[int] = None) -> None:
        """Emit a ``stage.started`` event."""
        data: dict[str, Any] = {"stage": self.stage}
        if agent_count is not None:
            data["agent_count"] = agent_count
        else:
            data["agent_count"] = len(self.agent_ids)
        self._emit("stage.started", data)

    def _emit_stage_completed(self) -> None:
        """Emit a ``stage.completed`` event."""
        self._emit("stage.completed", {"stage": self.stage})

    def _emit_agent_started(self, agent_id: str, display_name: str = "") -> None:
        """
        Emit an ``agent.started`` event for a specific agent.

        Args:
            agent_id:     Unique agent slug (e.g. "requirement_analyzer").
            display_name: Human-readable name for the UI.  Falls back to agent_id.
        """
        self._emit(
            "agent.started",
            {
                "agent_id": agent_id,
                "display_name": display_name or agent_id.replace("_", " ").title(),
            },
        )

    def _emit_agent_completed(
        self,
        agent_id: str,
        output_preview: str = "",
    ) -> None:
        """
        Emit an ``agent.completed`` event.

        Args:
            agent_id:       Unique agent slug.
            output_preview: First ≤200 chars of the output (for UI preview).
        """
        self._emit(
            "agent.completed",
            {
                "agent_id": agent_id,
                "output_preview": output_preview[:200],
            },
        )

    def _emit_agent_failed(self, agent_id: str, error: str) -> None:
        """
        Emit an ``agent.failed`` event.

        Args:
            agent_id: Unique agent slug.
            error:    Error message / exception string.
        """
        self._emit(
            "agent.failed",
            {
                "agent_id": agent_id,
                "error": str(error)[:500],
            },
        )

    def _emit_log(self, message: str, level: str = "info") -> None:
        """
        Emit a free-form ``log`` event.

        Args:
            message: Human-readable log message.
            level:   Log level string (info | warning | error).
        """
        self._emit("log", {"message": message, "level": level})

    # ─────────────────────────────────────────────────────────────────────────
    # JSON output parsing
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json_output(raw: Any) -> Any:
        """
        Best-effort JSON parser for CrewAI task outputs.

        CrewAI returns different types depending on version and process type:
          - ``str``        – raw LLM output (may or may not be valid JSON)
          - ``dict``       – already parsed
          - ``list``       – already parsed list
          - ``CrewOutput`` – has a ``.raw`` attribute in newer versions

        Parsing strategy:
          1. If already a dict or list → return as-is.
          2. If it has a ``.raw`` attribute → use that string.
          3. Try ``json.loads(text)`` directly.
          4. Try to extract a JSON object/array from inside markdown code fences.
          5. Try to extract the first ``{…}`` or ``[…]`` block in the text.
          6. Fall back to ``{"raw_output": text}``.

        Args:
            raw: The value returned by ``crew.kickoff()`` or a task callback.

        Returns:
            Parsed Python object (dict, list, or fallback dict).
        """
        # Already parsed
        if isinstance(raw, (dict, list)):
            return raw

        # CrewOutput / objects with .raw attribute (crewai >= 0.80)
        if hasattr(raw, "raw"):
            raw = raw.raw

        # Convert to string
        if not isinstance(raw, str):
            try:
                raw = str(raw)
            except Exception:  # pylint: disable=broad-exception-caught
                return {"raw_output": repr(raw)}

        text = raw.strip()

        if not text:
            return {}

        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Markdown code fence (```json … ``` or ``` … ```)
        fence_match = re.search(
            r"```(?:json)?\s*\n?([\s\S]+?)\n?```",
            text,
            re.IGNORECASE,
        )
        if fence_match:
            try:
                return json.loads(fence_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 3. First top-level JSON object { … } or array [ … ]
        for start_char, end_char in [("{", "}"), ("[", "]")]:
            start = text.find(start_char)
            if start == -1:
                continue
            # Walk backwards from the end to find the matching closing bracket
            end = text.rfind(end_char)
            if end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass

        # 4. Fallback: wrap raw text so downstream code can still handle it
        logger.warning(
            "Could not parse JSON from crew output (len=%d). "
            "Returning raw_output fallback.",
            len(text),
        )
        return {"raw_output": text}

    # ─────────────────────────────────────────────────────────────────────────
    # Mock-mode helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _is_mock_mode(self) -> bool:
        """Return True when mock mode is active for this crew."""
        return self._mock_mode

    def _run_async_from_thread(self, coro: Any, timeout: float = 60.0) -> Any:
        """Run an async coroutine from within a synchronous thread context.

        Uses the event loop stored in ``self._event_loop`` (injected by the
        pipeline runner before the thread is spawned) so the coroutine runs on
        the **same** event loop that owns the ``AsyncMongoClient`` instance.

        This avoids the "Cannot use AsyncMongoClient in different event loop"
        error that occurs when ``asyncio.run()`` creates a brand-new event loop
        while the MongoDB client is bound to the original FastAPI event loop.

        Args:
            coro:    Awaitable / coroutine to execute.
            timeout: Maximum seconds to wait for the result (default 60 s).

        Returns:
            Whatever the coroutine returns.

        Raises:
            concurrent.futures.TimeoutError: If *timeout* elapses.
            Any exception raised by the coroutine itself.
        """
        loop = self._event_loop
        if loop is not None and loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(coro, loop)
            return fut.result(timeout=timeout)
        # Fallback – used in unit tests / sync contexts where no loop is stored.
        return asyncio.run(coro)

    # ─────────────────────────────────────────────────────────────────────────
    # Repr
    # ─────────────────────────────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"stage={self.stage!r} "
            f"run_id={self._run_id[:8]!r} "
            f"mock={self._mock_mode}>"
        )
