from __future__ import annotations

"""
tests/test_phase10.py – Phase 10: Report Export test suite.

Tests cover:
  - ExportService.export_html()  → returns valid UTF-8 HTML bytes
  - ExportService.export_docx()  → returns valid DOCX bytes (ZIP magic)
  - ExportService._load_run_data() → correct context dict assembly
  - DocxReportBuilder              → each section can be built without error
  - GET /api/v1/pipeline/runs/{run_id}/export/html  → 200 / 404 / 400
  - GET /api/v1/pipeline/runs/{run_id}/export/docx  → 200 / 404 / 400

All external I/O (MongoDB / Beanie) is mocked via unittest.mock.

Run:
    cd backend
    uv run pytest tests/test_phase10.py -v
"""

import io
import uuid
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Shared helpers / factories
# ─────────────────────────────────────────────────────────────────────────────

_RUN_ID = str(uuid.uuid4())
_DOC_NAME = "SampleSRS.pdf"


def _make_run_doc(
    run_id: str = _RUN_ID,
    status: str = "completed",
    document_name: str = _DOC_NAME,
) -> MagicMock:
    """Return a minimal PipelineRunDocument mock."""
    doc = MagicMock()
    doc.run_id = run_id
    doc.document_name = document_name
    doc.status = status
    doc.created_at = datetime.now(timezone.utc)
    doc.started_at = datetime.now(timezone.utc)
    doc.finished_at = datetime.now(timezone.utc)
    return doc


def _make_result_doc(stage: str, output: dict) -> MagicMock:
    """Return a minimal PipelineResultDocument mock."""
    doc = MagicMock()
    doc.run_id = _RUN_ID
    doc.stage = stage
    doc.agent_id = "crew_output"
    doc.output = output
    doc.created_at = datetime.now(timezone.utc)
    return doc


# ── Minimal stage outputs ─────────────────────────────────────────────────────

_INGESTION_OUTPUT = {
    "document_name": _DOC_NAME,
    "total_requirements": 2,
    "chunks_processed": 3,
    "processing_notes": [],
    "requirements": [
        {
            "id": "REQ-001",
            "title": "User login",
            "description": "Users must log in with email and password.",
            "type": "functional",
            "priority": "high",
            "tags": [],
            "notes": "",
            "raw_text": "",
            "source_chunk": None,
        },
        {
            "id": "REQ-002",
            "title": "Response time",
            "description": "API must respond within 500ms.",
            "type": "non_functional",
            "priority": "medium",
            "tags": [],
            "notes": "",
            "raw_text": "",
            "source_chunk": None,
        },
    ],
}

_TESTCASE_OUTPUT = {
    "test_cases": [
        {
            "id": "TC-001",
            "requirement_id": "REQ-001",
            "title": "Valid login",
            "description": "Login with correct credentials",
            "preconditions": "User account exists",
            "steps": [
                {
                    "step_number": 1,
                    "action": "POST /auth/login",
                    "expected_result": "200 OK",
                },
            ],
            "expected_result": "JWT token returned",
            "test_type": "api",
            "category": "positive",
            "priority": "high",
            "tags": [],
            "automation_script": None,
            "api_endpoint": "/auth/login",
            "http_method": "POST",
            "request_headers": None,
            "request_body": None,
            "expected_status_code": 200,
            "ui_page": None,
            "ui_selector": None,
        },
        {
            "id": "TC-002",
            "requirement_id": "REQ-001",
            "title": "Invalid login",
            "description": "Login with wrong password",
            "preconditions": "",
            "steps": [],
            "expected_result": "401 Unauthorised",
            "test_type": "api",
            "category": "negative",
            "priority": "medium",
            "tags": [],
            "automation_script": None,
            "api_endpoint": "/auth/login",
            "http_method": "POST",
            "request_headers": None,
            "request_body": None,
            "expected_status_code": 401,
            "ui_page": None,
            "ui_selector": None,
        },
    ],
    "total_test_cases": 2,
    "coverage_summary": {
        "total_requirements": 2,
        "covered_requirements": 1,
        "coverage_percentage": 50.0,
        "uncovered_requirements": ["REQ-002"],
        "by_type": {"functional": 2},
        "by_priority": {"high": 1, "medium": 1},
        "by_category": {"positive": 1, "negative": 1},
        "coverage_gaps": [],
    },
    "automation_readiness": {
        "total_automated": 0,
        "automation_percentage": 0.0,
        "frameworks_used": [],
    },
    "design_notes": ["Initial test design complete."],
    "risks": ["REQ-002 has no functional tests yet."],
    "recommendations": ["Add performance tests for REQ-002."],
}

_EXECUTION_OUTPUT = {
    "results": [
        {
            "test_case_id": "TC-001",
            "status": "passed",
            "duration_ms": 123.4,
            "actual_result": "200 OK, token returned",
            "actual_status_code": 200,
            "actual_response": {"token": "abc"},
            "error_message": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logs": [],
        },
        {
            "test_case_id": "TC-002",
            "status": "failed",
            "duration_ms": 45.6,
            "actual_result": "200 OK (expected 401)",
            "actual_status_code": 200,
            "actual_response": {},
            "error_message": "Expected status 401, got 200",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "logs": [],
        },
    ],
    "summary": {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "skipped": 0,
        "errors": 0,
        "pass_rate": 50.0,
        "duration_seconds": 0.169,
    },
    "environment": "default",
    "timing_stats": {"min_ms": 45.6, "max_ms": 123.4, "avg_ms": 84.5, "p95_ms": 120.0},
    "failure_patterns": [],
    "execution_notes": [],
}

_REPORT_OUTPUT = {
    "coverage_percentage": 50.0,
    "coverage_analysis": {
        "total_requirements": 2,
        "covered_requirements": 1,
        "validated_requirements": 1,
        "coverage_percentage": 50.0,
        "validation_percentage": 50.0,
        "uncovered_requirements": ["REQ-002"],
        "failed_requirements": ["REQ-001"],
        "by_type": {"functional": 1},
        "by_priority": {"high": 1},
        "requirement_details": [],
    },
    "root_cause_analysis": [
        {
            "test_case_id": "TC-002",
            "failure_pattern": "Auth endpoint returning 200 for invalid creds",
            "probable_cause": "Bug in authentication middleware",
            "root_cause_category": "authentication",
            "recommendation": "Fix auth middleware validation logic",
            "affected_tests": ["TC-002"],
            "severity": "high",
            "suggested_fix": "Return 401 when credentials are invalid",
        }
    ],
    "executive_summary": "50% pass rate. One authentication bug found.",
    "recommendations": ["Fix auth middleware", "Add REQ-002 tests"],
    "risk_items": ["Production auth bypass risk"],
    "total_test_cases": 2,
    "pass_rate": 50.0,
    "metrics": {},
    "generated_at": datetime.now(timezone.utc).isoformat(),
}


# ─────────────────────────────────────────────────────────────────────────────
# DocxReportBuilder unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestDocxReportBuilder:
    """Verify that each section of DocxReportBuilder generates valid DOCX bytes."""

    def test_build_empty_document_returns_valid_docx(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        result = builder.build()
        assert isinstance(result, bytes)
        assert len(result) > 0
        # DOCX is a ZIP archive – verify magic bytes (PK\x03\x04)
        assert result[:4] == b"PK\x03\x04", "DOCX bytes must start with ZIP magic"

    def test_add_title_page_produces_valid_docx(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_title_page(
            document_name="Test App SRS.pdf",
            run_id=_RUN_ID,
            generated_at="2024-01-15 10:00:00 UTC",
            status="completed",
        )
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_executive_summary_produces_valid_docx(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_executive_summary(
            summary="50% pass rate. One bug found.",
            metrics={
                "Pass Rate": "50.0%",
                "Coverage": "50.0%",
                "Total Tests": "2",
                "Total Requirements": "2",
            },
        )
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_executive_summary_empty_metrics(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_executive_summary(summary="Some summary", metrics={})
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_requirements_section(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_requirements_section(_INGESTION_OUTPUT["requirements"])
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_requirements_section_empty_is_noop(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_requirements_section([])
        # Should not raise
        result = builder.build()
        assert isinstance(result, bytes)

    def test_add_test_cases_table_with_exec_results(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_test_cases_table(
            _TESTCASE_OUTPUT["test_cases"],
            _EXECUTION_OUTPUT["results"],
        )
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_test_cases_table_without_exec_results(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_test_cases_table(_TESTCASE_OUTPUT["test_cases"], [])
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_execution_summary(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_execution_summary(_EXECUTION_OUTPUT["summary"])
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_execution_summary_empty_is_noop(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_execution_summary({})
        result = builder.build()
        assert isinstance(result, bytes)

    def test_add_coverage_section(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_coverage_section(_REPORT_OUTPUT["coverage_analysis"])
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_coverage_section_empty_is_noop(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_coverage_section({})
        result = builder.build()
        assert isinstance(result, bytes)

    def test_add_root_cause_section(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_root_cause_section(_REPORT_OUTPUT["root_cause_analysis"])
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_root_cause_section_empty_is_noop(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_root_cause_section([])
        result = builder.build()
        assert isinstance(result, bytes)

    def test_add_recommendations(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_recommendations(
            recommendations=["Fix auth", "Add tests"],
            risks=["Production bypass"],
        )
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

    def test_add_recommendations_empty(self):
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_recommendations(recommendations=[], risks=[])
        result = builder.build()
        assert isinstance(result, bytes)

    def test_full_document_all_sections(self):
        """Build a document with all sections populated — no exception, valid DOCX."""
        from app.services.docx_builder import DocxReportBuilder

        builder = DocxReportBuilder()
        builder.add_title_page(
            document_name=_DOC_NAME,
            run_id=_RUN_ID,
            generated_at="2024-01-15 10:00:00 UTC",
            status="completed",
        )
        builder.add_executive_summary(
            summary=_REPORT_OUTPUT["executive_summary"],
            metrics={
                "Pass Rate": "50.0%",
                "Coverage": "50.0%",
                "Total Tests": "2",
                "Total Requirements": "2",
            },
        )
        builder.add_requirements_section(_INGESTION_OUTPUT["requirements"])
        builder.add_test_cases_table(
            _TESTCASE_OUTPUT["test_cases"],
            _EXECUTION_OUTPUT["results"],
        )
        builder.add_execution_summary(_EXECUTION_OUTPUT["summary"])
        builder.add_coverage_section(_REPORT_OUTPUT["coverage_analysis"])
        builder.add_root_cause_section(_REPORT_OUTPUT["root_cause_analysis"])
        builder.add_recommendations(
            recommendations=_REPORT_OUTPUT["recommendations"],
            risks=_REPORT_OUTPUT["risk_items"],
        )
        result = builder.build()
        assert result[:4] == b"PK\x03\x04"

        # Verify we can open it as a valid ZIP (all DOCX files are ZIPs)
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            names = zf.namelist()
        assert "word/document.xml" in names, "DOCX must contain word/document.xml"


# ─────────────────────────────────────────────────────────────────────────────
# ExportService unit tests
# ─────────────────────────────────────────────────────────────────────────────


class TestExportServiceLoadRunData:
    """Tests for ExportService._load_run_data()."""

    @pytest.mark.asyncio
    async def test_raises_value_error_when_run_not_found(self):
        from app.services.export_service import ExportService

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=None)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService("nonexistent-run-id")
            with pytest.raises(ValueError, match="not found"):
                await service._load_run_data()

    @pytest.mark.asyncio
    async def test_returns_correct_run_metadata(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        assert data["run_id"] == _RUN_ID
        assert data["document_name"] == _DOC_NAME
        assert data["run_status"] == "completed"
        assert "generated_at" in data
        assert "UTC" in data["generated_at"]

    @pytest.mark.asyncio
    async def test_parses_ingestion_output(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_doc = _make_result_doc("ingestion", _INGESTION_OUTPUT)

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[result_doc])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        assert data["ingestion"] is not None
        assert len(data["requirements"]) == 2
        assert data["requirements"][0]["id"] == "REQ-001"

    @pytest.mark.asyncio
    async def test_parses_testcase_output(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_doc = _make_result_doc("testcase", _TESTCASE_OUTPUT)

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[result_doc])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        assert data["testcase"] is not None
        assert len(data["test_cases"]) == 2
        assert data["test_cases"][0]["id"] == "TC-001"
        assert data["total_test_cases"] == 2
        # With no report stage, coverage falls back to testcase coverage
        assert data["coverage_percentage"] == 50.0

    @pytest.mark.asyncio
    async def test_parses_execution_output(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_doc = _make_result_doc("execution", _EXECUTION_OUTPUT)

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[result_doc])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        assert data["execution"] is not None
        assert len(data["exec_results"]) == 2
        assert data["exec_results"][0]["test_case_id"] == "TC-001"
        # pass_rate should come from execution summary when no report
        assert data["pass_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_parses_reporting_output(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_doc = _make_result_doc("reporting", _REPORT_OUTPUT)

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[result_doc])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        assert data["report"] is not None
        assert len(data["root_causes"]) == 1
        assert (
            data["executive_summary"] == "50% pass rate. One authentication bug found."
        )
        assert data["pass_rate"] == 50.0
        assert len(data["recommendations"]) == 2
        assert len(data["risks"]) == 1

    @pytest.mark.asyncio
    async def test_all_stages_present(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_docs = [
            _make_result_doc("ingestion", _INGESTION_OUTPUT),
            _make_result_doc("testcase", _TESTCASE_OUTPUT),
            _make_result_doc("execution", _EXECUTION_OUTPUT),
            _make_result_doc("reporting", _REPORT_OUTPUT),
        ]

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=result_docs)

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        # All sections populated
        assert data["ingestion"] is not None
        assert data["testcase"] is not None
        assert data["execution"] is not None
        assert data["report"] is not None
        # report takes priority for derived metrics
        assert data["pass_rate"] == _REPORT_OUTPUT["pass_rate"]
        assert data["coverage_percentage"] == _REPORT_OUTPUT["coverage_percentage"]
        assert data["total_test_cases"] == _REPORT_OUTPUT["total_test_cases"]

    @pytest.mark.asyncio
    async def test_gracefully_handles_corrupt_stage_output(self):
        """A stage output with only unknown fields should not crash.

        Pydantic's model_validate() is permissive: if all model fields have
        defaults, a dict containing only extra/unknown keys still validates
        successfully (returning a model with all defaults).  The load should
        never raise; callers just get empty collections for the missing data.
        """
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        # dict with only unknown fields — Pydantic validates it with defaults
        corrupt = _make_result_doc("testcase", {"invalid_field": "garbage"})

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[corrupt])

            service = ExportService(_RUN_ID)
            # Should never raise regardless of the parsing outcome
            data = await service._load_run_data()

        # Pydantic accepted the dict with defaults → test_cases list is empty
        assert data["test_cases"] == []

    @pytest.mark.asyncio
    async def test_gracefully_handles_truly_invalid_stage_output(self):
        """A stage output whose values cannot be coerced must not propagate an
        exception — the stage result is silently dropped (None)."""
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        # Passing a non-dict triggers a Pydantic ValidationError on model_validate
        bad_result = _make_result_doc("testcase", None)  # type: ignore[arg-type]
        bad_result.output = "this-is-not-a-dict"

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[bad_result])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        # Parsing failed → testcase stays None → test_cases is empty list
        assert data["testcase"] is None
        assert data["test_cases"] == []

    @pytest.mark.asyncio
    async def test_empty_run_returns_zero_defaults(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            data = await service._load_run_data()

        assert data["test_cases"] == []
        assert data["exec_results"] == []
        assert data["root_causes"] == []
        assert data["requirements"] == []
        assert data["recommendations"] == []
        assert data["risks"] == []
        assert data["pass_rate"] == 0.0
        assert data["coverage_percentage"] == 0.0
        assert data["total_test_cases"] == 0
        assert data["executive_summary"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# ExportService.export_html()
# ─────────────────────────────────────────────────────────────────────────────


class TestExportServiceHTML:
    """Tests for ExportService.export_html()."""

    @pytest.mark.asyncio
    async def test_returns_bytes(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_valid_utf8_encoding(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        decoded = result.decode("utf-8")
        assert len(decoded) > 0

    @pytest.mark.asyncio
    async def test_html_contains_doctype(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        html = result.decode("utf-8")
        assert "<!DOCTYPE html>" in html.upper() or "<!doctype html>" in html.lower()

    @pytest.mark.asyncio
    async def test_html_contains_document_name(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        html = result.decode("utf-8")
        assert _DOC_NAME in html

    @pytest.mark.asyncio
    async def test_html_contains_run_id(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        html = result.decode("utf-8")
        assert _RUN_ID in html

    @pytest.mark.asyncio
    async def test_html_with_all_stages_contains_test_cases(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_docs = [
            _make_result_doc("ingestion", _INGESTION_OUTPUT),
            _make_result_doc("testcase", _TESTCASE_OUTPUT),
            _make_result_doc("execution", _EXECUTION_OUTPUT),
            _make_result_doc("reporting", _REPORT_OUTPUT),
        ]

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=result_docs)

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        html = result.decode("utf-8")
        assert "TC-001" in html
        assert "TC-002" in html
        assert "REQ-001" in html

    @pytest.mark.asyncio
    async def test_html_with_report_stage_contains_executive_summary(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_docs = [
            _make_result_doc("reporting", _REPORT_OUTPUT),
        ]

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=result_docs)

            service = ExportService(_RUN_ID)
            result = await service.export_html()

        html = result.decode("utf-8")
        assert "One authentication bug found" in html

    @pytest.mark.asyncio
    async def test_raises_value_error_for_missing_run(self):
        from app.services.export_service import ExportService

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=None)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService("missing-id")
            with pytest.raises(ValueError):
                await service.export_html()


# ─────────────────────────────────────────────────────────────────────────────
# ExportService.export_docx()
# ─────────────────────────────────────────────────────────────────────────────


class TestExportServiceDOCX:
    """Tests for ExportService.export_docx()."""

    @pytest.mark.asyncio
    async def test_returns_bytes(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_docx()

        assert isinstance(result, bytes)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_returns_valid_zip_docx(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_docx()

        # DOCX = ZIP with PK magic bytes
        assert result[:4] == b"PK\x03\x04"
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "word/document.xml" in zf.namelist()

    @pytest.mark.asyncio
    async def test_docx_with_all_stages(self):
        from app.services.export_service import ExportService

        run_doc = _make_run_doc()
        result_docs = [
            _make_result_doc("ingestion", _INGESTION_OUTPUT),
            _make_result_doc("testcase", _TESTCASE_OUTPUT),
            _make_result_doc("execution", _EXECUTION_OUTPUT),
            _make_result_doc("reporting", _REPORT_OUTPUT),
        ]

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=result_docs)

            service = ExportService(_RUN_ID)
            result = await service.export_docx()

        assert result[:4] == b"PK\x03\x04"
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            doc_xml = zf.read("word/document.xml").decode("utf-8")

        # Document name should appear in title page
        assert _DOC_NAME in doc_xml

    @pytest.mark.asyncio
    async def test_raises_value_error_for_missing_run(self):
        from app.services.export_service import ExportService

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=None)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService("missing-id")
            with pytest.raises(ValueError):
                await service.export_docx()

    @pytest.mark.asyncio
    async def test_docx_empty_run_no_crash(self):
        """An empty run (no stage results) should still produce valid DOCX."""
        from app.services.export_service import ExportService

        run_doc = _make_run_doc(status="running")

        with patch("app.services.export_service.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            mock_crud.get_pipeline_results = AsyncMock(return_value=[])

            service = ExportService(_RUN_ID)
            result = await service.export_docx()

        assert result[:4] == b"PK\x03\x04"


# ─────────────────────────────────────────────────────────────────────────────
# API endpoint tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture()
def client():
    """Provide a FastAPI TestClient with MongoDB initialisation skipped."""
    from unittest.mock import AsyncMock, patch

    from fastapi.testclient import TestClient

    # Patch the lifespan so MongoDB is never actually contacted
    with (
        patch("app.db.database.init_db", new_callable=AsyncMock),
        patch("app.db.database.close_db", new_callable=AsyncMock),
        patch("app.db.seed.seed_all", new_callable=AsyncMock),
        patch(
            "app.db.crud.recover_orphaned_runs", new_callable=AsyncMock, return_value=0
        ),
    ):
        from app.main import app

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestExportHTMLEndpoint:
    """Tests for GET /api/v1/pipeline/runs/{run_id}/export/html."""

    def test_404_for_unknown_run(self, client):
        missing_id = str(uuid.uuid4())
        with patch("app.api.v1.pipeline.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=None)
            resp = client.get(f"/api/v1/pipeline/runs/{missing_id}/export/html")
        assert resp.status_code == 404

    def test_200_returns_html_content_type(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/html")

        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]

    def test_200_response_has_content_disposition(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/html")

        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".html" in cd

    def test_200_response_body_is_valid_html(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/html")

        assert resp.status_code == 200
        body = resp.text
        assert "<!DOCTYPE html>" in body.upper() or "<!doctype html>" in body.lower()
        assert _DOC_NAME in body

    def test_filename_includes_run_id_prefix(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/html")

        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert _RUN_ID[:8] in cd


class TestExportDOCXEndpoint:
    """Tests for GET /api/v1/pipeline/runs/{run_id}/export/docx."""

    def test_404_for_unknown_run(self, client):
        missing_id = str(uuid.uuid4())
        with patch("app.api.v1.pipeline.crud") as mock_crud:
            mock_crud.get_pipeline_run = AsyncMock(return_value=None)
            resp = client.get(f"/api/v1/pipeline/runs/{missing_id}/export/docx")
        assert resp.status_code == 404

    def test_200_returns_docx_content_type(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/docx")

        assert resp.status_code == 200
        ct = resp.headers["content-type"]
        assert "wordprocessingml" in ct or "octet-stream" in ct

    def test_200_response_has_content_disposition(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/docx")

        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".docx" in cd

    def test_200_response_body_is_valid_docx(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/docx")

        assert resp.status_code == 200
        body = resp.content
        # Must start with ZIP magic bytes
        assert body[:4] == b"PK\x03\x04"

    def test_filename_includes_run_id_prefix(self, client):
        run_doc = _make_run_doc()

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=[])

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/docx")

        assert resp.status_code == 200
        cd = resp.headers.get("content-disposition", "")
        assert _RUN_ID[:8] in cd

    def test_docx_with_full_pipeline_data(self, client):
        """End-to-end: all four stage results → valid downloadable DOCX."""
        run_doc = _make_run_doc()
        result_docs = [
            _make_result_doc("ingestion", _INGESTION_OUTPUT),
            _make_result_doc("testcase", _TESTCASE_OUTPUT),
            _make_result_doc("execution", _EXECUTION_OUTPUT),
            _make_result_doc("reporting", _REPORT_OUTPUT),
        ]

        with (
            patch("app.api.v1.pipeline.crud") as mock_crud,
            patch("app.services.export_service.crud") as svc_crud,
        ):
            mock_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_run = AsyncMock(return_value=run_doc)
            svc_crud.get_pipeline_results = AsyncMock(return_value=result_docs)

            resp = client.get(f"/api/v1/pipeline/runs/{_RUN_ID}/export/docx")

        assert resp.status_code == 200
        body = resp.content
        assert body[:4] == b"PK\x03\x04"
        with zipfile.ZipFile(io.BytesIO(body)) as zf:
            assert "word/document.xml" in zf.namelist()
