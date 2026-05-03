"""
tools/text_chunker_tool.py – CrewAI BaseTool wrapper for text_chunker.

Wraps ``chunk_text`` so agents can split large documents into manageable
chunks before processing them with an LLM.

Usage::

    from app.tools.text_chunker_tool import TextChunkerTool

    tool = TextChunkerTool()
    agent = Agent(..., tools=[tool])
"""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

try:
    from crewai.tools import BaseTool  # type: ignore[import-untyped]
    from pydantic import BaseModel, Field

    _CREWAI_AVAILABLE = True
except ImportError:
    BaseTool = object  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Input schema
# ─────────────────────────────────────────────────────────────────────────────

if _CREWAI_AVAILABLE:
    class _TextChunkerInput(BaseModel):
        text: str = Field(description="The text to split into chunks.")
        chunk_size: int = Field(
            default=2000,
            ge=100,
            le=10000,
            description="Target chunk size in characters (default 2000).",
        )
        overlap: int = Field(
            default=200,
            ge=0,
            description="Overlap between consecutive chunks in characters (default 200).",
        )

else:
    _TextChunkerInput = None  # type: ignore[assignment,misc]


# ─────────────────────────────────────────────────────────────────────────────
# Tool
# ─────────────────────────────────────────────────────────────────────────────

if _CREWAI_AVAILABLE:
    class TextChunkerTool(BaseTool):  # type: ignore[misc]
        """CrewAI tool that splits long text into overlapping chunks.

        Returns a JSON array of chunk strings.
        """

        name: str = "text_chunker"
        description: str = (
            "Split a long piece of text into overlapping chunks suitable for LLM processing. "
            "Returns a JSON array of text strings. "
            "Use this before passing large documents to an LLM."
        )
        args_schema: type = _TextChunkerInput

        def _run(  # type: ignore[override]
            self,
            text: str,
            chunk_size: int = 2000,
            overlap: int = 200,
        ) -> str:
            from app.tools.text_chunker import chunk_text  # noqa: PLC0415

            try:
                chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
                logger.info(
                    "[TextChunkerTool] Split %d chars → %d chunks (size=%d, overlap=%d)",
                    len(text),
                    len(chunks),
                    chunk_size,
                    overlap,
                )
                return json.dumps(chunks, ensure_ascii=False)
            except Exception as exc:  # noqa: BLE001
                logger.exception("[TextChunkerTool] Error chunking text")
                return json.dumps({"error": str(exc)})

else:
    class TextChunkerTool:  # type: ignore[no-redef]
        """Stub — crewai is not installed."""

        def __init__(self) -> None:
            raise ImportError(
                "crewai is not installed. Run: uv add crewai"
            )
