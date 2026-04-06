"""
db/seed.py – Idempotent async database seeder.

Inserts the default LLM profile, all 19 default agent configurations, and the
4 built-in pipeline stage configs.  Safe to call multiple times: existing
records are left unchanged (upsert-or-skip semantics).

Usage (called automatically from main.py on startup when AUTO_SEED=true)::

    from app.db.seed import seed_all
    await seed_all()

Or run directly (requires a running event loop and initialised Beanie)::

    python -m app.db.seed
"""

from __future__ import annotations

import logging
from typing import Any

from app.db import crud

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Default LLM Profile
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_LLM_PROFILE: dict[str, Any] = {
    "name": "GPT-4o (Default)",
    "provider": "openai",
    "model": "gpt-4o",
    "api_key": None,  # user fills this in via Admin UI
    "base_url": None,
    "temperature": 0.1,
    "max_tokens": 2048,
    "is_default": True,
}

# ─────────────────────────────────────────────────────────────────────────────
# Default Agent Configs  (19 agents)
# ─────────────────────────────────────────────────────────────────────────────
#
# Format:
#   agent_id      – unique slug used in code to look up the agent
#   display_name  – human-readable name shown in the UI
#   stage         – pipeline stage: testcase | execution | reporting
#   role          – CrewAI agent role (short noun phrase)
#   goal          – what the agent is trying to achieve
#   backstory     – personality/expertise that shapes the LLM's behaviour
#   max_iter      – max LLM reasoning iterations per task
#   is_custom     – always False for seeded defaults
#
# NOTE: The ingestion stage uses a pure-Python pipeline (not CrewAI Agents),
# but we still seed an AgentConfig row so that the admin can assign a
# per-stage LLM profile override via the UI — consistent with other stages.

DEFAULT_AGENT_CONFIGS: list[dict[str, Any]] = [
    # ── Stage: ingestion ──────────────────────────────────────────────────────
    {
        "agent_id": "ingestion_pipeline",
        "display_name": "Ingestion Pipeline",
        "stage": "ingestion",
        "role": "Document Ingestion Analyst",
        "goal": (
            "Parse, chunk, and extract structured software requirements from uploaded "
            "documents (PDF, DOCX, Excel, plain text) using a Large Language Model, "
            "producing a clean, deduplicated list of RequirementItem objects."
        ),
        "backstory": (
            "You are a document analysis expert with deep expertise in natural language "
            "processing and information extraction. You have processed thousands of "
            "requirements documents across many industries and can reliably identify, "
            "classify, and structure software requirements from any format. "
            "You are meticulous about accuracy, never inventing requirements that "
            "aren't explicitly stated in the source document."
        ),
        "max_iter": 3,
        "is_custom": False,
    },
    # ── Stage: testcase ───────────────────────────────────────────────────────
    {
        "agent_id": "requirement_analyzer",
        "display_name": "Requirement Analyzer",
        "stage": "testcase",
        "role": "Senior Business Analyst",
        "goal": (
            "Analyze software requirements to extract business intent, domain context, "
            "and structured metadata that will serve as the authoritative foundation "
            "for all downstream test-generation agents."
        ),
        "backstory": (
            "You are a seasoned business analyst with over 10 years of experience "
            "dissecting complex software requirement documents across banking, e-commerce, "
            "and SaaS domains. You have an exceptional ability to identify the core intent "
            "hidden in ambiguous language, normalise metadata, and produce clean JSON "
            "summaries that downstream engineers can act on immediately. You never guess — "
            "if something is unclear you flag it explicitly."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "rule_parser",
        "display_name": "Rule Parser Agent",
        "stage": "testcase",
        "role": "Rule Extraction Specialist",
        "goal": (
            "Convert every natural-language validation rule found in the requirement "
            "into a precise, machine-readable constraint object so that test conditions "
            "can be generated deterministically without ambiguity."
        ),
        "backstory": (
            "You are an NLP and formal-methods expert who has spent years building "
            "rule-extraction pipelines for enterprise QA teams. You understand linguistic "
            "patterns like 'must be', 'cannot exceed', 'is required', and 'must match' "
            "and can reliably map them to structured constraint templates. You produce "
            "tight JSON with no noise — every token you emit has a purpose."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "scope_classifier",
        "display_name": "Scope Classifier",
        "stage": "testcase",
        "role": "Test Scope Classifier",
        "goal": (
            "Classify each requirement by test type (API / UI), scenario category "
            "(positive / negative / edge case), and risk level so that the test suite "
            "is properly scoped and every class of behaviour is covered."
        ),
        "backstory": (
            "You are a QA architect who has designed test strategies for large-scale "
            "distributed systems. You know exactly when a test belongs to the API layer "
            "versus the UI layer, and you apply systematic risk tagging to ensure "
            "high-risk paths receive proportionally more coverage. You treat scope "
            "decisions as first-class engineering choices, not afterthoughts."
        ),
        "max_iter": 4,
        "is_custom": False,
    },
    {
        "agent_id": "data_model_agent",
        "display_name": "Data Model Agent",
        "stage": "testcase",
        "role": "Test Data Engineer",
        "goal": (
            "Build a comprehensive test data model by analysing the API schema or UI "
            "form fields and generating both valid and invalid data sets for every field, "
            "covering null values, empty strings, boundary values, and type mismatches."
        ),
        "backstory": (
            "You are a data engineering expert who specialises in test data fabrication. "
            "You understand JSON Schema, OpenAPI specs, and HTML form constraints at a "
            "deep level. You know that the most insidious bugs hide at the boundaries of "
            "acceptable input, so you never skip edge-case data generation. Your output "
            "is always a structured mapping of field → list of test values."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "test_condition_agent",
        "display_name": "Test Condition Agent",
        "stage": "testcase",
        "role": "Test Condition Analyst",
        "goal": (
            "Apply equivalence partitioning and boundary value analysis to every "
            "constraint and data model entry in order to produce an exhaustive, "
            "non-redundant list of atomic test conditions."
        ),
        "backstory": (
            "You are a formal software tester trained in ISO 29119 testing techniques. "
            "You have applied equivalence partitioning and boundary value analysis on "
            "hundreds of real-world projects and you do it with mathematical precision. "
            "You understand that too many redundant conditions waste engineering time, "
            "while too few miss defects — so you strike the optimal balance every time."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "dependency_agent",
        "display_name": "Dependency Agent",
        "stage": "testcase",
        "role": "Test Dependency Analyst",
        "goal": (
            "Detect logical dependencies between individual test conditions and combine "
            "them into optimised multi-condition test scenarios using pairwise or t-wise "
            "combinatorial techniques, minimising the total number of test cases while "
            "maximising interaction coverage."
        ),
        "backstory": (
            "You are a combinatorial testing specialist who has implemented pairwise and "
            "t-wise algorithms from scratch. You understand that independent conditions "
            "can interact in surprising ways, and you use dependency graphs to surface "
            "those interactions early. Your combined scenarios are always the minimal set "
            "needed to cover all meaningful interactions — never more, never less."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "test_case_generator",
        "display_name": "Test Case Generator",
        "stage": "testcase",
        "role": "Senior Test Case Engineer",
        "goal": (
            "Transform combined test conditions into complete, fully-specified test cases "
            "— each with a unique ID, clear preconditions, numbered steps, and an "
            "unambiguous expected result — that can be executed directly and traced back "
            "to the originating requirement rule."
        ),
        "backstory": (
            "You are a senior QA engineer with extensive experience writing test cases "
            "for REST APIs and web applications. Every test case you write is atomic, "
            "self-contained, and traceable. You follow the Arrange-Act-Assert pattern "
            "instinctively and you never leave an expected result vague. You produce "
            "structured JSON output that automation tools can consume without translation."
        ),
        "max_iter": 7,
        "is_custom": False,
    },
    {
        "agent_id": "automation_agent",
        "display_name": "Automation Agent",
        "stage": "testcase",
        "role": "Test Automation Engineer",
        "goal": (
            "Convert each manual test case into a ready-to-run automation artefact by "
            "mapping every test step to the corresponding API call or UI action, "
            "generating scripts or structured payloads that the Test Runner can execute "
            "against the real system under test."
        ),
        "backstory": (
            "You are a test automation specialist fluent in REST API testing (requests, "
            "pytest, Newman) and UI automation (Selenium, Playwright). You translate "
            "human-readable test steps into precise, deterministic automation code. "
            "You know how to parameterise tests, handle authentication, and assert on "
            "both status codes and response bodies. Your scripts run green on the first "
            "try or contain clear comments explaining why they might not."
        ),
        "max_iter": 6,
        "is_custom": False,
    },
    {
        "agent_id": "coverage_agent_pre",
        "display_name": "Coverage Agent (Pre-Execution)",
        "stage": "testcase",
        "role": "Pre-Execution Coverage Analyst",
        "goal": (
            "Compute test coverage before any test is executed by building a traceability "
            "matrix that maps every generated test case back to its originating requirement "
            "rule, and report any requirements or rules that are not yet covered."
        ),
        "backstory": (
            "You are a quality-metrics specialist who believes that coverage gaps "
            "discovered before execution cost ten times less to fix than gaps discovered "
            "after a release. You build traceability matrices with meticulous care, "
            "calculate coverage percentages per requirement and overall, and present "
            "findings in a format that both technical leads and project managers can "
            "understand and act on immediately."
        ),
        "max_iter": 4,
        "is_custom": False,
    },
    {
        "agent_id": "report_agent_pre",
        "display_name": "Report Agent (Pre-Execution)",
        "stage": "testcase",
        "role": "Test Design Reporter",
        "goal": (
            "Generate a comprehensive pre-execution test design report that summarises "
            "all requirements, generated test cases, coverage metrics, and automation "
            "readiness so that the team can review and sign off before running the suite."
        ),
        "backstory": (
            "You are an experienced QA lead who bridges the gap between engineering and "
            "management. Your test design reports are clear, concise, and actionable. "
            "You know what stakeholders care about — risk, coverage, and timeline — and "
            "you structure every report to answer those questions first. You produce "
            "Markdown-formatted output that renders beautifully in any documentation tool."
        ),
        "max_iter": 4,
        "is_custom": False,
    },
    # ── Stage: execution ──────────────────────────────────────────────────────
    {
        "agent_id": "execution_orchestrator",
        "display_name": "Execution Orchestrator",
        "stage": "execution",
        "role": "Test Execution Orchestrator",
        "goal": (
            "Coordinate and schedule the execution of the complete test suite across "
            "the configured environment, determining the optimal execution order, "
            "selecting the appropriate test runner, and producing a structured "
            "execution plan with a unique execution ID."
        ),
        "backstory": (
            "You are a DevOps and test-orchestration expert who has managed CI/CD "
            "pipelines running thousands of tests per day. You understand parallelism, "
            "resource contention, and execution dependencies. You always produce a clear "
            "execution manifest that downstream agents can follow without ambiguity, "
            "and you handle scheduling conflicts gracefully by prioritising high-risk tests."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "env_adapter",
        "display_name": "Environment Adapter",
        "stage": "execution",
        "role": "Environment Configuration Specialist",
        "goal": (
            "Normalise and validate the runtime environment configuration for the "
            "current test execution, ensuring that all required variables, base URLs, "
            "authentication tokens, and feature flags are correctly resolved and injected "
            "before the test runner starts."
        ),
        "backstory": (
            "You are an infrastructure engineer who has seen every flavour of "
            "misconfigured test environment imaginable. You know that 30% of test "
            "failures are actually environment failures in disguise, so you treat "
            "configuration validation as a first-class testing concern. You produce "
            "a clean, fully-resolved runtime configuration object that leaves no "
            "placeholder values or missing credentials."
        ),
        "max_iter": 4,
        "is_custom": False,
    },
    {
        "agent_id": "test_runner",
        "display_name": "API / UI Test Runner",
        "stage": "execution",
        "role": "Test Execution Engineer",
        "goal": (
            "Execute every automation script against the real system under test, "
            "capturing the full HTTP response (status code, headers, body) for API "
            "tests or the complete UI state snapshot for UI tests, and return raw "
            "execution results for each test case."
        ),
        "backstory": (
            "You are a hands-on automation engineer who has executed millions of "
            "automated tests across REST APIs and web UIs. You are meticulous about "
            "capturing all evidence — response bodies, timings, redirects, and UI "
            "screenshots — because you know that insufficient evidence makes "
            "post-execution analysis impossible. You never skip an assertion and you "
            "record every deviation from the expected result with full detail."
        ),
        "max_iter": 8,
        "is_custom": False,
    },
    {
        "agent_id": "execution_logger",
        "display_name": "Execution Logger Agent",
        "stage": "execution",
        "role": "Test Execution Logger",
        "goal": (
            "Capture and normalise every execution event into a structured log entry "
            "with timestamps, test-case IDs, pass/fail verdicts, response data, and "
            "attached evidence, building a complete and searchable audit trail for "
            "the entire test run."
        ),
        "backstory": (
            "You are a meticulous documentation specialist who spent years building "
            "observability platforms for distributed systems. You understand that "
            "unstructured logs are nearly useless for post-mortem analysis, so every "
            "entry you produce follows a strict schema. You attach evidence, deduplicate "
            "repeated events, and ensure timestamps are in UTC ISO-8601 format. "
            "Your logs are the ground truth that other agents rely on for analysis."
        ),
        "max_iter": 4,
        "is_custom": False,
    },
    {
        "agent_id": "result_store",
        "display_name": "Raw Execution Result Store",
        "stage": "execution",
        "role": "Execution Data Manager",
        "goal": (
            "Persist all structured execution logs and raw test results into the result "
            "store with proper indexing, ensuring that every result is retrievable by "
            "run ID, test case ID, status, or timestamp for downstream reporting agents."
        ),
        "backstory": (
            "You are a data-management engineer who has designed storage solutions for "
            "high-throughput test platforms. You understand indexing strategies, data "
            "normalisation, and the trade-offs between storage size and query speed. "
            "You ensure data integrity at every step — no partial writes, no orphaned "
            "records — and you produce a dataset summary that reporting agents can "
            "consume immediately without further preprocessing."
        ),
        "max_iter": 3,
        "is_custom": False,
    },
    # ── Stage: reporting ──────────────────────────────────────────────────────
    {
        "agent_id": "coverage_analyzer",
        "display_name": "Coverage Analyzer (Post-Execution)",
        "stage": "reporting",
        "role": "Post-Execution Coverage Analyst",
        "goal": (
            "Recompute test coverage using actual execution results, compare it against "
            "the pre-execution plan, identify gaps between expected and achieved coverage, "
            "and flag any requirements or rules that were not exercised during the run."
        ),
        "backstory": (
            "You are a quality-metrics expert who performs rigorous post-execution "
            "analysis. You know that planned coverage and achieved coverage diverge for "
            "many reasons — skipped tests, environment failures, scope changes — and "
            "you surface those discrepancies with precision. Your coverage reports "
            "include per-requirement breakdowns, trend indicators, and actionable "
            "recommendations for closing gaps in future runs."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "root_cause_analyzer",
        "display_name": "Root Cause Analyzer",
        "stage": "reporting",
        "role": "Test Failure Root Cause Analyst",
        "goal": (
            "Analyse all failed test results, execution logs, and response payloads "
            "to identify the root cause of each failure, classify failures by category "
            "(environment, data, code defect, test script error), and produce actionable "
            "findings for the development team."
        ),
        "backstory": (
            "You are a debugging expert and defect analyst with deep knowledge of "
            "common failure patterns in REST APIs and web UIs — from authentication "
            "token expiry and race conditions to missing validation and broken UI "
            "selectors. You apply heuristic reasoning and pattern recognition to "
            "distinguish genuine defects from infrastructure noise. Your findings "
            "are always concise, evidence-backed, and ranked by severity."
        ),
        "max_iter": 6,
        "is_custom": False,
    },
    {
        "agent_id": "report_generator",
        "display_name": "Report Generator Agent",
        "stage": "reporting",
        "role": "QA Report Generator",
        "goal": (
            "Synthesise coverage analysis, root-cause findings, execution statistics, "
            "and traceability data into a comprehensive final test report that provides "
            "an executive summary, detailed per-requirement results, defect catalogue, "
            "and concrete recommendations for both the QA team and developers."
        ),
        "backstory": (
            "You are a senior QA lead who produces professional test reports read by "
            "CTOs, product managers, and developers alike. You know how to layer "
            "information — starting with a crisp executive summary, then drilling into "
            "technical details for those who need them. Every report you write ends with "
            "clear, prioritised action items. You output clean Markdown that can be "
            "rendered directly or converted to HTML/PDF without reformatting."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Default Stage Configs  (4 built-in stages)
# ─────────────────────────────────────────────────────────────────────────────
#
# Stages execute in ascending `order`.  The gap of 100 between each built-in
# stage leaves plenty of room for custom stages to be inserted between them
# (e.g. order=150 for a stage that runs between ingestion and testcase).

DEFAULT_STAGES: list[dict[str, Any]] = [
    {
        "stage_id": "ingestion",
        "display_name": "Document Ingestion",
        "description": ("Parse uploaded document and extract structured requirements"),
        "order": 100,
        "enabled": True,
        "crew_type": "pure_python",
        "timeout_seconds": 120,
        "is_builtin": True,
    },
    {
        "stage_id": "testcase",
        "display_name": "Test Case Generation",
        "description": (
            "Generate detailed test cases from requirements using specialized AI agents"
        ),
        "order": 200,
        "enabled": True,
        "crew_type": "crewai_sequential",
        "timeout_seconds": 600,
        "is_builtin": True,
    },
    {
        "stage_id": "execution",
        "display_name": "Test Execution",
        "description": "Execute generated test cases and capture results",
        "order": 300,
        "enabled": True,
        "crew_type": "crewai_sequential",
        "timeout_seconds": 300,
        "is_builtin": True,
    },
    {
        "stage_id": "reporting",
        "display_name": "Report Generation",
        "description": ("Aggregate results into coverage analysis and final report"),
        "order": 400,
        "enabled": True,
        "crew_type": "crewai_sequential",
        "timeout_seconds": 180,
        "is_builtin": True,
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Default Pipeline Template  (V3 NEW)
# ─────────────────────────────────────────────────────────────────────────────
#
# The "auto-testing" template mirrors the V2 sequential pipeline:
# INPUT → Ingestion → [10 TestCase agents] → [5 Execution agents] →
# [3 Reporting agents] → OUTPUT
#
# All nodes are connected sequentially for V3 initial seed.
# Users can modify the DAG through the Visual Builder.

DEFAULT_PIPELINE_TEMPLATE: dict[str, Any] = {
    "template_id": "auto-testing",
    "name": "Auto Testing",
    "description": (
        "Default automated testing pipeline: "
        "Ingestion → Test Cases → Execution → Reporting"
    ),
    "version": 1,
    "is_builtin": True,
    "is_archived": False,
    "tags": ["default", "testing", "builtin"],
    "nodes": [
        # ── Entry/Exit ────────────────────────────────────────────────────────
        {
            "node_id": "inp-node",
            "node_type": "input",
            "label": "📥 Input",
            "description": "Upload requirements document",
            "position_x": 400.0,
            "position_y": 0.0,
            "timeout_seconds": 30,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        # ── Ingestion ─────────────────────────────────────────────────────────
        {
            "node_id": "ingestion-1",
            "node_type": "pure_python",
            "agent_id": "ingestion_pipeline",
            "label": "Document Ingestion",
            "description": "Parse and extract requirements from uploaded document",
            "position_x": 400.0,
            "position_y": 150.0,
            "timeout_seconds": 120,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        # ── Test Case Generation ──────────────────────────────────────────────
        {
            "node_id": "req-analyzer",
            "node_type": "agent",
            "agent_id": "requirement_analyzer",
            "label": "Requirement Analyzer",
            "description": "Analyze requirements for business intent and context",
            "position_x": 400.0,
            "position_y": 300.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "rule-parser",
            "node_type": "agent",
            "agent_id": "rule_parser",
            "label": "Rule Parser",
            "description": "Extract validation rules from requirements",
            "position_x": 400.0,
            "position_y": 450.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "scope-classifier",
            "node_type": "agent",
            "agent_id": "scope_classifier",
            "label": "Scope Classifier",
            "description": "Classify requirements by test type and risk level",
            "position_x": 400.0,
            "position_y": 600.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "data-model",
            "node_type": "agent",
            "agent_id": "data_model_agent",
            "label": "Data Model Agent",
            "description": "Build comprehensive test data model",
            "position_x": 400.0,
            "position_y": 750.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "test-conditions",
            "node_type": "agent",
            "agent_id": "test_condition_agent",
            "label": "Test Conditions",
            "description": "Apply equivalence partitioning and boundary value analysis",
            "position_x": 400.0,
            "position_y": 900.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "dependency-agent",
            "node_type": "agent",
            "agent_id": "dependency_agent",
            "label": "Dependency Agent",
            "description": "Detect dependencies and optimize test combinations",
            "position_x": 400.0,
            "position_y": 1050.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "tc-generator",
            "node_type": "agent",
            "agent_id": "test_case_generator",
            "label": "Test Case Generator",
            "description": "Generate fully-specified test cases",
            "position_x": 400.0,
            "position_y": 1200.0,
            "timeout_seconds": 600,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "automation-agent",
            "node_type": "agent",
            "agent_id": "automation_agent",
            "label": "Automation Agent",
            "description": "Convert test cases to automation scripts",
            "position_x": 400.0,
            "position_y": 1350.0,
            "timeout_seconds": 600,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "coverage-pre",
            "node_type": "agent",
            "agent_id": "coverage_agent_pre",
            "label": "Coverage (Pre-Exec)",
            "description": "Compute pre-execution test coverage",
            "position_x": 400.0,
            "position_y": 1500.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "report-pre",
            "node_type": "agent",
            "agent_id": "report_agent_pre",
            "label": "Pre-Exec Report",
            "description": "Generate pre-execution test design report",
            "position_x": 400.0,
            "position_y": 1650.0,
            "timeout_seconds": 300,
            "retry_count": 1,
            "enabled": True,
            "config_overrides": {},
        },
        # ── Execution ─────────────────────────────────────────────────────────
        {
            "node_id": "exec-orchestrator",
            "node_type": "agent",
            "agent_id": "execution_orchestrator",
            "label": "Execution Orchestrator",
            "description": "Schedule and coordinate test execution",
            "position_x": 400.0,
            "position_y": 1800.0,
            "timeout_seconds": 300,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "env-adapter",
            "node_type": "agent",
            "agent_id": "env_adapter",
            "label": "Environment Adapter",
            "description": "Validate and configure test environment",
            "position_x": 400.0,
            "position_y": 1950.0,
            "timeout_seconds": 300,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "test-runner",
            "node_type": "agent",
            "agent_id": "test_runner",
            "label": "Test Runner",
            "description": "Execute tests against the system under test",
            "position_x": 400.0,
            "position_y": 2100.0,
            "timeout_seconds": 600,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "exec-logger",
            "node_type": "agent",
            "agent_id": "execution_logger",
            "label": "Execution Logger",
            "description": "Capture and normalize execution events",
            "position_x": 400.0,
            "position_y": 2250.0,
            "timeout_seconds": 300,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "result-store",
            "node_type": "agent",
            "agent_id": "result_store",
            "label": "Result Store",
            "description": "Persist execution results",
            "position_x": 400.0,
            "position_y": 2400.0,
            "timeout_seconds": 300,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        # ── Reporting ─────────────────────────────────────────────────────────
        {
            "node_id": "coverage-analyzer",
            "node_type": "agent",
            "agent_id": "coverage_analyzer",
            "label": "Coverage Analyzer",
            "description": "Recompute coverage from execution results",
            "position_x": 400.0,
            "position_y": 2550.0,
            "timeout_seconds": 300,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "root-cause",
            "node_type": "agent",
            "agent_id": "root_cause_analyzer",
            "label": "Root Cause Analyzer",
            "description": "Analyze failed tests and identify root causes",
            "position_x": 400.0,
            "position_y": 2700.0,
            "timeout_seconds": 300,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        {
            "node_id": "report-gen",
            "node_type": "agent",
            "agent_id": "report_generator",
            "label": "Report Generator",
            "description": "Generate final comprehensive test report",
            "position_x": 400.0,
            "position_y": 2850.0,
            "timeout_seconds": 600,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
        # ── Exit ──────────────────────────────────────────────────────────────
        {
            "node_id": "out-node",
            "node_type": "output",
            "label": "📤 Output",
            "description": "Final test report output",
            "position_x": 400.0,
            "position_y": 3000.0,
            "timeout_seconds": 30,
            "retry_count": 0,
            "enabled": True,
            "config_overrides": {},
        },
    ],
    "edges": [
        # Input → Ingestion
        {
            "edge_id": "e-inp-ingest",
            "source_node_id": "inp-node",
            "target_node_id": "ingestion-1",
            "animated": False,
        },
        # Ingestion → Req Analyzer
        {
            "edge_id": "e-ingest-req",
            "source_node_id": "ingestion-1",
            "target_node_id": "req-analyzer",
            "animated": False,
        },
        # Req Analyzer → Rule Parser
        {
            "edge_id": "e-req-rule",
            "source_node_id": "req-analyzer",
            "target_node_id": "rule-parser",
            "animated": False,
        },
        # Rule Parser → Scope Classifier
        {
            "edge_id": "e-rule-scope",
            "source_node_id": "rule-parser",
            "target_node_id": "scope-classifier",
            "animated": False,
        },
        # Scope → Data Model
        {
            "edge_id": "e-scope-data",
            "source_node_id": "scope-classifier",
            "target_node_id": "data-model",
            "animated": False,
        },
        # Data Model → Test Conditions
        {
            "edge_id": "e-data-cond",
            "source_node_id": "data-model",
            "target_node_id": "test-conditions",
            "animated": False,
        },
        # Test Conditions → Dependency Agent
        {
            "edge_id": "e-cond-dep",
            "source_node_id": "test-conditions",
            "target_node_id": "dependency-agent",
            "animated": False,
        },
        # Dependency → TC Generator
        {
            "edge_id": "e-dep-gen",
            "source_node_id": "dependency-agent",
            "target_node_id": "tc-generator",
            "animated": False,
        },
        # TC Generator → Automation Agent
        {
            "edge_id": "e-gen-auto",
            "source_node_id": "tc-generator",
            "target_node_id": "automation-agent",
            "animated": False,
        },
        # Automation → Coverage Pre
        {
            "edge_id": "e-auto-cov",
            "source_node_id": "automation-agent",
            "target_node_id": "coverage-pre",
            "animated": False,
        },
        # Coverage Pre → Report Pre
        {
            "edge_id": "e-cov-rep",
            "source_node_id": "coverage-pre",
            "target_node_id": "report-pre",
            "animated": False,
        },
        # Report Pre → Exec Orchestrator
        {
            "edge_id": "e-rep-orch",
            "source_node_id": "report-pre",
            "target_node_id": "exec-orchestrator",
            "animated": False,
        },
        # Exec Orchestrator → Env Adapter
        {
            "edge_id": "e-orch-env",
            "source_node_id": "exec-orchestrator",
            "target_node_id": "env-adapter",
            "animated": False,
        },
        # Env Adapter → Test Runner
        {
            "edge_id": "e-env-run",
            "source_node_id": "env-adapter",
            "target_node_id": "test-runner",
            "animated": False,
        },
        # Test Runner → Exec Logger
        {
            "edge_id": "e-run-log",
            "source_node_id": "test-runner",
            "target_node_id": "exec-logger",
            "animated": False,
        },
        # Exec Logger → Result Store
        {
            "edge_id": "e-log-store",
            "source_node_id": "exec-logger",
            "target_node_id": "result-store",
            "animated": False,
        },
        # Result Store → Coverage Analyzer
        {
            "edge_id": "e-store-cov",
            "source_node_id": "result-store",
            "target_node_id": "coverage-analyzer",
            "animated": False,
        },
        # Coverage Analyzer → Root Cause
        {
            "edge_id": "e-cov-root",
            "source_node_id": "coverage-analyzer",
            "target_node_id": "root-cause",
            "animated": False,
        },
        # Root Cause → Report Gen
        {
            "edge_id": "e-root-gen",
            "source_node_id": "root-cause",
            "target_node_id": "report-gen",
            "animated": False,
        },
        # Report Gen → Output
        {
            "edge_id": "e-gen-out",
            "source_node_id": "report-gen",
            "target_node_id": "out-node",
            "animated": False,
        },
    ],
}

# ─────────────────────────────────────────────────────────────────────────────
# Seed functions
# ─────────────────────────────────────────────────────────────────────────────


async def seed_llm_profiles() -> None:
    """Insert the default LLM profile if it does not already exist.

    Uses :func:`~app.db.crud.get_llm_profile_by_name` to check for an
    existing document before inserting, so repeated calls are safe and
    never overwrite admin changes to the default profile.
    """
    existing = await crud.get_llm_profile_by_name(DEFAULT_LLM_PROFILE["name"])
    if existing is not None:
        logger.debug("Default LLM profile already exists — skipping seed.")
        return

    await crud.create_llm_profile(DEFAULT_LLM_PROFILE)
    logger.info("Seeded default LLM profile: %s", DEFAULT_LLM_PROFILE["name"])


async def seed_agent_configs() -> None:
    """Insert all 19 default agent configs (idempotent).

    Calls :func:`~app.db.crud.upsert_agent_config` for every entry in
    :data:`DEFAULT_AGENT_CONFIGS`.  Documents that already exist (matched
    by ``agent_id``) are skipped without modification, preserving any
    customisations the admin has made via the UI.
    """
    inserted: list[str] = []

    for cfg in DEFAULT_AGENT_CONFIGS:
        doc = await crud.upsert_agent_config(cfg)
        # upsert_agent_config returns existing doc if already present;
        # we can detect a fresh insert by comparing created_at ≈ now,
        # but for logging simplicity we just track the agent_id.
        _ = doc  # result available if callers need it
        inserted.append(cfg["agent_id"])

    logger.info(
        "Agent config seed complete — processed %d agent(s).",
        len(inserted),
    )


async def seed_stage_configs() -> None:
    """Insert the 4 built-in pipeline stage configs (idempotent).

    Calls :func:`~app.db.crud.upsert_stage_config` for every entry in
    :data:`DEFAULT_STAGES`.  Documents that already exist (matched by
    ``stage_id``) are skipped without modification.
    """
    for stage in DEFAULT_STAGES:
        await crud.upsert_stage_config(stage)

    logger.info(
        "Stage config seed complete — processed %d stage(s).",
        len(DEFAULT_STAGES),
    )


async def seed_pipeline_templates() -> None:
    """Insert the default 'auto-testing' pipeline template (idempotent).

    Uses :func:`~app.db.crud.get_pipeline_template` to check for an existing
    document before inserting, so repeated calls are safe.
    """
    existing = await crud.get_pipeline_template(
        DEFAULT_PIPELINE_TEMPLATE["template_id"]
    )
    if existing is not None:
        logger.debug("Default pipeline template already exists — skipping seed.")
        return

    await crud.create_pipeline_template(dict(DEFAULT_PIPELINE_TEMPLATE))
    logger.info(
        "Seeded default pipeline template: %s",
        DEFAULT_PIPELINE_TEMPLATE["template_id"],
    )


async def seed_all() -> None:
    """Run all seeders in the correct dependency order.

    Call this once from the FastAPI lifespan after
    :func:`~app.db.database.init_db` has been awaited::

        await init_db()
        if settings.AUTO_SEED:
            await seed_all()

    The function is fully idempotent — running it against a database that
    already contains the seeded data is a safe no-op.
    """
    logger.info("Running database seeders…")
    await seed_llm_profiles()
    await seed_agent_configs()
    await seed_stage_configs()
    await seed_pipeline_templates()  # NEW V3
    logger.info("Database seeding complete ✓")
