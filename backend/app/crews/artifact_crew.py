"""
crews/artifact_crew.py
──────────────────────
Artifact Generation crew — pure Python, no CrewAI agents.

Takes TestCaseOutput (test_cases + requirements) and produces two artifacts:
    1. Unit test files  – runnable test files per language / framework
    2. Test case document – human-readable Markdown specification

Supported languages (auto-detected or caller-specified):
    python (default) | typescript | javascript | java | go | csharp

Pipeline stages:
    1. _detect_language()       – read from input or scan project files
    2. _build_unit_test_files() – group TCs, render per-language files
    3. _build_test_doc()        – render Markdown spec document
    4. _build_fixtures()        – extract JSON test data fixtures

Usage::

    from app.crews.artifact_crew import ArtifactCrew

    crew = ArtifactCrew(run_id="abc-123")
    result = crew.run({
        "test_cases": [...],           # list[TestCase.model_dump()]
        "requirements": [...],         # list[RequirementItem.model_dump()]
        "document_name": "spec.pdf",
        "language": "python",          # optional; auto-detected otherwise
    })
    # result is TestArtifactOutput.model_dump()
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

from app.crews.base_crew import BaseCrew, ProgressCallback
from app.schemas.pipeline_io import TestArtifactOutput, TestLanguage, UnitTestFile
from app.tools.test_file_renderer import (
    group_test_cases,
    render_file,
    render_fixtures,
    render_test_doc_markdown,
)

logger = logging.getLogger(__name__)

# Language detection: project-root config file → language
_LANG_HINTS: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("setup.cfg", "python"),
    ("package.json", "typescript"),  # prefer TS if tsconfig exists alongside
    ("tsconfig.json", "typescript"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("go.mod", "go"),
    ("*.csproj", "csharp"),
    ("*.sln", "csharp"),
]

_FRAMEWORK_MAP = {
    "python": "pytest",
    "typescript": "vitest",
    "javascript": "jest",
    "java": "junit5",
    "go": "go_test",
    "csharp": "xunit",
}


class ArtifactCrew(BaseCrew):
    """
    Pure-Python crew that converts TestCaseOutput into runnable test files
    and a human-readable test case specification document.

    Attributes:
        stage:     ``"artifact"``
        agent_ids: Three logical phase IDs (not CrewAI agents).
    """

    stage = "artifact"
    agent_ids = ["lang_detector", "unit_file_writer", "testcase_doc_writer"]

    def __init__(
        self,
        run_id: str,
        run_profile_id: Optional[str] = None,
        progress_callback: Optional[ProgressCallback] = None,
        mock_mode: Optional[bool] = None,
        project_root: Optional[str] = None,
        **_kwargs: Any,
    ) -> None:
        super().__init__(
            run_id=run_id,
            run_profile_id=run_profile_id,
            progress_callback=progress_callback,
            mock_mode=mock_mode,
        )
        self._project_root = Path(project_root) if project_root else None

    # ─────────────────────────────────────────────────────────────────────────
    # Public entry point
    # ─────────────────────────────────────────────────────────────────────────

    def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Generate test artifacts from TestCaseOutput.

        Args:
            input_data: Must contain:
                ``test_cases``   (list[dict]) – TestCase objects from TestcaseCrew.
                ``requirements`` (list[dict]) – RequirementItem objects (for doc).
                ``document_name`` (str)       – source document name.
            Optional:
                ``language`` (str)            – override language detection.
                ``project_root`` (str)        – path to scan for language hints.

        Returns:
            ``TestArtifactOutput.model_dump()``
        """
        test_cases: list[dict] = input_data.get("test_cases") or []
        requirements: list[dict] = input_data.get("requirements") or []
        document_name: str = input_data.get("document_name") or "document"

        self._emit("log", {"message": f"Starting artifact generation for '{document_name}'", "level": "info"})
        self._emit_agent_started("lang_detector", "Language Detector")

        # ── Phase 1: Detect language ─────────────────────────────────────────
        language_str = (
            input_data.get("language")
            or self._detect_language(input_data.get("project_root"))
        )
        try:
            language = TestLanguage(language_str.lower())
        except ValueError:
            logger.warning("[Artifact][%s] Unknown language %r — defaulting to python", self._run_id, language_str)
            language = TestLanguage.PYTHON

        framework = _FRAMEWORK_MAP[language.value]
        self._emit_agent_completed("lang_detector", output_preview=f"language={language.value}, framework={framework}")
        self._emit("log", {"message": f"Detected language: {language.value} → framework: {framework}", "level": "info"})

        # ── Phase 2: Build unit test files ───────────────────────────────────
        self._emit_agent_started("unit_file_writer", "Unit Test File Writer")
        unit_files = self._build_unit_test_files(test_cases, language, document_name)
        self._emit_agent_completed(
            "unit_file_writer",
            output_preview=f"Generated {len(unit_files)} test file(s) ({sum(f.test_count for f in unit_files)} tests)"
        )

        # ── Phase 3: Build test case document ────────────────────────────────
        self._emit_agent_started("testcase_doc_writer", "Test Case Doc Writer")
        markdown = render_test_doc_markdown(test_cases, requirements, document_name)
        fixtures = render_fixtures(test_cases)
        self._emit_agent_completed(
            "testcase_doc_writer",
            output_preview=f"Generated spec document ({len(markdown):,} chars), {len(fixtures)} fixtures"
        )

        output = TestArtifactOutput(
            unit_test_files=unit_files,
            test_case_markdown=markdown,
            test_fixtures=fixtures,
            language=language,
            document_name=document_name,
        )

        self._emit("log", {
            "message": (
                f"Artifact generation complete: {output.total_files} file(s), "
                f"{output.total_tests} test(s), {len(markdown):,} chars of spec"
            ),
            "level": "info",
        })
        logger.info(
            "[Artifact][%s] Done: %d files / %d tests for '%s'",
            self._run_id, output.total_files, output.total_tests, document_name,
        )
        return output.model_dump()

    # ─────────────────────────────────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _detect_language(self, project_root_override: Optional[str] = None) -> str:
        """
        Detect project language by scanning for well-known config files.
        Falls back to ``python`` when no hints are found.
        """
        root = Path(project_root_override) if project_root_override else self._project_root
        if root and root.exists():
            for pattern, lang in _LANG_HINTS:
                if list(root.glob(pattern)):
                    logger.debug("[Artifact][%s] Language hint '%s' → %s", self._run_id, pattern, lang)
                    return lang
        return "python"

    def _build_unit_test_files(
        self,
        test_cases: list[dict],
        language: TestLanguage,
        doc_name: str,
    ) -> list[UnitTestFile]:
        """Group test cases and render one file per bucket."""
        if not test_cases:
            return []

        buckets = group_test_cases(test_cases)
        files: list[UnitTestFile] = []

        for stem, tcs in buckets.items():
            req_ids = sorted({tc.get("requirement_id", "") for tc in tcs if tc.get("requirement_id")})
            try:
                filename, content = render_file(stem, tcs, language.value, doc_name)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logger.warning("[Artifact][%s] Render failed for stem=%r: %s", self._run_id, stem, exc)
                continue

            files.append(UnitTestFile(
                filename=filename,
                language=language,
                framework=_FRAMEWORK_MAP[language.value],
                content=content,
                test_count=len(tcs),
                requirement_ids=req_ids,
            ))

        return files
