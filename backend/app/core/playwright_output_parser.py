"""
core/playwright_output_parser.py – Robust extractor for Playwright LLM outputs.

LLMs routinely ignore the expected_output schema and return data in many ad-hoc
formats.  This module normalises all observed patterns into a stable
``dict[filename → content]`` mapping that can be uploaded to MinIO.

Supported patterns (per agent):

playwright_spec_writer
    A. spec_files: {filepath: ts_content}                  (ideal)
    B. test_file_name + description + steps                 (structured metadata)
    C. test_cases: [{name, description, steps}]             (grouped metadata)
    D. raw_output containing JSON with test_code/test_file  (escaped TypeScript)
    E. raw_output containing TypeScript directly            (raw TS string)

playwright_fixture_writer
    A. page_objects + fixtures_ts + test_data_ts + playwright_config_ts + env_example  (ideal)
    B. raw_output containing JSON with test_code/test_file  (single spec fallback)
    C. raw_output containing TypeScript directly
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# ── Default filenames for plain-string output keys ────────────────────────────
_PLAIN_KEY_FILENAMES: dict[str, str] = {
    "fixtures_ts": "fixtures.ts",
    "test_data_ts": "test-data.ts",
    "playwright_config_ts": "playwright.config.ts",
    "env_example": ".env.example",
}

# ── Keys that represent dict[filepath, content] ───────────────────────────────
_DICT_FILE_KEYS = ("spec_files", "page_objects")

# All keys that, when present, should trigger artifact saving
ARTIFACT_TRIGGER_KEYS = (
    *_DICT_FILE_KEYS,
    *_PLAIN_KEY_FILENAMES,
    "test_file_name",
    "test_cases",
    "raw_output",
    "test_code",
)


def _esc(s: object) -> str:
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", " ")
        .replace("\r", "")
    )


def _synthesize_from_metadata(output: dict) -> dict[str, str]:  # type: ignore[type-arg]
    """Pattern B: test_file_name + description + steps → single .spec.ts."""
    test_file_name = _esc(output.get("test_file_name") or "playwright_spec")
    test_description = _esc(output.get("test_description") or "Playwright E2E test")
    steps = output.get("steps") or []

    lines = [
        'import { test, expect } from "@playwright/test";',
        "",
        f'test.describe("{test_file_name}", () => {{',
        f'  test("{test_description}", async ({{ page }}) => {{',
    ]
    for step in steps:
        if not isinstance(step, dict):
            continue
        num = step.get("step_number", "")
        action = _esc(step.get("action", ""))
        details = _esc(step.get("details", ""))
        lines.append(f"    // Step {num}: {action}")
        if details:
            lines.append(f"    //   {details}")
        lines.append("    // TODO: add Playwright automation")
        lines.append("")
    lines += ["  });", "});", ""]

    safe = str(output.get("test_file_name") or "playwright_spec").replace(" ", "_")
    return {f"{safe}.spec.ts": "\n".join(lines)}


def _synthesize_from_test_cases(output: dict) -> dict[str, str]:  # type: ignore[type-arg]
    """Pattern C: test_cases: [{name, description, steps}] → grouped .spec.ts."""
    test_cases = output.get("test_cases") or []
    if not isinstance(test_cases, list) or not test_cases:
        return {}

    lines = [
        'import { test, expect } from "@playwright/test";',
        "",
        'test.describe("Generated Playwright Tests", () => {',
    ]
    for tc in test_cases:
        if not isinstance(tc, dict):
            continue
        name = _esc(tc.get("name") or tc.get("title") or "test case")
        desc = _esc(tc.get("description") or "")
        steps = tc.get("steps") or []

        lines.append(f'  test("{name}", async ({{ page }}) => {{')
        if desc:
            lines.append(f'    // {desc}')
        for step in steps:
            step_str = _esc(step) if isinstance(step, str) else _esc(step.get("action", step))
            lines.append(f"    // {step_str}")
            lines.append("    // TODO: add Playwright automation")
        lines.append("  });")
        lines.append("")
    lines += ["});", ""]

    return {"generated_tests.spec.ts": "\n".join(lines)}


# Default filename when extraction can't determine a better name
_DEFAULT_SPEC_FILENAME = "extracted_tests.spec.ts"


def _extract_from_raw_output(raw: str) -> dict[str, str]:
    """Patterns D/E: extract TypeScript from raw_output string.

    Tries in order:
    1. Embedded JSON with test_code field → use as TypeScript
    2. Direct TypeScript (starts with import / test. / describe)
    """
    if not raw or not isinstance(raw, str):
        return {}

    # 1. Embedded JSON → look for test_code
    json_match = re.search(r"\{[\s\S]+\}", raw)
    if json_match:
        try:
            obj = json.loads(json_match.group(0))
            code = obj.get("test_code") or obj.get("code") or obj.get("content")
            if code and isinstance(code, str) and len(code) > 50:
                filename = obj.get("test_file") or obj.get("filename") or _DEFAULT_SPEC_FILENAME
                if not filename.endswith(".ts"):
                    filename += ".spec.ts"
                return {filename: code}
        except (json.JSONDecodeError, TypeError):
            pass

    # 2. Markdown code fence containing TypeScript
    fence = re.search(r"```(?:typescript|ts|javascript|js)?\s*\n([\s\S]*?)```", raw)
    if fence:
        code = fence.group(1).strip()
        if len(code) > 50:
            return {_DEFAULT_SPEC_FILENAME: code}

    # 3. Raw string looks like TypeScript
    stripped = raw.strip()
    if stripped.startswith("import ") or "test.describe" in stripped or "test(" in stripped:
        if len(stripped) > 50:
            return {_DEFAULT_SPEC_FILENAME: stripped}

    return {}


def extract_playwright_files(
    agent_id: str,
    output: dict,  # type: ignore[type-arg]
) -> dict[str, str]:
    """Extract a filename → TypeScript content mapping from any LLM output format.

    Returns an empty dict when no usable file content can be found.
    """
    if not isinstance(output, dict):
        return {}

    files: dict[str, str] = {}

    # Pattern A — direct file dict keys
    for key in _DICT_FILE_KEYS:
        val = output.get(key)
        if isinstance(val, dict):
            for filepath, content in val.items():
                if isinstance(content, str) and content.strip():
                    files[filepath] = content

    # Pattern A — plain string keys with default names
    for key, default_name in _PLAIN_KEY_FILENAMES.items():
        val = output.get(key)
        if isinstance(val, str) and val.strip():
            files[default_name] = val

    if files:
        return files

    # Pattern B — structured single spec (test_file_name + steps)
    if output.get("test_file_name"):
        return _synthesize_from_metadata(output)

    # Pattern C — test_cases list
    if output.get("test_cases"):
        result = _synthesize_from_test_cases(output)
        if result:
            return result

    # Pattern D/E — raw_output
    raw = output.get("raw_output")
    if raw:
        result = _extract_from_raw_output(raw)
        if result:
            return result

    # Pattern D/E — test_code directly in output
    code = output.get("test_code") or output.get("code")
    if isinstance(code, str) and code.strip():
        filename = str(output.get("test_file") or output.get("filename") or _DEFAULT_SPEC_FILENAME)
        if not filename.endswith(".ts"):
            filename += ".spec.ts"
        return {filename: code}

    logger.warning(
        "[playwright_output_parser] agent=%r — no file content found in output keys: %s",
        agent_id,
        list(output.keys()),
    )
    return {}
