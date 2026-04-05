from __future__ import annotations

"""
services/export_service.py
──────────────────────────
ExportService: Generates HTML or DOCX report from a completed pipeline run.

Usage:
    service = ExportService(run_id)
    html_bytes = await service.export_html()
    docx_bytes = await service.export_docx()
"""

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.db import crud
from app.schemas.pipeline_io import (
    ExecutionOutput,
    IngestionOutput,
    PipelineReport,
    TestCaseOutput,
)
from app.services.docx_builder import DocxReportBuilder

# ─────────────────────────────────────────────────────────────────────────────
# Jinja2 environment – loaded once at module import time
# ─────────────────────────────────────────────────────────────────────────────

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

_jinja_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=True,
)


# ─────────────────────────────────────────────────────────────────────────────
# ExportService
# ─────────────────────────────────────────────────────────────────────────────


class ExportService:
    """Generate HTML or DOCX reports from a completed pipeline run.

    Args:
        run_id: UUID string of the pipeline run to export.
    """

    def __init__(self, run_id: str) -> None:
        self._run_id = run_id

    # ── Public API ────────────────────────────────────────────────────────────

    async def export_html(self) -> bytes:
        """Render the Jinja2 ``report.html.j2`` template and return UTF-8 bytes.

        Returns:
            UTF-8 encoded HTML document.

        Raises:
            ValueError: If the run does not exist in the database.
        """
        data = await self._load_run_data()
        template = _jinja_env.get_template("report.html.j2")
        html_str = template.render(**data)
        return html_str.encode("utf-8")

    async def export_docx(self) -> bytes:
        """Build a DOCX report using :class:`DocxReportBuilder` and return bytes.

        Returns:
            Raw bytes of the generated ``.docx`` file.

        Raises:
            ValueError: If the run does not exist in the database.
        """
        data = await self._load_run_data()

        builder = DocxReportBuilder()

        builder.add_title_page(
            document_name=data["document_name"],
            run_id=data["run_id"],
            generated_at=data["generated_at"],
            status=data["run_status"],
        )

        builder.add_executive_summary(
            summary=data["executive_summary"],
            metrics={
                "Pass Rate": f"{data['pass_rate']:.1f}%",
                "Coverage": f"{data['coverage_percentage']:.1f}%",
                "Total Tests": str(data["total_test_cases"]),
                "Total Requirements": str(len(data["requirements"])),
            },
        )

        if data["requirements"]:
            builder.add_requirements_section(data["requirements"])

        if data["test_cases"]:
            builder.add_test_cases_table(data["test_cases"], data["exec_results"])

        if data["execution"]:
            exec_summary = data["execution"].get("summary", {})
            builder.add_execution_summary(exec_summary)

        if data["report"] and data["report"].get("coverage_analysis"):
            builder.add_coverage_section(data["report"]["coverage_analysis"])

        if data["root_causes"]:
            builder.add_root_cause_section(data["root_causes"])

        if data["recommendations"] or data["risks"]:
            builder.add_recommendations(data["recommendations"], data["risks"])

        return builder.build()

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _load_run_data(self) -> dict:
        """Fetch pipeline run metadata and all stage results from MongoDB.

        Parses each stage's raw output dict into the appropriate Pydantic model
        (falling back to the raw dict if parsing fails), then assembles and
        returns the full template context dict.

        Returns:
            A dict containing all variables expected by the Jinja2 template
            and :class:`DocxReportBuilder`.

        Raises:
            ValueError: If no pipeline run with ``self._run_id`` exists.
        """
        # 1. Load the run document
        run = await crud.get_pipeline_run(self._run_id)
        if run is None:
            raise ValueError(
                f"Pipeline run '{self._run_id}' not found. "
                "The run may not exist or may have been deleted."
            )

        # 2. Load all stage result documents for this run
        results = await crud.get_pipeline_results(self._run_id)

        # 3. Parse each stage output into its Pydantic model
        ingestion: IngestionOutput | None = None
        testcase: TestCaseOutput | None = None
        execution: ExecutionOutput | None = None
        report: PipelineReport | None = None

        for result in results:
            output = result.output  # native BSON dict – no json.loads needed

            if result.stage == "ingestion":
                try:
                    ingestion = IngestionOutput.model_validate(output)
                except Exception:
                    pass  # leave as None; template handles missing data gracefully

            elif result.stage == "testcase":
                try:
                    testcase = TestCaseOutput.model_validate(output)
                except Exception:
                    pass

            elif result.stage == "execution":
                try:
                    execution = ExecutionOutput.model_validate(output)
                except Exception:
                    pass

            elif result.stage == "reporting":
                try:
                    report = PipelineReport.model_validate(output)
                except Exception:
                    pass

        # 4. Build and return the template context dict
        return {
            # ── Run metadata ──────────────────────────────────────────────────
            "run_id": run.run_id,
            "document_name": run.document_name,
            "run_status": run.status,
            "generated_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M:%S UTC"
            ),
            # ── Serialised stage data (JSON-safe dicts or None) ───────────────
            "ingestion": ingestion.model_dump(mode="json") if ingestion else None,
            "testcase": testcase.model_dump(mode="json") if testcase else None,
            "execution": execution.model_dump(mode="json") if execution else None,
            "report": report.model_dump(mode="json") if report else None,
            # ── Convenience lists (pre-serialised for template iteration) ─────
            "test_cases": (
                [tc.model_dump(mode="json") for tc in testcase.test_cases]
                if testcase
                else []
            ),
            "exec_results": (
                [r.model_dump(mode="json") for r in execution.results]
                if execution
                else []
            ),
            "root_causes": (
                [rc.model_dump(mode="json") for rc in report.root_cause_analysis]
                if report
                else []
            ),
            # ── Derived / headline metrics ────────────────────────────────────
            "executive_summary": (
                report.executive_summary
                if report
                else (
                    testcase.design_notes[0]
                    if testcase and testcase.design_notes
                    else ""
                )
            ),
            "pass_rate": (
                report.pass_rate
                if report
                else (execution.summary.pass_rate if execution else 0.0)
            ),
            "coverage_percentage": (
                report.coverage_percentage
                if report
                else (
                    testcase.coverage_summary.coverage_percentage if testcase else 0.0
                )
            ),
            "total_test_cases": (
                report.total_test_cases
                if report
                else (testcase.total_test_cases if testcase else 0)
            ),
            "requirements": (
                [req.model_dump(mode="json") for req in ingestion.requirements]
                if ingestion
                else []
            ),
            "recommendations": (
                report.recommendations
                if report
                else (testcase.recommendations if testcase else [])
            ),
            "risks": (
                report.risk_items if report else (testcase.risks if testcase else [])
            ),
        }
