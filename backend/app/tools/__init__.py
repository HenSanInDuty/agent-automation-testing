"""
tools/ – Auto-AT agent tools package.

Provides reusable tools for document parsing, text chunking,
API execution, and environment config loading.

Exported symbols:
    document_parser : parse_document, parse_pdf, parse_docx, parse_excel
    text_chunker    : chunk_text, chunk_text_rich, TextChunk
    api_runner      : run_api_request, APIRunnerTool (if crewai installed)
    config_loader   : load_env_config, ConfigLoaderTool (if crewai installed)
    registry        : ToolRegistry – central tool slug → instance resolver
"""

from app.tools.registry import ToolRegistry

__all__ = ["ToolRegistry"]
