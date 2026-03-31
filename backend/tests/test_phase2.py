from __future__ import annotations

"""
tests/test_phase2.py
────────────────────
Phase 2 test suite covering:
  - tools: text_chunker, document_parser (basic), api_runner, config_loader
  - schemas: pipeline_io models
  - crews: all four crews in mock / no-LLM mode
  - pipeline runner: end-to-end mock run

All tests run without a live LLM or real HTTP server.
Tests that require an actual file on disk use tmp_path fixtures.
"""

import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# In-memory DB fixture (shared across all tests)
# ─────────────────────────────────────────────────────────────────────────────
from app.db.database import Base
from app.db.models import AgentConfig, LLMProfile, PipelineRun
from app.db.seed import seed_all


@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture(scope="module")
def db_session(db_engine):
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    # Seed default data (18 agents + default LLM profile)
    seed_all(session)
    yield session
    session.close()


@pytest.fixture
def run_id() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Helper: minimal PipelineRun in DB
# ─────────────────────────────────────────────────────────────────────────────


def _make_pipeline_run(
    db: Session, rid: str, doc_name: str = "test.txt"
) -> PipelineRun:
    run = PipelineRun(
        id=rid,
        document_name=doc_name,
        document_path=f"/tmp/{doc_name}",
        status="pending",
        agent_statuses="{}",
    )
    db.add(run)
    db.commit()
    return run


# ═════════════════════════════════════════════════════════════════════════════
# 1.  schemas/pipeline_io
# ═════════════════════════════════════════════════════════════════════════════


class TestPipelineIOSchemas:
    def test_requirement_item_defaults(self):
        from app.schemas.pipeline_io import RequirementItem, RequirementType

        req = RequirementItem(title="Login", description="User can log in")
        assert req.id == "TBD"
        assert req.type == RequirementType.FUNCTIONAL
        assert req.priority == "medium"
        assert req.tags == []

    def test_ingestion_output_total_sync(self):
        from app.schemas.pipeline_io import IngestionOutput, RequirementItem

        items = [
            RequirementItem(id=f"REQ-{i:03d}", title=f"Req {i}", description="desc")
            for i in range(1, 4)
        ]
        out = IngestionOutput(requirements=items, document_name="spec.pdf")
        assert out.total_requirements == 3  # auto-synced by model_validator

    def test_coverage_summary_percentage(self):
        from app.schemas.pipeline_io import CoverageSummary

        cs = CoverageSummary(total_requirements=10, covered_requirements=8)
        assert cs.coverage_percentage == 80.0

    def test_execution_summary_pass_rate(self):
        from app.schemas.pipeline_io import ExecutionSummary

        es = ExecutionSummary(total=20, passed=15, failed=4, skipped=1, errors=0)
        assert es.pass_rate == 75.0

    def test_test_case_output_total_sync(self):
        from app.schemas.pipeline_io import TestCase, TestCaseOutput

        tcs = [
            TestCase(
                id=f"TC-{i:03d}",
                requirement_id="REQ-001",
                title=f"TC {i}",
            )
            for i in range(1, 6)
        ]
        out = TestCaseOutput(test_cases=tcs)
        assert out.total_test_cases == 5

    def test_pipeline_report_roundtrip(self):
        from app.schemas.pipeline_io import PipelineReport

        report = PipelineReport(
            coverage_percentage=75.0,
            executive_summary="All good",
            total_test_cases=10,
            pass_rate=80.0,
        )
        d = report.model_dump()
        assert d["coverage_percentage"] == 75.0
        assert d["pass_rate"] == 80.0
        assert "generated_at" in d


# ═════════════════════════════════════════════════════════════════════════════
# 2.  tools/text_chunker
# ═════════════════════════════════════════════════════════════════════════════


class TestTextChunker:
    def test_empty_input(self):
        from app.tools.text_chunker import chunk_text

        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        from app.tools.text_chunker import chunk_text

        text = "Hello world, this is a short text."
        result = chunk_text(text, chunk_size=500)
        assert result == [text]

    def test_long_text_multiple_chunks(self):
        from app.tools.text_chunker import chunk_text

        # Create text longer than chunk_size
        text = "The system must allow users to log in with valid credentials. " * 50
        chunks = chunk_text(text, chunk_size=200, overlap=20, min_chunk_size=10)
        assert len(chunks) > 1
        # Each chunk should be roughly <= chunk_size + some slack
        for chunk in chunks:
            assert len(chunk) <= 600  # allow generous upper bound

    def test_overlap_causes_coverage(self):
        from app.tools.text_chunker import chunk_text

        text = "ABCDEFGHIJ" * 100  # 1000 chars
        chunks = chunk_text(text, chunk_size=200, overlap=50, min_chunk_size=10)
        assert len(chunks) > 1
        # With overlap, adjacent chunks should share some content
        if len(chunks) >= 2:
            end_of_first = chunks[0][-30:]
            start_of_second = chunks[1][:50]
            # They should share at least some characters
            shared = set(end_of_first) & set(start_of_second)
            assert len(shared) > 0

    def test_invalid_overlap_raises(self):
        from app.tools.text_chunker import chunk_text

        with pytest.raises(ValueError, match="overlap"):
            chunk_text("some text", chunk_size=100, overlap=100)

    def test_chunk_text_rich_positions(self):
        from app.tools.text_chunker import chunk_text_rich

        text = "The quick brown fox jumps over the lazy dog. " * 30
        rich_chunks = chunk_text_rich(text, chunk_size=100, overlap=10)
        assert len(rich_chunks) > 1
        for c in rich_chunks:
            assert c.chunk_index >= 0
            assert c.char_start >= 0
            assert c.length > 0
            assert c.word_count > 0

    def test_estimate_token_count(self):
        from app.tools.text_chunker import estimate_token_count

        count = estimate_token_count("Hello world", chars_per_token=4.0)
        assert count >= 1

    def test_chunk_by_tokens(self):
        from app.tools.text_chunker import chunk_by_tokens

        text = "Requirements document. " * 200
        chunks = chunk_by_tokens(text, max_tokens=100, overlap_tokens=10)
        assert len(chunks) >= 1


# ═════════════════════════════════════════════════════════════════════════════
# 3.  tools/document_parser
# ═════════════════════════════════════════════════════════════════════════════


class TestDocumentParser:
    def test_parse_txt(self, tmp_path):
        from app.tools.document_parser import parse_document

        txt_file = tmp_path / "spec.txt"
        txt_file.write_text(
            "The system must allow user login.\nThe system shall log out users.",
            encoding="utf-8",
        )
        result = parse_document(txt_file)
        assert "system must allow user login" in result
        assert "log out users" in result

    def test_parse_markdown(self, tmp_path):
        from app.tools.document_parser import parse_document

        md_file = tmp_path / "spec.md"
        md_file.write_text(
            "# Requirements\n\n## Functional\n\n- User must be able to login",
            encoding="utf-8",
        )
        result = parse_document(md_file)
        assert "Requirements" in result
        assert "login" in result

    def test_parse_csv(self, tmp_path):
        from app.tools.document_parser import parse_document

        csv_file = tmp_path / "reqs.csv"
        csv_file.write_text(
            "id,title,description\nREQ-001,Login,User can login\nREQ-002,Logout,User can logout",
            encoding="utf-8",
        )
        result = parse_document(csv_file)
        assert "Login" in result
        assert "REQ-001" in result

    def test_unsupported_format_raises(self, tmp_path):
        from app.tools.document_parser import parse_document

        bad_file = tmp_path / "file.xyz"
        bad_file.write_text("content")
        with pytest.raises(ValueError, match="Unsupported"):
            parse_document(bad_file)

    def test_missing_file_raises(self):
        from app.tools.document_parser import parse_document

        with pytest.raises(FileNotFoundError):
            parse_document("/nonexistent/path/spec.pdf")

    def test_supported_extensions(self):
        from app.tools.document_parser import supported_extensions

        exts = supported_extensions()
        assert ".pdf" in exts
        assert ".docx" in exts
        assert ".txt" in exts


# ═════════════════════════════════════════════════════════════════════════════
# 4.  tools/api_runner
# ═════════════════════════════════════════════════════════════════════════════


class TestAPIRunner:
    def test_run_api_request_success(self):
        """Test a successful mock HTTP response."""
        from app.tools.api_runner import run_api_request

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/json"}
        mock_response.json.return_value = {"id": 1, "name": "Alice"}
        mock_response.text = '{"id": 1, "name": "Alice"}'

        with patch("app.tools.api_runner.httpx") as mock_httpx:
            mock_httpx.Client.return_value.__enter__ = MagicMock(
                return_value=MagicMock()
            )
            mock_httpx.Client.return_value.__exit__ = MagicMock(return_value=False)
            mock_client = mock_httpx.Client.return_value.__enter__.return_value
            mock_client.request.return_value = mock_response

            result = run_api_request(
                url="http://example.com/api/users",
                method="GET",
                expected_status=200,
            )

        assert isinstance(result, dict)
        assert "status_code" in result
        assert "success" in result
        assert "duration_ms" in result

    def test_run_api_request_no_httpx(self):
        """When httpx is not available, return error dict."""
        from app.tools.api_runner import _empty_result

        result = _empty_result("httpx not installed")
        assert result["success"] is False
        assert result["status_code"] is None
        assert "httpx not installed" in result["error"]

    def test_run_api_requests_batch_empty(self):
        """Empty batch returns empty list."""
        from app.tools.api_runner import run_api_requests_batch

        results = run_api_requests_batch([])
        assert results == []


# ═════════════════════════════════════════════════════════════════════════════
# 5.  tools/config_loader
# ═════════════════════════════════════════════════════════════════════════════


class TestConfigLoader:
    def test_load_env_config_defaults(self):
        from app.tools.config_loader import load_env_config

        config = load_env_config("default")
        assert config["environment"] == "default"
        assert "timeout_seconds" in config
        assert "headers" in config
        assert isinstance(config["headers"], dict)

    def test_load_env_config_from_env_vars(self):
        from app.tools.config_loader import load_env_config

        with patch.dict(os.environ, {"TEST_BASE_URL": "https://api.example.com"}):
            config = load_env_config("staging")
        assert config["base_url"] == "https://api.example.com"

    def test_load_env_config_from_file(self, tmp_path):
        from app.tools.config_loader import load_env_config

        cfg_file = tmp_path / "test_env.json"
        cfg_file.write_text(
            json.dumps(
                {
                    "base_url": "https://test.api.io",
                    "auth_token": "test-token-123",
                    "timeout_seconds": 60,
                }
            ),
            encoding="utf-8",
        )

        config = load_env_config("default", config_file=str(cfg_file))
        assert config["base_url"] == "https://test.api.io"
        assert config["timeout_seconds"] == 60

    def test_build_auth_headers_bearer(self):
        from app.tools.config_loader import build_auth_headers

        config = {"auth_token": "my-token", "auth_type": "Bearer"}
        headers = build_auth_headers(config)
        assert headers == {"Authorization": "Bearer my-token"}

    def test_build_auth_headers_no_token(self):
        from app.tools.config_loader import build_auth_headers

        config = {"auth_token": None, "auth_type": "Bearer"}
        headers = build_auth_headers(config)
        assert headers == {}

    def test_merge_headers(self):
        from app.tools.config_loader import merge_headers

        config = {
            "headers": {"X-Custom": "value"},
            "auth_token": "tok",
            "auth_type": "Bearer",
        }
        merged = merge_headers(config)
        assert "X-Custom" in merged
        assert "Authorization" in merged

    def test_post_process_strips_trailing_slash(self):
        from app.tools.config_loader import load_env_config

        with patch.dict(os.environ, {"TEST_BASE_URL": "https://api.example.com/"}):
            config = load_env_config("default")
        assert config.get("base_url", "").rstrip("/") == config.get("base_url", "")


# ═════════════════════════════════════════════════════════════════════════════
# 6.  crews/base_crew
# ═════════════════════════════════════════════════════════════════════════════


class TestBaseCrew:
    def test_parse_json_output_dict(self):
        from app.crews.base_crew import BaseCrew

        result = BaseCrew._parse_json_output({"key": "value"})
        assert result == {"key": "value"}

    def test_parse_json_output_list(self):
        from app.crews.base_crew import BaseCrew

        result = BaseCrew._parse_json_output([1, 2, 3])
        assert result == [1, 2, 3]

    def test_parse_json_output_valid_string(self):
        from app.crews.base_crew import BaseCrew

        result = BaseCrew._parse_json_output('{"a": 1, "b": [2, 3]}')
        assert result == {"a": 1, "b": [2, 3]}

    def test_parse_json_output_markdown_fenced(self):
        from app.crews.base_crew import BaseCrew

        raw = '```json\n{"name": "test", "value": 42}\n```'
        result = BaseCrew._parse_json_output(raw)
        assert result["name"] == "test"
        assert result["value"] == 42

    def test_parse_json_output_embedded_json(self):
        from app.crews.base_crew import BaseCrew

        raw = 'Here is the result: {"status": "ok", "count": 5} as requested.'
        result = BaseCrew._parse_json_output(raw)
        assert result.get("status") == "ok"

    def test_parse_json_output_fallback(self):
        from app.crews.base_crew import BaseCrew

        result = BaseCrew._parse_json_output("this is not json at all")
        assert "raw_output" in result

    def test_parse_json_output_crewai_output_obj(self):
        """Objects with a .raw attribute (e.g. CrewOutput) are handled."""
        from app.crews.base_crew import BaseCrew

        mock_output = MagicMock()
        mock_output.raw = '{"result": "done"}'
        result = BaseCrew._parse_json_output(mock_output)
        assert result.get("result") == "done"

    def test_emit_calls_callback(self, db_session, run_id):
        from app.crews.base_crew import BaseCrew

        received: list[tuple[str, dict]] = []

        def callback(event_type: str, data: dict) -> None:
            received.append((event_type, data))

        # Use a concrete subclass for testing
        class DummyCrew(BaseCrew):
            stage = "test_stage"

            def run(self, input_data):
                return {}

        crew = DummyCrew(db=db_session, run_id=run_id, progress_callback=callback)
        crew._emit("agent.started", {"agent_id": "test_agent"})

        assert len(received) == 1
        event_type, data = received[0]
        assert event_type == "agent.started"
        assert data["agent_id"] == "test_agent"
        assert data["run_id"] == run_id

    def test_mock_mode_from_settings(self, db_session, run_id):
        """Mock mode defaults to settings.MOCK_CREWS."""
        from app.crews.base_crew import BaseCrew

        class DummyCrew(BaseCrew):
            stage = "test"

            def run(self, input_data):
                return {}

        with patch("app.crews.base_crew.settings") as mock_settings:
            mock_settings.MOCK_CREWS = True
            crew = DummyCrew(db=db_session, run_id=run_id)
            assert crew._is_mock_mode() is True

    def test_mock_mode_explicit_override(self, db_session, run_id):
        from app.crews.base_crew import BaseCrew

        class DummyCrew(BaseCrew):
            stage = "test"

            def run(self, input_data):
                return {}

        crew = DummyCrew(db=db_session, run_id=run_id, mock_mode=True)
        assert crew._is_mock_mode() is True

        crew2 = DummyCrew(db=db_session, run_id=run_id, mock_mode=False)
        assert crew2._is_mock_mode() is False


# ═════════════════════════════════════════════════════════════════════════════
# 7.  crews/ingestion_crew
# ═════════════════════════════════════════════════════════════════════════════


class TestIngestionCrew:
    def test_run_with_txt_file(self, db_session, run_id, tmp_path):
        from app.crews.ingestion_crew import IngestionCrew

        txt_file = tmp_path / "spec.txt"
        txt_file.write_text(
            "The system must allow users to register with a username and password.\n"
            "Users shall be able to log in using their credentials.\n"
            "The application should log out inactive users after 30 minutes.\n"
            "Passwords must be at least 8 characters long and contain a number.\n",
            encoding="utf-8",
        )

        crew = IngestionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "file_path": str(txt_file),
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        assert isinstance(result, dict)
        assert "requirements" in result
        assert "document_name" in result
        assert result["document_name"] == "spec.txt"
        assert isinstance(result["requirements"], list)
        assert result["chunks_processed"] >= 1

    def test_run_assigns_sequential_ids(self, db_session, run_id, tmp_path):
        from app.crews.ingestion_crew import IngestionCrew

        txt_file = tmp_path / "reqs.txt"
        txt_file.write_text(
            "The system must support user authentication.\n"
            "Users shall be able to reset their password.\n"
            "The system must store passwords securely using hashing.\n",
            encoding="utf-8",
        )

        crew = IngestionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"file_path": str(txt_file), "mock_mode": True})

        reqs = result["requirements"]
        if reqs:
            # IDs should be REQ-001, REQ-002, ...
            for i, req in enumerate(reqs, start=1):
                assert req["id"] == f"REQ-{i:03d}", (
                    f"Expected REQ-{i:03d}, got {req['id']}"
                )

    def test_run_empty_file(self, db_session, run_id, tmp_path):
        from app.crews.ingestion_crew import IngestionCrew

        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("   \n  \n  ", encoding="utf-8")

        crew = IngestionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"file_path": str(empty_file), "mock_mode": True})

        assert result["total_requirements"] == 0
        assert result["requirements"] == []

    def test_run_file_not_found(self, db_session, run_id):
        from app.crews.ingestion_crew import IngestionCrew

        crew = IngestionCrew(db=db_session, run_id=run_id, mock_mode=True)
        with pytest.raises(FileNotFoundError):
            crew.run({"file_path": "/nonexistent/file.txt", "mock_mode": True})

    def test_progress_events_emitted(self, db_session, run_id, tmp_path):
        from app.crews.ingestion_crew import IngestionCrew

        txt_file = tmp_path / "spec2.txt"
        txt_file.write_text(
            "The system must allow login. Users shall be authenticated.",
            encoding="utf-8",
        )

        events: list[str] = []

        def callback(event_type: str, data: dict) -> None:
            events.append(event_type)

        crew = IngestionCrew(
            db=db_session, run_id=run_id, progress_callback=callback, mock_mode=True
        )
        crew.run({"file_path": str(txt_file), "mock_mode": True})

        assert "stage.started" in events
        assert "stage.completed" in events

    def test_deduplication(self):
        from app.crews.ingestion_crew import IngestionCrew, _normalise_for_dedup
        from app.schemas.pipeline_io import RequirementItem

        dup1 = RequirementItem(id="TBD", title="User Login", description="desc1")
        dup2 = RequirementItem(
            id="TBD", title="User Login!", description="desc2"
        )  # near-dup
        unique = RequirementItem(id="TBD", title="Password Reset", description="desc3")

        result = IngestionCrew._deduplicate([dup1, dup2, unique])
        # Should keep first occurrence of near-duplicate
        assert len(result) == 2
        titles = [r.title for r in result]
        assert "User Login" in titles
        assert "Password Reset" in titles

    def test_normalise_for_dedup(self):
        from app.crews.ingestion_crew import _normalise_for_dedup

        a = _normalise_for_dedup("User Login!")
        b = _normalise_for_dedup("User Login")
        assert a == b  # punctuation stripped → same normalised form

    def test_strip_code_fences(self):
        from app.crews.ingestion_crew import _strip_code_fences

        fenced = '```json\n{"requirements": []}\n```'
        result = _strip_code_fences(fenced)
        assert result == '{"requirements": []}'

        plain = '{"requirements": []}'
        assert _strip_code_fences(plain) == plain

    def test_extract_json_from_text(self):
        from app.crews.ingestion_crew import _extract_json_from_text

        text = 'Sure! Here is the JSON: {"requirements": [{"title": "Login"}]}'
        result = _extract_json_from_text(text)
        assert result is not None
        assert "requirements" in result

        no_json = "This has no JSON in it at all."
        assert _extract_json_from_text(no_json) is None


# ═════════════════════════════════════════════════════════════════════════════
# 8.  crews/testcase_crew (mock mode)
# ═════════════════════════════════════════════════════════════════════════════


SAMPLE_REQUIREMENTS = [
    {
        "id": "REQ-001",
        "title": "User Registration",
        "description": "Users must be able to register with email and password.",
        "type": "functional",
        "priority": "high",
        "tags": ["auth"],
        "notes": "",
    },
    {
        "id": "REQ-002",
        "title": "User Login",
        "description": "Registered users must be able to log in with their credentials.",
        "type": "functional",
        "priority": "high",
        "tags": ["auth"],
        "notes": "",
    },
    {
        "id": "REQ-003",
        "title": "Password Length Validation",
        "description": "Passwords must be at least 8 characters long.",
        "type": "constraint",
        "priority": "medium",
        "tags": ["validation"],
        "notes": "",
    },
]


class TestTestcaseCrew:
    def test_mock_run_basic(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        crew = TestcaseCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "requirements": SAMPLE_REQUIREMENTS,
                "document_name": "spec.txt",
            }
        )

        assert isinstance(result, dict)
        assert "test_cases" in result
        assert len(result["test_cases"]) > 0
        assert "total_test_cases" in result
        assert result["total_test_cases"] == len(result["test_cases"])

    def test_mock_generates_positive_and_negative(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        crew = TestcaseCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "requirements": SAMPLE_REQUIREMENTS,
                "document_name": "spec.txt",
            }
        )

        categories = {tc["category"] for tc in result["test_cases"]}
        # High-priority requirements should generate both positive and negative tests
        assert "positive" in categories
        assert "negative" in categories

    def test_mock_run_coverage_summary(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        crew = TestcaseCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "requirements": SAMPLE_REQUIREMENTS,
                "document_name": "spec.txt",
            }
        )

        cs = result["coverage_summary"]
        assert cs["total_requirements"] == len(SAMPLE_REQUIREMENTS)
        assert cs["covered_requirements"] <= cs["total_requirements"]
        assert 0.0 <= cs["coverage_percentage"] <= 100.0

    def test_mock_run_test_case_has_steps(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        crew = TestcaseCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "requirements": [SAMPLE_REQUIREMENTS[0]],
                "document_name": "spec.txt",
            }
        )

        assert len(result["test_cases"]) > 0
        first_tc = result["test_cases"][0]
        assert "steps" in first_tc
        assert len(first_tc["steps"]) > 0
        assert "action" in first_tc["steps"][0]

    def test_mock_run_has_automation_script(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        crew = TestcaseCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "requirements": [SAMPLE_REQUIREMENTS[0]],
                "document_name": "spec.txt",
            }
        )

        tc = result["test_cases"][0]
        assert tc.get("automation_script") is not None
        assert "def test_" in tc["automation_script"]

    def test_mock_run_empty_requirements(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        crew = TestcaseCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"requirements": [], "document_name": "empty.txt"})

        assert result["test_cases"] == []
        assert result["total_test_cases"] == 0

    def test_title_to_endpoint_slug(self):
        from app.crews.testcase_crew import _title_to_endpoint_slug

        slug = _title_to_endpoint_slug("User Registration")
        assert slug.startswith("/api/v1/")
        assert " " not in slug
        assert slug == slug.lower()

    def test_coerce_test_case_handles_missing_fields(self):
        from app.crews.testcase_crew import _coerce_test_case

        minimal = {"id": "TC-001", "requirement_id": "REQ-001", "title": "Test"}
        tc = _coerce_test_case(minimal, fallback_idx=1)
        assert tc.id == "TC-001"
        assert tc.test_type.value in ("api", "ui", "integration", "unit")
        assert tc.category.value in ("positive", "negative", "edge_case", "boundary")

    def test_progress_events_fired(self, db_session, run_id):
        from app.crews.testcase_crew import TestcaseCrew

        events: list[str] = []

        def cb(event_type: str, data: dict) -> None:
            events.append(event_type)

        crew = TestcaseCrew(
            db=db_session, run_id=run_id, mock_mode=True, progress_callback=cb
        )
        crew.run({"requirements": SAMPLE_REQUIREMENTS, "document_name": "spec.txt"})

        assert "stage.started" in events
        assert "stage.completed" in events


# ═════════════════════════════════════════════════════════════════════════════
# 9.  crews/execution_crew (mock mode)
# ═════════════════════════════════════════════════════════════════════════════


SAMPLE_TEST_CASES = [
    {
        "id": "TC-001",
        "requirement_id": "REQ-001",
        "title": "POST /users with valid data",
        "test_type": "api",
        "category": "positive",
        "priority": "high",
        "api_endpoint": "/api/v1/users",
        "http_method": "POST",
        "request_body": {"email": "alice@example.com", "password": "Pass1234"},
        "expected_status_code": 201,
    },
    {
        "id": "TC-002",
        "requirement_id": "REQ-001",
        "title": "POST /users with missing email",
        "test_type": "api",
        "category": "negative",
        "priority": "medium",
        "api_endpoint": "/api/v1/users",
        "http_method": "POST",
        "request_body": {"password": "Pass1234"},
        "expected_status_code": 400,
    },
    {
        "id": "TC-003",
        "requirement_id": "REQ-002",
        "title": "POST /auth/login with valid credentials",
        "test_type": "api",
        "category": "positive",
        "priority": "high",
        "api_endpoint": "/api/v1/auth/login",
        "http_method": "POST",
        "request_body": {"email": "alice@example.com", "password": "Pass1234"},
        "expected_status_code": 200,
    },
]


class TestExecutionCrew:
    def test_mock_run_returns_results(self, db_session, run_id):
        from app.crews.execution_crew import ExecutionCrew

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "test_cases": SAMPLE_TEST_CASES,
                "environment": "default",
            }
        )

        assert "results" in result
        assert len(result["results"]) == len(SAMPLE_TEST_CASES)

    def test_mock_run_all_test_cases_have_status(self, db_session, run_id):
        from app.crews.execution_crew import ExecutionCrew

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"test_cases": SAMPLE_TEST_CASES, "environment": "default"})

        valid_statuses = {"passed", "failed", "skipped", "error"}
        for r in result["results"]:
            assert r["status"] in valid_statuses

    def test_mock_run_summary_totals_match(self, db_session, run_id):
        from app.crews.execution_crew import ExecutionCrew

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"test_cases": SAMPLE_TEST_CASES, "environment": "default"})

        summary = result["summary"]
        total_from_summary = (
            summary["passed"]
            + summary["failed"]
            + summary["skipped"]
            + summary["errors"]
        )
        assert total_from_summary == summary["total"]
        assert summary["total"] == len(SAMPLE_TEST_CASES)

    def test_mock_run_high_priority_always_passes(self, db_session, run_id):
        """High-priority tests should always pass in mock mode."""
        from app.crews.execution_crew import ExecutionCrew

        high_prio_tcs = [tc for tc in SAMPLE_TEST_CASES if tc["priority"] == "high"]
        assert len(high_prio_tcs) > 0

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"test_cases": high_prio_tcs, "environment": "default"})

        for r in result["results"]:
            assert r["status"] == "passed", (
                f"High-priority test {r['test_case_id']} should always pass in mock mode"
            )

    def test_mock_run_includes_timing(self, db_session, run_id):
        from app.crews.execution_crew import ExecutionCrew

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"test_cases": SAMPLE_TEST_CASES, "environment": "default"})

        assert "timing_stats" in result
        ts = result["timing_stats"]
        assert ts["min_ms"] >= 0
        assert ts["max_ms"] >= ts["min_ms"]

    def test_mock_run_empty_test_cases(self, db_session, run_id):
        from app.crews.execution_crew import ExecutionCrew

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run({"test_cases": [], "environment": "default"})

        assert result["results"] == []
        assert result["summary"]["total"] == 0

    def test_mock_run_deterministic(self, db_session, run_id):
        """Same input should always produce the same statuses (hash-based)."""
        from app.crews.execution_crew import ExecutionCrew

        crew = ExecutionCrew(db=db_session, run_id=run_id, mock_mode=True)
        result1 = crew.run({"test_cases": SAMPLE_TEST_CASES, "environment": "default"})

        new_run_id = str(uuid.uuid4())
        crew2 = ExecutionCrew(db=db_session, run_id=new_run_id, mock_mode=True)
        result2 = crew2.run({"test_cases": SAMPLE_TEST_CASES, "environment": "default"})

        statuses1 = [r["status"] for r in result1["results"]]
        statuses2 = [r["status"] for r in result2["results"]]
        assert statuses1 == statuses2

    def test_progress_events_fired(self, db_session, run_id):
        from app.crews.execution_crew import ExecutionCrew

        events: list[str] = []

        def cb(event_type: str, data: dict) -> None:
            events.append(event_type)

        crew = ExecutionCrew(
            db=db_session, run_id=run_id, mock_mode=True, progress_callback=cb
        )
        crew.run({"test_cases": SAMPLE_TEST_CASES[:1], "environment": "default"})

        assert "stage.started" in events
        assert "stage.completed" in events


# ═════════════════════════════════════════════════════════════════════════════
# 10.  crews/reporting_crew (mock mode)
# ═════════════════════════════════════════════════════════════════════════════


SAMPLE_EXEC_RESULTS = [
    {
        "test_case_id": "TC-001",
        "status": "passed",
        "duration_ms": 120.0,
        "actual_result": "HTTP 201 Created",
        "actual_status_code": 201,
        "error_message": None,
        "logs": ["PASSED"],
    },
    {
        "test_case_id": "TC-002",
        "status": "failed",
        "duration_ms": 80.0,
        "actual_result": "HTTP 500 Internal Server Error",
        "actual_status_code": 500,
        "error_message": "Expected 400, got 500",
        "logs": ["FAILED: status mismatch"],
    },
    {
        "test_case_id": "TC-003",
        "status": "passed",
        "duration_ms": 95.0,
        "actual_result": "HTTP 200 OK",
        "actual_status_code": 200,
        "error_message": None,
        "logs": ["PASSED"],
    },
]


class TestReportingCrew:
    def test_mock_run_returns_report(self, db_session, run_id):
        from app.crews.reporting_crew import ReportingCrew

        crew = ReportingCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "test_cases_json": SAMPLE_TEST_CASES,
                "execution_results_json": SAMPLE_EXEC_RESULTS,
                "requirements_json": SAMPLE_REQUIREMENTS,
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        assert isinstance(result, dict)
        assert "coverage_percentage" in result
        assert "executive_summary" in result
        assert "recommendations" in result
        assert "risk_items" in result
        assert "metrics" in result
        assert "generated_at" in result

    def test_mock_coverage_percentage(self, db_session, run_id):
        from app.crews.reporting_crew import ReportingCrew

        crew = ReportingCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "test_cases_json": SAMPLE_TEST_CASES,
                "execution_results_json": SAMPLE_EXEC_RESULTS,
                "requirements_json": SAMPLE_REQUIREMENTS,
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        cov = result["coverage_percentage"]
        assert 0.0 <= cov <= 100.0

    def test_mock_root_cause_analysis_for_failures(self, db_session, run_id):
        from app.crews.reporting_crew import ReportingCrew

        crew = ReportingCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "test_cases_json": SAMPLE_TEST_CASES,
                "execution_results_json": SAMPLE_EXEC_RESULTS,
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        # TC-002 failed — there should be at least one root cause entry
        rca = result.get("root_cause_analysis", [])
        assert isinstance(rca, list)
        # At least one entry should mention TC-002 in affected_tests
        tc002_mentioned = any(
            "TC-002" in entry.get("affected_tests", []) for entry in rca
        )
        assert tc002_mentioned

    def test_mock_pass_rate_correct(self, db_session, run_id):
        from app.crews.reporting_crew import ReportingCrew

        crew = ReportingCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "test_cases_json": SAMPLE_TEST_CASES,
                "execution_results_json": SAMPLE_EXEC_RESULTS,
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        # 2 passed out of 3 = 66.7%
        assert result["pass_rate"] == pytest.approx(66.7, abs=0.2)

    def test_mock_run_no_failures_is_fine(self, db_session, run_id):
        from app.crews.reporting_crew import ReportingCrew

        all_passed = [
            {**r, "status": "passed", "error_message": None}
            for r in SAMPLE_EXEC_RESULTS
        ]

        crew = ReportingCrew(db=db_session, run_id=run_id, mock_mode=True)
        result = crew.run(
            {
                "test_cases_json": SAMPLE_TEST_CASES,
                "execution_results_json": all_passed,
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        assert result["root_cause_analysis"] == []
        assert result["pass_rate"] == 100.0

    def test_progress_events_fired(self, db_session, run_id):
        from app.crews.reporting_crew import ReportingCrew

        events: list[str] = []

        def cb(event_type: str, data: dict) -> None:
            events.append(event_type)

        crew = ReportingCrew(
            db=db_session, run_id=run_id, mock_mode=True, progress_callback=cb
        )
        crew.run(
            {
                "test_cases_json": SAMPLE_TEST_CASES,
                "execution_results_json": SAMPLE_EXEC_RESULTS,
                "document_name": "spec.txt",
                "mock_mode": True,
            }
        )

        assert "stage.started" in events
        assert "stage.completed" in events
        assert "agent.started" in events
        assert "agent.completed" in events


# ═════════════════════════════════════════════════════════════════════════════
# 11.  core/pipeline_runner (end-to-end mock)
# ═════════════════════════════════════════════════════════════════════════════


class TestPipelineRunner:
    def test_full_mock_pipeline(self, db_session, tmp_path):
        """Run the full 4-stage pipeline in mock mode with a real text file."""
        from app.core.pipeline_runner import PipelineRunner

        txt_file = tmp_path / "spec.txt"
        txt_file.write_text(
            "The system must allow user registration with email and password.\n"
            "Users shall be able to log in using their registered credentials.\n"
            "The system must validate that passwords are at least 8 characters long.\n"
            "Users should be able to reset their password via email.\n",
            encoding="utf-8",
        )

        rid = str(uuid.uuid4())
        _make_pipeline_run(db_session, rid, "spec.txt")

        runner = PipelineRunner(
            db=db_session,
            run_id=rid,
            mock_mode=True,
        )
        result = runner.run(file_path=txt_file, document_name="spec.txt")

        assert result["status"] == "completed"
        assert result["error"] is None
        assert result["ingestion"] is not None
        assert result["testcase"] is not None
        assert result["execution"] is not None
        assert result["report"] is not None
        assert result["duration_seconds"] >= 0

    def test_pipeline_metrics(self, db_session, tmp_path):
        from app.core.pipeline_runner import PipelineRunner

        txt_file = tmp_path / "spec2.txt"
        txt_file.write_text(
            "The system must allow user registration.\nUsers must be able to log in.\n",
            encoding="utf-8",
        )

        rid = str(uuid.uuid4())
        _make_pipeline_run(db_session, rid, "spec2.txt")

        runner = PipelineRunner(db=db_session, run_id=rid, mock_mode=True)
        result = runner.run(file_path=txt_file)

        metrics = result["metrics"]
        assert "requirements_count" in metrics
        assert "test_cases_count" in metrics
        assert "pass_rate" in metrics
        assert "coverage_percentage" in metrics

    def test_pipeline_progress_events(self, db_session, tmp_path):
        from app.core.pipeline_runner import PipelineRunner

        txt_file = tmp_path / "spec3.txt"
        txt_file.write_text("The system must allow user login.", encoding="utf-8")

        rid = str(uuid.uuid4())
        _make_pipeline_run(db_session, rid, "spec3.txt")

        events: list[str] = []

        def broadcaster(event_type: str, data: dict) -> None:
            events.append(event_type)

        runner = PipelineRunner(
            db=db_session,
            run_id=rid,
            mock_mode=True,
            ws_broadcaster=broadcaster,
        )
        runner.run(file_path=txt_file)

        # Check that key lifecycle events were emitted
        assert "run.started" in events
        assert "run.completed" in events
        assert "stage.started" in events
        assert "stage.completed" in events

    def test_pipeline_skip_execution(self, db_session, tmp_path):
        from app.core.pipeline_runner import PipelineRunner

        txt_file = tmp_path / "spec4.txt"
        txt_file.write_text(
            "The system must allow user registration.", encoding="utf-8"
        )

        rid = str(uuid.uuid4())
        _make_pipeline_run(db_session, rid, "spec4.txt")

        runner = PipelineRunner(db=db_session, run_id=rid, mock_mode=True)
        result = runner.run(file_path=txt_file, skip_execution=True)

        assert result["status"] == "completed"
        # When skip_execution=True, execution and report stages are not run
        assert result["execution"] is None
        assert result["report"] is None
        # Ingestion and testcase should still be present
        assert result["ingestion"] is not None
        assert result["testcase"] is not None

    def test_pipeline_file_not_found(self, db_session):
        from app.core.pipeline_runner import PipelineRunner

        rid = str(uuid.uuid4())
        runner = PipelineRunner(db=db_session, run_id=rid, mock_mode=True)

        with pytest.raises(FileNotFoundError):
            runner.run(file_path="/nonexistent/path/spec.pdf")

    def test_pipeline_db_status_updated(self, db_session, tmp_path):
        """Verify that the PipelineRun.status is updated to 'completed' in DB."""
        from app.core.pipeline_runner import PipelineRunner

        txt_file = tmp_path / "spec5.txt"
        txt_file.write_text(
            "The system must handle user authentication.", encoding="utf-8"
        )

        rid = str(uuid.uuid4())
        _make_pipeline_run(db_session, rid, "spec5.txt")

        runner = PipelineRunner(db=db_session, run_id=rid, mock_mode=True)
        runner.run(file_path=txt_file)

        db_session.expire_all()
        run = db_session.get(PipelineRun, rid)
        assert run is not None
        assert run.status == "completed"
        assert run.finished_at is not None

    def test_pipeline_results_persisted(self, db_session, tmp_path):
        """Verify that PipelineResult rows are created in DB for each stage."""
        from app.core.pipeline_runner import PipelineRunner
        from app.db.crud import get_pipeline_results

        txt_file = tmp_path / "spec6.txt"
        txt_file.write_text(
            "The system must allow secure user login.", encoding="utf-8"
        )

        rid = str(uuid.uuid4())
        _make_pipeline_run(db_session, rid, "spec6.txt")

        runner = PipelineRunner(db=db_session, run_id=rid, mock_mode=True)
        runner.run(file_path=txt_file)

        results = get_pipeline_results(db_session, rid)
        stages_with_results = {r.stage for r in results}

        # At minimum, ingestion and testcase should have results
        assert "ingestion" in stages_with_results
        assert "testcase" in stages_with_results

    def test_pipeline_compute_summary_metrics(self, db_session):
        from app.core.pipeline_runner import PipelineRunner

        rid = str(uuid.uuid4())
        runner = PipelineRunner(db=db_session, run_id=rid, mock_mode=True)

        # Manually set stage outputs to test metric computation
        runner._ingestion_output = {
            "requirements": [{"id": "REQ-001"}, {"id": "REQ-002"}]
        }
        runner._testcase_output = {
            "test_cases": [{"id": f"TC-{i:03d}"} for i in range(5)],
            "total_test_cases": 5,
        }
        runner._execution_output = {
            "summary": {
                "total": 5,
                "passed": 4,
                "failed": 1,
                "skipped": 0,
                "errors": 0,
                "pass_rate": 80.0,
            }
        }
        runner._report_output = {"coverage_percentage": 90.0}

        metrics = runner._compute_summary_metrics()

        assert metrics["requirements_count"] == 2
        assert metrics["test_cases_count"] == 5
        assert metrics["pass_rate"] == 80.0
        assert metrics["coverage_percentage"] == 90.0


# ═════════════════════════════════════════════════════════════════════════════
# 12.  tasks/ (import-only tests — verify factory functions are importable)
# ═════════════════════════════════════════════════════════════════════════════


class TestTaskImports:
    """
    Light-weight smoke tests that verify the task factory functions are
    importable and callable without crewai installed.
    The _require_crewai() guard should raise ImportError (not AttributeError
    or SyntaxError) when crewai is absent.
    """

    def _assert_raises_import_error_or_crewai_task(self, fn, *args, **kwargs):
        """Helper: either crewai is installed (returns Task) or raises ImportError."""
        try:
            result = fn(*args, **kwargs)
            # If crewai is installed, result should be a Task-like object
            assert result is not None
        except ImportError:
            pass  # Expected when crewai is not installed

    def test_testcase_tasks_importable(self):
        from app.tasks import testcase_tasks  # noqa: F401

        assert hasattr(testcase_tasks, "make_requirement_analyzer_task")
        assert hasattr(testcase_tasks, "make_report_pre_task")

    def test_execution_tasks_importable(self):
        from app.tasks import execution_tasks  # noqa: F401

        assert hasattr(execution_tasks, "make_execution_orchestrator_task")
        assert hasattr(execution_tasks, "make_result_store_task")

    def test_reporting_tasks_importable(self):
        from app.tasks import reporting_tasks  # noqa: F401

        assert hasattr(reporting_tasks, "make_coverage_analyzer_task")
        assert hasattr(reporting_tasks, "make_report_generator_task")

    def test_compact_json_truncation(self):
        from app.tasks.testcase_tasks import _compact_json

        large_list = [{"id": i} for i in range(100)]
        result = _compact_json(large_list, max_items=5)
        assert "omitted for brevity" in result

    def test_compact_json_small_list(self):
        from app.tasks.testcase_tasks import _compact_json

        small = [{"id": 1}, {"id": 2}]
        result = _compact_json(small, max_items=10)
        parsed = json.loads(result)
        assert len(parsed) == 2
