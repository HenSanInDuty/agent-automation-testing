"""
Auto-AT crews package.

Exposes the four pipeline crews:
    IngestionCrew   – pure-Python document parsing pipeline (no CrewAI agents)
    TestcaseCrew    – CrewAI Sequential crew (10 agents)
    ExecutionCrew   – CrewAI Sequential crew (5 agents, mock-capable)
    ReportingCrew   – CrewAI Sequential crew (3 agents)

Each crew accepts a progress_callback so the pipeline runner can stream
WebSocket events without the crew knowing about HTTP or WebSocket details.
"""

from app.crews.api_test_case_crew import ApiTestCaseCrew
from app.crews.api_test_runner_crew import ApiTestRunnerCrew
from app.crews.base_crew import BaseCrew, ProgressCallback
from app.crews.execution_crew import ExecutionCrew
from app.crews.ingestion_crew import IngestionCrew
from app.crews.export_crew import ExportCrew
from app.crews.md_spec_verifier_crew import MDSpecVerifierCrew
from app.crews.report_verifier_crew import ReportVerifierCrew
from app.crews.reporting_crew import ReportingCrew
from app.crews.test_level_classifier_crew import TestLevelClassifierCrew
from app.crews.testcase_crew import TestcaseCrew

__all__ = [
    "BaseCrew",
    "ProgressCallback",
    "ApiTestCaseCrew",
    "ApiTestRunnerCrew",
    "IngestionCrew",
    "MDSpecVerifierCrew",
    "TestLevelClassifierCrew",
    "ExportCrew",
    "ReportVerifierCrew",
    "TestcaseCrew",
    "ExecutionCrew",
    "ReportingCrew",
]
