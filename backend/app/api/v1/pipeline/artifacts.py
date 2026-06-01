"""
pipeline/artifacts.py – Download endpoints for run artifacts.

Adds download support for Dev / Tester roles to grab the raw inputs and
outputs of a pipeline run:

    GET /pipeline/runs/{run_id}/artifacts/testcases           – JSON or Markdown spec
    GET /pipeline/runs/{run_id}/artifacts/unit-tests          – list generated unit-test files
    GET /pipeline/runs/{run_id}/artifacts/unit-tests/zip      – ZIP all generated unit-test files
    GET /pipeline/runs/{run_id}/artifacts/unit-tests/file     – download a single unit-test file
    GET /pipeline/runs/{run_id}/artifacts/execution-result    – execution results (JSON)
    GET /pipeline/runs/{run_id}/artifacts/bundle              – ZIP of every artifact for the run

Sources:
    - Test case payload                                from agent outputs (DB)
    - Unit test files + Markdown spec                  from artifact_pipeline node (DB)
    - Playwright source files (TS spec, fixtures, …)   from MinIO runs/{run_id}/playwright/
    - Execution results                                from execution agent (DB)
    - HTML / DOCX report                               from ExportService (rendered on demand)
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import posixpath
import zipfile
from typing import Annotated, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from fastapi.responses import Response as FastAPIResponse

from app.db import crud

from ._helpers import _get_run_or_404

logger = logging.getLogger(__name__)

router = APIRouter()

# Agents whose output carries test_cases / unit_test_files / executions.
_TESTCASE_AGENT_IDS = frozenset(
    {"testcase_generator", "api_test_case_generator", "testcase_aggregator"}
)
_ARTIFACT_NODE_IDS = frozenset({"artifact_pipeline", "test_artifact_generator"})
_EXECUTION_AGENT_IDS = frozenset(
    {"result_store", "execution_logger", "test_runner", "api_test_runner"}
)


# ─────────────────────────────────────────────────────────────────────────────
# DB → payload extraction helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _collect_test_cases(run_id: str) -> list[dict[str, Any]]:
    """Find test_cases[] in any agent output for *run_id*."""
    results = await crud.get_pipeline_results(run_id)
    for r in results:
        output = r.output or {}
        if not isinstance(output, dict):
            continue
        agent_id = (r.agent_id or "").lower()
        # Fast-path: known testcase agents.
        if agent_id in _TESTCASE_AGENT_IDS and output.get("test_cases"):
            return list(output["test_cases"])
        # Fallback: any agent that happens to publish a non-empty test_cases.
        if isinstance(output.get("test_cases"), list) and output["test_cases"]:
            return list(output["test_cases"])
    return []


async def _collect_artifact_bundle(
    run_id: str,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    """Return (unit_test_files, test_case_markdown, fixtures) from ArtifactCrew output."""
    results = await crud.get_pipeline_results(run_id)
    for r in results:
        output = r.output or {}
        if not isinstance(output, dict):
            continue
        agent_id = (r.agent_id or "").lower()
        stage = (r.stage or "").lower()
        if agent_id in _ARTIFACT_NODE_IDS or stage == "artifact" or "unit_test_files" in output:
            files = output.get("unit_test_files") or []
            markdown = output.get("test_case_markdown") or ""
            fixtures = output.get("test_fixtures") or {}
            if isinstance(files, list):
                return files, markdown, fixtures if isinstance(fixtures, dict) else {}
    return [], "", {}


async def _collect_execution_output(run_id: str) -> Optional[dict[str, Any]]:
    """Return the full ExecutionOutput dict (results, summary, timings)."""
    results = await crud.get_pipeline_results(run_id)
    for r in results:
        output = r.output or {}
        if not isinstance(output, dict):
            continue
        agent_id = (r.agent_id or "").lower()
        stage = (r.stage or "").lower()
        if (
            agent_id in _EXECUTION_AGENT_IDS
            or stage == "execution"
            or "results" in output
            and any(
                isinstance(item, dict) and "test_case_id" in item
                for item in output.get("results", [])
            )
        ):
            return output
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Test cases download
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/artifacts/testcases",
    summary="Download generated test cases",
    description=(
        "Returns the test cases produced by the test case generation stage as "
        "either JSON (default) or Markdown (the human-readable specification)."
    ),
    response_class=Response,
)
async def download_test_cases(
    run_id: str,
    fmt: Annotated[
        str,
        Query(
            alias="format",
            description="Output format: 'json' (default) or 'md'",
            pattern="^(json|md)$",
        ),
    ] = "json",
) -> Response:
    await _get_run_or_404(run_id)

    if fmt == "md":
        _, markdown, _ = await _collect_artifact_bundle(run_id)
        if not markdown:
            # Fall back to a minimal Markdown rendering of test_cases if the
            # ArtifactCrew did not run for this template.
            test_cases = await _collect_test_cases(run_id)
            if not test_cases:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No test cases found for this run.",
                )
            markdown = _render_minimal_markdown(test_cases)
        filename = f"test-cases-{run_id[:8]}.md"
        return FastAPIResponse(
            content=markdown.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # JSON
    test_cases = await _collect_test_cases(run_id)
    if not test_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No test cases found for this run.",
        )
    payload = json.dumps(
        {"run_id": run_id, "count": len(test_cases), "test_cases": test_cases},
        ensure_ascii=False,
        indent=2,
        default=str,
    )
    filename = f"test-cases-{run_id[:8]}.json"
    return FastAPIResponse(
        content=payload.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _render_minimal_markdown(test_cases: list[dict[str, Any]]) -> str:
    """Render a basic Markdown table from raw test_case dicts."""
    lines = ["# Test Cases", "", f"Total: **{len(test_cases)}**", ""]
    for tc in test_cases:
        if not isinstance(tc, dict):
            continue
        lines.append(f"## {tc.get('id', '?')} — {tc.get('title', '')}")
        if tc.get("description"):
            lines.append("")
            lines.append(str(tc["description"]))
        if tc.get("preconditions"):
            lines.extend(["", "**Preconditions:** " + str(tc["preconditions"])])
        steps = tc.get("steps") or []
        if isinstance(steps, list) and steps:
            lines.extend(["", "**Steps:**"])
            for i, step in enumerate(steps, 1):
                if isinstance(step, dict):
                    action = step.get("action") or step.get("description") or step
                    expected = step.get("expected_result") or step.get("expected") or ""
                    line = f"{i}. {action}"
                    if expected:
                        line += f" → _{expected}_"
                    lines.append(line)
                else:
                    lines.append(f"{i}. {step}")
        lines.append("")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Unit test files (from ArtifactCrew, DB-backed)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/artifacts/unit-tests",
    summary="List generated unit test files",
    description="Returns metadata for each unit test file produced by the artifact stage.",
)
async def list_unit_test_files(run_id: str) -> list[dict]:
    await _get_run_or_404(run_id)
    files, _markdown, _fixtures = await _collect_artifact_bundle(run_id)
    return [
        {
            "filename": f.get("filename") or f"test_{i}.txt",
            "language": f.get("language") or "",
            "framework": f.get("framework") or "",
            "test_count": f.get("test_count") or 0,
            "size_bytes": len((f.get("content") or "").encode("utf-8")),
        }
        for i, f in enumerate(files)
        if isinstance(f, dict)
    ]


@router.get(
    "/runs/{run_id}/artifacts/unit-tests/file",
    summary="Download a single unit test file",
    response_class=Response,
)
async def download_unit_test_file(
    run_id: str,
    name: Annotated[str, Query(description="Filename returned by list_unit_test_files")],
) -> Response:
    await _get_run_or_404(run_id)

    # Reject traversal attempts — these names came from LLM output.
    normalised = posixpath.basename(name)
    if normalised in ("", ".", "..") or normalised != name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename.")

    files, _markdown, _fixtures = await _collect_artifact_bundle(run_id)
    for f in files:
        if isinstance(f, dict) and f.get("filename") == normalised:
            content = (f.get("content") or "").encode("utf-8")
            return FastAPIResponse(
                content=content,
                media_type="text/plain; charset=utf-8",
                headers={"Content-Disposition": f'attachment; filename="{normalised}"'},
            )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unit test file not found: {name}")


@router.get(
    "/runs/{run_id}/artifacts/unit-tests/zip",
    summary="Download all generated unit test files as a ZIP",
    response_class=Response,
)
async def download_unit_tests_zip(run_id: str) -> Response:
    await _get_run_or_404(run_id)
    files, _markdown, fixtures = await _collect_artifact_bundle(run_id)
    if not files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No unit test files found for this run.",
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if not isinstance(f, dict):
                continue
            filename = f.get("filename") or "test.txt"
            zf.writestr(filename, f.get("content") or "")
        if fixtures:
            zf.writestr(
                "fixtures.json",
                json.dumps(fixtures, ensure_ascii=False, indent=2, default=str),
            )

    filename = f"unit-tests-{run_id[:8]}.zip"
    return FastAPIResponse(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Execution result
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/artifacts/execution-result",
    summary="Download execution results as JSON",
    response_class=Response,
)
async def download_execution_result(run_id: str) -> Response:
    await _get_run_or_404(run_id)
    output = await _collect_execution_output(run_id)
    if not output:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No execution result found for this run.",
        )
    payload = json.dumps({"run_id": run_id, **output}, ensure_ascii=False, indent=2, default=str)
    filename = f"execution-result-{run_id[:8]}.json"
    return FastAPIResponse(
        content=payload.encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Bundle (everything)
# ─────────────────────────────────────────────────────────────────────────────


@router.get(
    "/runs/{run_id}/artifacts/bundle",
    summary="Download every artifact for a run as a single ZIP",
    description=(
        "Bundles test cases (JSON + Markdown), unit-test files, Playwright source "
        "files (if any), and the execution result into one ZIP for Dev/QA hand-off."
    ),
    response_class=Response,
)
async def download_bundle(run_id: str) -> Response:
    await _get_run_or_404(run_id)

    loop = asyncio.get_running_loop()

    buf = io.BytesIO()
    written = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) test_cases
        test_cases = await _collect_test_cases(run_id)
        if test_cases:
            zf.writestr(
                "test-cases/test-cases.json",
                json.dumps(
                    {"run_id": run_id, "count": len(test_cases), "test_cases": test_cases},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            )
            written += 1

        # 2) Artifact crew output: unit tests + markdown spec + fixtures
        unit_files, markdown, fixtures = await _collect_artifact_bundle(run_id)
        if markdown:
            zf.writestr("test-cases/test-cases.md", markdown)
            written += 1
        for f in unit_files:
            if not isinstance(f, dict):
                continue
            fname = f.get("filename") or "test.txt"
            zf.writestr(f"unit-tests/{fname}", f.get("content") or "")
            written += 1
        if fixtures:
            zf.writestr(
                "unit-tests/fixtures.json",
                json.dumps(fixtures, ensure_ascii=False, indent=2, default=str),
            )
            written += 1

        # 3) Playwright artifacts from MinIO (if any)
        try:
            from app.services.storage_service import storage

            pw_files = await loop.run_in_executor(None, storage.list_playwright_files, run_id)
            for entry in pw_files:
                rel_path = entry.get("path") if isinstance(entry, dict) else None
                if not rel_path:
                    continue
                data = await loop.run_in_executor(
                    None, storage.download_playwright_file, run_id, rel_path
                )
                zf.writestr(f"playwright/{rel_path}", data)
                written += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[bundle] Skipping Playwright artifacts: %s", exc)

        # 4) Execution result
        execution = await _collect_execution_output(run_id)
        if execution:
            zf.writestr(
                "execution/execution-result.json",
                json.dumps(
                    {"run_id": run_id, **execution},
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                ),
            )
            written += 1

    if written == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No downloadable artifacts found for this run yet.",
        )

    filename = f"auto-at-bundle-{run_id[:8]}.zip"
    return FastAPIResponse(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
