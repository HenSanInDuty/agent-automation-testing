"""
tools/document_parser_tool.py – CrewAI BaseTool wrapper for document_parser.

Wraps the existing ``parse_document`` function so it can be attached to any
CrewAI agent as a tool, allowing the agent to autonomously extract text from
files (PDF, DOCX, TXT, MD, CSV, XLSX).

Usage::

    from app.tools.document_parser_tool import DocumentParserTool

    tool = DocumentParserTool()
    agent = Agent(..., tools=[tool])
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

try:
    from crewai.tools import BaseTool  # type: ignore[import-untyped]
    from pydantic import BaseModel, Field

    _CREWAI_AVAILABLE = True
except ImportError:
    BaseTool = object  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False

if TYPE_CHECKING:
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Input schema
# ─────────────────────────────────────────────────────────────────────────────

if _CREWAI_AVAILABLE:
    class _DocumentParserInput(BaseModel):
        file_path: str = Field(
            description=(
                "Absolute or relative path to the document file to parse. "
                "Supported formats: PDF, DOCX, TXT, MD, CSV, XLSX, XLS."
            )
        )

else:
    _DocumentParserInput = None  # type: ignore[assignment,misc]


# ─────────────────────────────────────────────────────────────────────────────
# Tool
# ─────────────────────────────────────────────────────────────────────────────

if _CREWAI_AVAILABLE:
    class DocumentParserTool(BaseTool):  # type: ignore[misc]
        """CrewAI tool that extracts plain text from a document file.

        Supports PDF, DOCX, TXT, Markdown, CSV, and Excel files.
        Returns the extracted text as a single string (pages separated by
        blank lines for multi-page documents).
        """

        name: str = "document_parser"
        description: str = (
            "Extract plain text from a document file (PDF, DOCX, TXT, MD, CSV, XLSX). "
            "Provide the absolute file path. "
            "Returns the full text content of the document."
        )
        args_schema: type = _DocumentParserInput

        def _run(self, file_path: str) -> str:  # type: ignore[override]
            from app.tools.document_parser import parse_document  # noqa: PLC0415

            try:
                text = parse_document(file_path)
                if not text:
                    return f"[DocumentParserTool] No text extracted from: {file_path}"
                logger.info(
                    "[DocumentParserTool] Parsed %r → %d chars", file_path, len(text)
                )
                return text
            except FileNotFoundError:
                return f"[DocumentParserTool] File not found: {file_path}"
            except Exception as exc:  # noqa: BLE001
                logger.exception("[DocumentParserTool] Error parsing %r", file_path)
                return f"[DocumentParserTool] Error: {exc}"

else:
    class DocumentParserTool:  # type: ignore[no-redef]
        """Stub — crewai is not installed."""

        def __init__(self) -> None:
            raise ImportError(
                "crewai is not installed. Run: uv add crewai"
            )
