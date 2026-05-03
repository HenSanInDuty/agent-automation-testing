"""
tools/registry.py – Centralised CrewAI tool registry.

All agent tools are registered here.  ``AgentFactory`` calls
``ToolRegistry.resolve(tool_names)`` to get the list of ``BaseTool``
instances to attach to an agent.

Adding a new tool
─────────────────
1. Implement it in a module under ``app/tools/`` (subclass
   ``crewai.tools.BaseTool`` or a plain-Python function wrapped with
   ``@tool``).
2. Register a factory function (or constant instance) in ``_REGISTRY``
   below using a unique lowercase slug as key.

Built-in tool slugs
────────────────────
    api_runner        – HTTP API execution (httpx-based)
    config_loader     – Environment config loader
    document_parser   – Multi-format document text extractor
    text_chunker      – Long-text chunking helper

Usage::

    from app.tools.registry import ToolRegistry

    tools = ToolRegistry.resolve(["api_runner", "document_parser"])
    agent = Agent(..., tools=tools)
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Type aliases
# ─────────────────────────────────────────────────────────────────────────────

# Each entry is either a pre-built tool instance or a zero-arg factory that
# returns one.  Using factories avoids importing crewai at module-import time
# (it's optional / slow) and lets each agent get its own isolated instance.
_ToolEntry = Any  # BaseTool instance or Callable[[], BaseTool]


# ─────────────────────────────────────────────────────────────────────────────
# Registry entries — lazy factories
# ─────────────────────────────────────────────────────────────────────────────

def _make_api_runner() -> Any:
    from app.tools.api_runner import APIRunnerTool  # noqa: PLC0415
    return APIRunnerTool()


def _make_config_loader() -> Any:
    from app.tools.config_loader import ConfigLoaderTool  # noqa: PLC0415
    return ConfigLoaderTool()


def _make_document_parser() -> Any:
    from app.tools.document_parser_tool import DocumentParserTool  # noqa: PLC0415
    return DocumentParserTool()


def _make_text_chunker() -> Any:
    from app.tools.text_chunker_tool import TextChunkerTool  # noqa: PLC0415
    return TextChunkerTool()


# slug → zero-arg factory function
_REGISTRY: dict[str, Callable[[], Any]] = {
    "api_runner": _make_api_runner,
    "config_loader": _make_config_loader,
    "document_parser": _make_document_parser,
    "text_chunker": _make_text_chunker,
}


# ─────────────────────────────────────────────────────────────────────────────
# ToolRegistry
# ─────────────────────────────────────────────────────────────────────────────

class ToolRegistry:
    """Static helper for resolving tool slugs → BaseTool instances."""

    @staticmethod
    def available() -> list[str]:
        """Return sorted list of all registered tool slugs."""
        return sorted(_REGISTRY.keys())

    @staticmethod
    def resolve(tool_names: list[str]) -> list[Any]:
        """Build and return a list of tool instances for the given slugs.

        Unknown slugs are logged and skipped — they never raise so a bad
        admin config cannot break an entire pipeline run.

        Args:
            tool_names: List of registered tool slugs.

        Returns:
            List of ``BaseTool`` instances in the same order as *tool_names*,
            with unknown / failed slugs omitted.
        """
        tools: list[Any] = []
        for name in tool_names:
            factory = _REGISTRY.get(name)
            if factory is None:
                logger.warning("[ToolRegistry] Unknown tool slug %r — skipping", name)
                continue
            try:
                tool = factory()
                tools.append(tool)
                logger.debug("[ToolRegistry] Resolved tool %r → %s", name, type(tool).__name__)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ToolRegistry] Failed to build tool %r: %s — skipping", name, exc
                )
        return tools

    @staticmethod
    def register(slug: str, factory: Callable[[], Any]) -> None:
        """Register a custom tool factory at runtime.

        Allows plugins / third-party code to add tools without editing
        this file.

        Args:
            slug:    Unique lowercase identifier for the tool.
            factory: Zero-argument callable that returns a ``BaseTool``
                     instance.  Called once per agent build.
        """
        if slug in _REGISTRY:
            logger.warning(
                "[ToolRegistry] Overwriting existing tool slug %r", slug
            )
        _REGISTRY[slug] = factory
        logger.info("[ToolRegistry] Registered tool %r", slug)

    @staticmethod
    def describe() -> list[dict[str, str]]:
        """Return a list of ``{"slug": ..., "class": ...}`` dicts for the API.

        The ``class`` key is populated by a dry-run factory call — if the
        factory fails (e.g. crewai not installed) ``"unavailable"`` is used.
        """
        result: list[dict[str, str]] = []
        for slug, factory in sorted(_REGISTRY.items()):
            try:
                tool = factory()
                class_name = type(tool).__name__
                description = getattr(tool, "description", "") or ""
            except Exception:  # noqa: BLE001
                class_name = "unavailable"
                description = ""
            result.append({
                "slug": slug,
                "class": class_name,
                "description": description,
            })
        return result
