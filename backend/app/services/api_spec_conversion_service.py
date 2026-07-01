"""Convert user API documents into the pipeline Markdown contract."""

from __future__ import annotations

import asyncio
import inspect
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.core.llm_factory import LLMFactory
from app.tools.md_api_spec_validator import ValidationResult, validate_md_api_spec

_MAX_SOURCE_CHARS = 60_000
_LLM_TIMEOUT_SECONDS = 90
# Weak local models produce contract-conformant Markdown only intermittently, so
# re-roll the conversion a few times and keep the first valid (or least-broken)
# draft. A stronger model typically succeeds on the first attempt.
_MAX_CONVERSION_ATTEMPTS = 3


class APISpecConversionResult(BaseModel):
    filename: str
    markdown: str
    validation: ValidationResult


def _conversion_prompt(source: str, source_name: str, base_url: str) -> str:
    return f"""Convert the API document below into the Auto-AT Markdown contract.

Rules:
- Return Markdown only, without code fences or commentary.
- Preserve every endpoint and every documented request/response detail.
- Use this exact base URL: {base_url}
- Start with a title, then `- Base URL: ...`, then exactly one `## Headers` table.
- The `## Headers` table is REQUIRED. It MUST use this exact column layout — a
  `Name`/`Value` header row, the separator row, then one data row per header:

      | Name | Value |
      | :--- | :--- |
      | Content-Type | application/json |

  If the source documents no request headers, keep the `Content-Type` row above.
  Never put secret or credential values in this table.
- For each endpoint use `## API: <name>`, then `### Endpoint`,
  `### Request`, and `### Response`.
- Endpoint requires `- Method:` and `- Path:`.
- Request must contain a field table or JSON body. Use `{{}}` when the source
  explicitly has no body; mark undocumented details as `not documented`.
- Response requires at least one HTTP status and JSON body/schema.
- Never invent credentials, business rules, paths, or status codes.

Source filename: {source_name}

--- SOURCE DOCUMENT ---
{source}
--- END SOURCE DOCUMENT ---
"""


def _strip_markdown_fence(value: Any) -> str:
    text = str(value or "").strip()
    match = re.fullmatch(r"```(?:markdown|md)?\s*\n(.*)\n```", text, re.DOTALL)
    return match.group(1).strip() if match else text


async def _call_llm(llm: Any, prompt: str) -> str:
    result = await asyncio.wait_for(
        asyncio.to_thread(llm.call, prompt),
        timeout=_LLM_TIMEOUT_SECONDS,
    )
    if inspect.isawaitable(result):
        result = await asyncio.wait_for(result, timeout=_LLM_TIMEOUT_SECONDS)
    return _strip_markdown_fence(result)


async def convert_api_document(
    source_text: str,
    *,
    source_name: str,
    base_url: str,
    llm_profile_id: str | None = None,
) -> APISpecConversionResult:
    """Convert extracted source text and validate the generated contract."""
    source = source_text.strip()
    if not source:
        raise ValueError("The uploaded document does not contain readable text.")
    if len(source) > _MAX_SOURCE_CHARS:
        raise ValueError(
            f"Document text exceeds {_MAX_SOURCE_CHARS:,} characters; split it before conversion."
        )

    llm = await LLMFactory(run_profile_id=llm_profile_id).build_default()
    prompt = _conversion_prompt(source, source_name, base_url)

    best_markdown = ""
    best_validation: ValidationResult | None = None
    for _ in range(_MAX_CONVERSION_ATTEMPTS):
        markdown = await _call_llm(llm, prompt)
        validation = validate_md_api_spec(markdown, strict=True)
        if validation.valid:
            best_markdown, best_validation = markdown, validation
            break
        # Track the least-broken draft so the caller still sees concrete,
        # actionable validation errors when no attempt fully passes.
        if best_validation is None or len(validation.field_errors) < len(
            best_validation.field_errors
        ):
            best_markdown, best_validation = markdown, validation

    stem = Path(source_name).stem or "api-spec"
    return APISpecConversionResult(
        filename=f"{stem}-pipeline.md",
        markdown=best_markdown,
        validation=best_validation,
    )
