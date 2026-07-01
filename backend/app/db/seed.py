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

from app.config import settings
from app.db import crud

logger = logging.getLogger(__name__)

# Resolve the seeded Ollama endpoint from the environment so a Docker-hosted
# backend reaches the host's Ollama (host.docker.internal) instead of pointing
# at the container itself. Falls back to the local default for native runs.
_DEFAULT_OLLAMA_BASE_URL = settings.DEFAULT_LLM_BASE_URL or settings.OLLAMA_BASE_URL

# ─────────────────────────────────────────────────────────────────────────────
# Default LLM Profile
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_LLM_PROFILE: dict[str, Any] = {
    "name": "Ollama Local (Default)",
    "provider": "ollama",
    "model": "gemma4:e2b",
    "api_key": None,
    "base_url": _DEFAULT_OLLAMA_BASE_URL,
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
        "tool_names": ["document_parser", "text_chunker"],
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
        "role": "Senior API Test Case Engineer",
        "goal": (
            "From the analysed requirements, generate complete and fully-specified "
            "REST API test cases in a single pass. Internally: extract validation "
            "rules, build the request/response data model, apply equivalence "
            "partitioning and boundary value analysis, map cross-field "
            "dependencies, then emit atomic test cases. Each case must include a "
            "unique ID, HTTP method + endpoint, request body/headers, expected "
            "status code, expected response shape, and traceability back to the "
            "source requirement. No UI / browser steps — API only."
        ),
        "backstory": (
            "You are a senior QA engineer specialised in REST API testing. You "
            "habitually decompose requirements into rules → data partitions → "
            "boundary values → dependency chains → concrete test cases in one "
            "pass without losing rigor. Every test case you write is atomic, "
            "self-contained, traceable, and runnable by an httpx/pytest "
            "harness. You produce structured JSON output with a top-level "
            "``test_cases`` array — no markdown, no prose."
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
        "display_name": "API Test Runner",
        "stage": "execution",
        "role": "API Test Execution Engineer",
        "goal": (
            "Execute every executable API test case against the configured "
            "target environment via the ``api_runner`` tool, capture the full "
            "HTTP response (status code, headers, body, latency), compare it "
            "against the expected status code and expected_result, and return "
            "a structured ExecutionOutput with per-case verdicts plus an "
            "aggregate summary (total / passed / failed / skipped / pass_rate)."
        ),
        "backstory": (
            "You are a REST API test execution specialist. You have run "
            "millions of httpx-driven test cases against production-grade "
            "APIs. You record every response with full evidence — body, "
            "headers, latency — and never paper over a deviation from the "
            "expected status code. You always emit a strict JSON object with "
            "``results`` (list of dicts) and ``summary`` (dict with "
            "``pass_rate``) so downstream verifiers can read it deterministically."
        ),
        "max_iter": 8,
        "is_custom": False,
        "tool_names": ["api_runner"],
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
            "From the executed API test cases, results, and generated unit "
            "test files, produce the final QA report in a single pass. "
            "Internally: compute post-execution coverage per requirement, "
            "diagnose root causes for each failed case (classify as "
            "code defect / data issue / environment / test-script bug), "
            "then emit an executive summary, per-requirement results table, "
            "defect catalogue ranked by severity, and prioritised "
            "recommendations. Do NOT discuss UI selectors or browser "
            "behaviour — this is an API testing pipeline."
        ),
        "backstory": (
            "You are a senior QA lead who synthesises coverage analysis, "
            "root-cause findings, and execution statistics in one pass for "
            "REST API test runs. Reports you write are read by CTOs, product "
            "managers, and developers — crisp executive summary up top, "
            "technical drill-down below, prioritised actions at the bottom. "
            "You output clean Markdown that converts directly to HTML/DOCX."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    # ── Stage: artifact ──────────────────────────────────────────────────────
    {
        "agent_id": "lang_detector",
        "display_name": "Language Detector",
        "stage": "artifact",
        "role": "Project Language Analyst",
        "goal": (
            "Detect the target programming language for test file generation by "
            "inspecting project configuration files (pyproject.toml, package.json, "
            "pom.xml, go.mod, etc.) or using the caller-specified language override."
        ),
        "backstory": (
            "You are a polyglot developer who has worked across Python, TypeScript, "
            "Java, Go, and C# codebases. You reliably identify a project's primary "
            "language from its configuration files and map it to the appropriate "
            "test framework (pytest, vitest, junit5, go test, xunit)."
        ),
        "max_iter": 2,
        "is_custom": False,
    },
    {
        "agent_id": "unit_file_writer",
        "display_name": "Unit Test File Writer",
        "stage": "artifact",
        "role": "Test Automation Engineer",
        "goal": (
            "Generate complete, runnable unit test files from TestCase objects, "
            "grouped logically by API endpoint or UI page, using idiomatic code "
            "for the detected language and framework."
        ),
        "backstory": (
            "You are a test automation specialist with deep expertise across multiple "
            "testing frameworks. You write clean, well-structured test code that "
            "follows the conventions of each language — pytest fixtures for Python, "
            "describe/it blocks for TypeScript/JavaScript, @Test annotations for Java. "
            "Every file you generate is immediately runnable with a single command."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "testcase_doc_writer",
        "display_name": "Test Case Doc Writer",
        "stage": "artifact",
        "role": "QA Documentation Specialist",
        "goal": (
            "Generate a comprehensive, human-readable Markdown test case specification "
            "document that maps every test case back to its source requirement, "
            "includes clear preconditions, step-by-step actions, and expected results."
        ),
        "backstory": (
            "You are a QA lead who has written test specifications for enterprise "
            "software projects across many domains. Your documents are models of clarity "
            "— organised by requirement, with traceability links, summary tables, and "
            "detailed step-by-step test procedures. They serve both manual testers and "
            "automated CI/CD pipelines without modification."
        ),
        "max_iter": 4,
        "is_custom": False,
    },
    # ── Stage: playwright ─────────────────────────────────────────────────────
    {
        "agent_id": "test_reviewer",
        "display_name": "Test Case Reviewer",
        "stage": "playwright",
        "role": "Senior QA Engineer",
        "goal": (
            "Review and refine the generated test cases for completeness, clarity, "
            "and end-to-end testability with Playwright. Identify missing edge cases, "
            "ambiguous steps, duplicate scenarios, and ensure every test case maps "
            "unambiguously back to a source requirement. Output a clean, finalised "
            "list of TestCase objects ready for Playwright code generation."
        ),
        "backstory": (
            "You are a senior QA engineer with 10 years of experience reviewing test "
            "cases for web and API applications. You have a sharp eye for incomplete "
            "preconditions, vague expected results, and missing negative test paths. "
            "You understand Playwright's capabilities and always flag test cases that "
            "cannot be automated — replacing them with automatable equivalents. "
            "Your reviews consistently improve test suite quality by 40%."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "playwright_spec_writer",
        "display_name": "Playwright Spec Writer",
        "stage": "playwright",
        "role": "Playwright Test Automation Engineer",
        "goal": (
            "Generate complete, immediately runnable Playwright TypeScript test spec "
            "files (.spec.ts) from the reviewed test cases. Follow Page Object Model "
            "pattern, use descriptive test names matching the test case titles, include "
            "proper locators (getByRole, getByTestId, getByLabel), assertions "
            "(expect(locator).toBeVisible(), toHaveText(), etc.), and group related "
            "tests in describe blocks. Each spec file maps to one functional area."
        ),
        "backstory": (
            "You are a Playwright expert who has automated thousands of web UI and API "
            "tests. You write TypeScript test code that is readable, maintainable, and "
            "follows Playwright best practices: prefer user-facing locators, avoid "
            "hard-coded waits, use auto-waiting assertions, and always test from the "
            "user's perspective. Your specs are used by CI/CD pipelines across dozens "
            "of production applications."
        ),
        "max_iter": 8,
        "is_custom": False,
    },
    {
        "agent_id": "playwright_fixture_writer",
        "display_name": "Playwright Fixture Writer",
        "stage": "playwright",
        "role": "Test Infrastructure Engineer",
        "goal": (
            "Generate the complete Playwright test infrastructure to support the spec "
            "files: (1) Page Object classes in pages/ for every page/component under "
            "test, (2) fixtures.ts extending base test with shared setup/teardown, "
            "(3) test-data.ts with typed test data constants, (4) playwright.config.ts "
            "with sensible defaults (baseURL, retries, reporter, browser projects), "
            "(5) .env.example listing required environment variables."
        ),
        "backstory": (
            "You are a test infrastructure specialist who designs maintainable Playwright "
            "frameworks from scratch. You understand how to structure a test project so "
            "that specs stay clean and infrastructure concerns are isolated. You always "
            "generate Page Object classes with typed locators, shared fixtures for "
            "authentication and API mocking, and configuration files that work out of "
            "the box with npx playwright test. Your setups reduce test maintenance cost "
            "by 60% compared to ad-hoc test files."
        ),
        "max_iter": 6,
        "is_custom": False,
    },
    # ── Stage: ingestion — Automation Testing API guard ───────────────────────
    {
        "agent_id": "md_api_spec_verifier",
        "display_name": "MD API Spec Verifier",
        "stage": "ingestion",
        "role": "MD API Spec Validator",
        "goal": (
            "Validate uploaded Markdown API specification files against the "
            "Automation Testing API contract v1: Endpoint / Request / Response "
            "sections must be present and well-formed. Fail-fast with a "
            "structured error so the downstream DAG never runs on broken input."
        ),
        "backstory": (
            "You are a deterministic, rule-based guard. You do not call an LLM. "
            "You parse the markdown line by line, extract Method / Path / "
            "request fields / response status codes, and either approve the spec "
            "or raise MDSpecValidationError with machine-readable codes."
        ),
        "max_iter": 1,
        "is_custom": False,
        "tool_names": ["md_api_spec_validator"],
    },
    # ── Stage: testcase — Test-level classifier ───────────────────────────────
    {
        "agent_id": "test_level_classifier",
        "display_name": "Test Level Classifier",
        "stage": "testcase",
        "role": "Test Level Classifier",
        "goal": (
            "Tag every test case with test_level ∈ {unit, integration, "
            "contract, e2e} and the executable boolean flag based on the "
            "endpoint hint and case content. Apply rule-based classification "
            "first; only fall back to LLM reasoning when the rule confidence "
            "is below threshold."
        ),
        "backstory": (
            "You are a senior QA architect specialised in test taxonomy. You "
            "know that misclassifying a unit test as integration wastes "
            "execution budget, and misclassifying an e2e as unit breaks the "
            "runner. You apply heuristics deterministically and only escalate "
            "ambiguous cases to the LLM."
        ),
        "max_iter": 3,
        "is_custom": False,
        "tool_names": ["test_level_tagger"],
    },
    # ── Stage: testcase — Request body synthesizer (LLM refinement) ───────────
    {
        "agent_id": "request_body_synthesizer",
        "display_name": "Request Body Synthesizer",
        "stage": "testcase",
        "role": "API Request Body Synthesizer",
        "goal": (
            "Turn each body-carrying endpoint's declared fields, rules, and "
            "spec example into ONE valid, domain-realistic happy-path request "
            "body, keyed by '<METHOD> <path>'. Keep every field, honour the "
            "declared type and rules, and replace schema placeholders "
            "(\"string\", \"YYYY-MM-DD\", \"HH:mm\") with believable values. "
            "Emit a strict JSON map — no prose, no markdown."
        ),
        "backstory": (
            "You are a QA data engineer who knows that a happy-path test only "
            "proves anything when its payload looks like real production data. "
            "You never invent fields the schema does not declare, and you never "
            "echo secret credential values. When unsure, you keep the "
            "deterministic reference value rather than guessing wildly."
        ),
        "max_iter": 3,
        "is_custom": False,
    },
    # ── Stage: reporting — Export + Verifier ──────────────────────────────────
    {
        "agent_id": "export_html_docx",
        "display_name": "Report Export (HTML + DOCX)",
        "stage": "reporting",
        "role": "Report Exporter",
        "goal": (
            "Render the final PipelineReport into HTML and DOCX formats and "
            "upload both files to MinIO under runs/{run_id}/report.{ext}. "
            "Return the storage paths plus byte sizes so the verifier can "
            "syntax-check before the user downloads."
        ),
        "backstory": (
            "You are a deterministic export utility. You template the report, "
            "package the unit test files, and persist artifacts. You never "
            "call an LLM."
        ),
        "max_iter": 1,
        "is_custom": False,
    },
    {
        "agent_id": "report_verifier",
        "display_name": "Report Verifier",
        "stage": "reporting",
        "role": "Report 3-Component Verifier",
        "goal": (
            "Verify that the final report contains all 3 mandatory "
            "components: (1) test case info, (2) execution results, (3) "
            "unit test files. Raise ReportVerificationError when any "
            "component is missing or malformed; the API will refuse the "
            "download until the issue is fixed."
        ),
        "backstory": (
            "You are the last guard before the user receives a deliverable. "
            "You are paranoid about empty arrays, missing pass-rate, and "
            "syntactically invalid generated files. You are rule-based and "
            "never call an LLM."
        ),
        "max_iter": 1,
        "is_custom": False,
        "tool_names": ["report_verifier"],
    },
    # ── Adaptive multi-agent planners (adaptive-api-testing-pipeline) ─────────
    # Five specialised API test planners. The complexity decision selects 1-5
    # of them in fixed priority order. Each emits a strict JSON test_cases
    # array, maps cases to source obligations, and never echoes secret values.
    {
        "agent_id": "adaptive_planner_positive",
        "display_name": "Positive Path Planner",
        "stage": "testcase",
        "role": "Positive-Path API Test Planner",
        "goal": (
            "Design valid happy-path API test cases covering every declared "
            "2xx response: correct method, fully-populated request body, valid "
            "headers, and the expected success status. Map each case to the "
            "response obligation it satisfies. Emit a strict JSON object with a "
            "top-level ``test_cases`` array — no prose, no markdown."
        ),
        "backstory": (
            "You are a senior QA engineer who proves the contract works as "
            "specified before anyone hunts for failures. You never invent "
            "behaviour the spec does not state, and when you must, you flag it "
            "as an assumption."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "adaptive_planner_negative_schema",
        "display_name": "Negative / Schema Planner",
        "stage": "testcase",
        "role": "Negative & Schema-Validation API Test Planner",
        "goal": (
            "Design negative API test cases that must be rejected with a 4xx: "
            "missing required fields, wrong types, malformed payloads, and "
            "schema violations. One focused mutation per case, each linked to "
            "the field/rule obligation it probes. Emit strict JSON with a "
            "top-level ``test_cases`` array."
        ),
        "backstory": (
            "You break inputs for a living. You think in equivalence classes of "
            "invalidity and assert the precise rejection status the contract "
            "promises, never echoing secret values."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "adaptive_planner_auth_security",
        "display_name": "Auth / Security Planner",
        "stage": "testcase",
        "role": "Authentication & Authorization API Test Planner",
        "goal": (
            "Design auth/security API test cases: missing or invalid tokens and "
            "missing required headers expecting 401/403, plus unauthorized "
            "access attempts. Use placeholders like ${TOKEN} — never real "
            "secret values. Map cases to auth/header obligations. Emit strict "
            "JSON with a top-level ``test_cases`` array."
        ),
        "backstory": (
            "You are a security-minded tester who assumes every endpoint is a "
            "target. You verify the access boundary without ever leaking a "
            "credential into a test artefact."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "adaptive_planner_boundary_data",
        "display_name": "Boundary / Data Planner",
        "stage": "testcase",
        "role": "Boundary-Value & Data-Partition API Test Planner",
        "goal": (
            "Design boundary-value and equivalence-partition API test cases: "
            "min/max lengths, empty/null, zero, and oversized inputs at the "
            "edges of each validation rule. Map cases to the rule obligation "
            "exercised. Emit strict JSON with a top-level ``test_cases`` array."
        ),
        "backstory": (
            "You live at the edges where off-by-one defects hide. You pick the "
            "exact boundary the rule defines and assert the behaviour on both "
            "sides of it, flagging any edge the spec leaves unstated."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    {
        "agent_id": "adaptive_planner_resilience",
        "display_name": "Resilience / Idempotency Planner",
        "stage": "testcase",
        "role": "Resilience & Idempotency API Test Planner",
        "goal": (
            "Design resilience and idempotency API test cases: repeated and "
            "duplicate requests, idempotent PUT/DELETE behaviour, and "
            "unknown-id lookups expecting 404. Map each case to the relevant "
            "obligation and flag invented behaviour as an assumption. Emit "
            "strict JSON with a top-level ``test_cases`` array."
        ),
        "backstory": (
            "You test what happens when the same request arrives twice, or the "
            "target is missing. You distinguish guaranteed contract behaviour "
            "from reasonable-but-unstated assumptions and label them honestly."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
    # ── Senior coverage reviewer (adaptive-api-testing-pipeline) ──────────────
    # One senior agent reviews the consolidated plan qualitatively. Numeric
    # coverage stays deterministic; this agent may reject but never fabricates
    # coverage. Its verdict + targeted feedback drive the bounded review loop.
    {
        "agent_id": "senior_api_test_reviewer",
        "display_name": "Senior API Test Reviewer",
        "stage": "testcase",
        "role": "Senior API Test Plan Reviewer",
        "goal": (
            "Critically review a consolidated API test plan for correctness, "
            "internal contradictions, unsafe assumptions, executability, and "
            "missing edge cases. Return a strict JSON verdict "
            "(approve|revise|reject) with concise evidence, identified gaps, "
            "unsafe assumptions, and targeted, actionable feedback for the next "
            "planning iteration. The numeric coverage is computed "
            "deterministically and is authoritative — never restate or override "
            "it. Emit no prose, no markdown, and never echo secret values."
        ),
        "backstory": (
            "You are a principal QA engineer who signs off on test suites before "
            "they run against real systems. You reject plans that are unsafe or "
            "self-contradictory and give precise, fixable feedback, but you never "
            "invent coverage numbers — the gate owns those."
        ),
        "max_iter": 5,
        "is_custom": False,
    },
]
# ─────────────────────────────────────────────────────────────────────────────
#
# Stages execute in ascending `order`.  The gap of 100 between each built-in
# stage leaves plenty of room for custom stages to be inserted between them
# (e.g. order=150 for a stage that runs between ingestion and testcase).

DEFAULT_STAGES: list[dict[str, Any]] = [
    {
        "stage_id": "ingestion",
        "display_name": "Document Ingestion",
        "description": "Parse and chunk uploaded documents for downstream processing.",
        "order": 100,
        "color": "#6366F1",  # Indigo
        "icon": "file-input",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "testcase",
        "display_name": "Test Case Generation",
        "description": "Analyze requirements and generate comprehensive test cases.",
        "order": 200,
        "color": "#8B5CF6",  # Violet
        "icon": "flask-conical",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "execution",
        "display_name": "Test Execution",
        "description": "Execute generated test cases against the target system.",
        "order": 300,
        "color": "#F59E0B",  # Amber
        "icon": "play",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "reporting",
        "display_name": "Reporting",
        "description": "Analyze results, identify root causes, and generate reports.",
        "order": 400,
        "color": "#10B981",  # Emerald
        "icon": "file-bar-chart",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "artifact",
        "display_name": "Artifact Generation",
        "description": "Generate runnable unit test files and human-readable test case spec.",
        "order": 450,
        "color": "#3B82F6",  # Blue
        "icon": "file-code",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "playwright",
        "display_name": "Playwright Generation",
        "description": "Review test cases and generate runnable Playwright TypeScript spec files and test infrastructure.",
        "order": 460,
        "color": "#059669",  # Emerald-600 (Playwright brand green)
        "icon": "play-circle",
        "enabled": True,
        "is_builtin": True,
    },
    {
        "stage_id": "custom",
        "display_name": "Custom / Unassigned",
        "description": "Catch-all stage for user-created agents not assigned to a specific stage.",
        "order": 9999,
        "color": "#6B7280",  # Gray
        "icon": "puzzle",
        "enabled": True,
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
    "is_builtin": False,
    "is_archived": False,
    "tags": ["default", "testing"],
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
    """Insert or refresh default agent configs (idempotent).

    Behaviour per agent:
      - missing in DB  → insert via :func:`~app.db.crud.upsert_agent_config`
      - exists & ``is_custom=False`` (seeded) → refresh the prompt fields
        from :data:`DEFAULT_AGENT_CONFIGS` so that goal/role/backstory
        updates in this file actually reach existing deployments
      - exists & ``is_custom=True`` (admin-customised) → left untouched
    """
    # Only refresh fields that describe the agent's behaviour. Things like
    # ``enabled`` and ``tool_names`` may have been deliberately tuned by
    # operators and are not refreshed automatically.
    _REFRESHABLE_FIELDS = ("role", "goal", "backstory", "display_name", "max_iter")

    inserted = 0
    refreshed = 0
    skipped_custom = 0

    for cfg in DEFAULT_AGENT_CONFIGS:
        existing = await crud.get_agent_config(cfg["agent_id"])
        if existing is None:
            await crud.upsert_agent_config(cfg)
            inserted += 1
            continue
        if getattr(existing, "is_custom", False):
            skipped_custom += 1
            continue
        diff = {
            field: cfg[field]
            for field in _REFRESHABLE_FIELDS
            if field in cfg and getattr(existing, field, None) != cfg[field]
        }
        if diff:
            await crud.update_agent_config(cfg["agent_id"], diff)
            refreshed += 1

    logger.info(
        "Agent configs: %d inserted, %d refreshed, %d custom left alone.",
        inserted,
        refreshed,
        skipped_custom,
    ) if (inserted or refreshed) else logger.debug(
        "Agent configs: unchanged (%d total).",
        len(DEFAULT_AGENT_CONFIGS),
    )


async def seed_stage_configs() -> None:
    """Insert the 4 built-in pipeline stage configs (idempotent).

    Calls :func:`~app.db.crud.upsert_stage_config` for every entry in
    :data:`DEFAULT_STAGES`.  Documents that already exist (matched by
    ``stage_id``) are skipped without modification.
    """
    for stage in DEFAULT_STAGES:
        await crud.upsert_stage_config(stage)

    logger.debug(
        "Stage configs: processed %d stage(s).",
        len(DEFAULT_STAGES),
    )


async def seed_pipeline_templates() -> None:
    """Insert pipeline templates if they do not already exist (idempotent)."""
    existing = await crud.get_pipeline_template(
        DEFAULT_PIPELINE_TEMPLATE["template_id"]
    )
    if existing is None:
        await crud.create_pipeline_template(dict(DEFAULT_PIPELINE_TEMPLATE))
        logger.info(
            "Seeded pipeline template: %s",
            DEFAULT_PIPELINE_TEMPLATE["template_id"],
        )
    else:
        logger.debug(
            "Pipeline template '%s' already exists — skipping seed.",
            DEFAULT_PIPELINE_TEMPLATE["template_id"],
        )

    at_template = _build_automation_testing_api_template()
    existing_at = await crud.get_pipeline_template(at_template["template_id"])
    if existing_at is None:
        await crud.create_pipeline_template(dict(at_template))
        logger.info(
            "Seeded pipeline template: %s (v%d)",
            at_template["template_id"],
            int(at_template.get("version") or 1),
        )
    else:
        logger.debug(
            "Pipeline template '%s' already exists — skipping seed.",
            at_template["template_id"],
        )
        # Upgrade an unchanged deployed v4 template to the adaptive planner.
        await migrate_automation_testing_api_to_v5()


# ─────────────────────────────────────────────────────────────────────────────
# Automation Testing API template builder (Phase 6 — automation-testing-api plan)
# ─────────────────────────────────────────────────────────────────────────────


def _build_automation_testing_api_template() -> dict[str, Any]:
    """Construct the slim ``automation-testing-api`` PipelineTemplateDocument.

    Linear API-only DAG — 11 nodes total (INPUT + 9 stages + OUTPUT). The
    previous v1 template chained 23 nodes including UI/UX-oriented agents
    (``scope_classifier``, ``automation_agent`` for Playwright/Selenium,
    ``test_runner`` described as "API / UI Test Runner") which are not
    needed for pure API testing. The pre-execution coverage / report agents
    and the 4 micro-stages around the test runner were also redundant.

    What stays:
        INPUT
          ↓
        md_api_spec_verifier   (pure_python guard — MD spec contract)
          ↓
        ingestion_pipeline     (pure_python — MD → requirements)
          ↓
        requirement_analyzer   (agent — enrich requirements, API-only)
          ↓
        test_case_generator    (agent — generate API test cases, EP/BVA
                                inline; replaces rule_parser, scope_classifier,
                                data_model, test_conditions, dependency)
          ↓
        test_level_classifier  (pure_python — tag executable flag)
          ↓
        test_runner            (agent — execute API tests via api_runner tool;
                                replaces orchestrator/env_adapter/logger/store)
          ↓
        artifact_pipeline      (pure_python — pytest+httpx test files)
          ↓
        report_generator       (agent — final report; replaces coverage_analyzer
                                and root_cause_analyzer)
          ↓
        export_html_docx       (pure_python — render + upload to MinIO)
          ↓
        report_verifier        (pure_python guard — 3-component completeness)
          ↓
        OUTPUT

    Every node id is prefixed with ``at-api-`` to avoid collisions with the
    default template.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    y = 0.0

    def _add_node(
        node_id: str,
        node_type: str,
        agent_id: str | None,
        label: str,
        description: str,
        timeout: int = 300,
        retry: int = 1,
    ) -> str:
        nonlocal y
        node: dict[str, Any] = {
            "node_id": node_id,
            "node_type": node_type,
            "label": label,
            "description": description,
            "position_x": 400.0,
            "position_y": y,
            "timeout_seconds": timeout,
            "retry_count": retry,
            "enabled": True,
            "config_overrides": {},
        }
        if agent_id:
            node["agent_id"] = agent_id
        nodes.append(node)
        y += 140.0
        return node_id

    def _edge(src: str, tgt: str) -> None:
        edges.append(
            {
                "edge_id": f"e-{src}-{tgt}",
                "source_node_id": src,
                "target_node_id": tgt,
                "animated": False,
            }
        )

    # Layer 0 — INPUT
    inp = _add_node(
        "at-api-input",
        "input",
        None,
        "📥 MD Upload",
        "Upload Markdown API specification",
        timeout=30,
        retry=0,
    )

    # Layer 1 — MD spec guard (fail-fast)
    verifier = _add_node(
        "at-api-md-verifier",
        "pure_python",
        "md_api_spec_verifier",
        "MD Spec Verifier",
        "Validate that the uploaded MD follows the v1 API spec contract",
        timeout=60,
        retry=0,
    )
    _edge(inp, verifier)

    # Layer 2 — parse MD into requirements
    ingestion = _add_node(
        "at-api-ingestion",
        "pure_python",
        "ingestion_pipeline",
        "Ingestion Pipeline",
        "Parse + chunk the MD spec into requirement items",
        timeout=180,
        retry=1,
    )
    _edge(verifier, ingestion)

    # Layer 3 — single requirement enrichment step
    req_analyzer = _add_node(
        "at-api-req-analyzer",
        "agent",
        "requirement_analyzer",
        "Requirement Analyzer",
        "Enrich requirements with API-focused context",
        timeout=300,
        retry=1,
    )
    _edge(ingestion, req_analyzer)

    # Layer 4 — generate API test cases deterministically from the parsed
    # MD spec (pure-Python rule-based; no LLM dependency).
    tc_generator = _add_node(
        "at-api-tc-generator",
        "pure_python",
        "adaptive_api_test_planner",
        "Adaptive Test Planner",
        "Baseline rule-based cases + 1-5 complexity-selected planner agents + "
        "debate + deterministic consolidation + bounded senior-review gate",
        timeout=600,
        retry=0,
    )
    # Adaptive-planner + review-gate defaults (configuration contract). Per-run
    # overrides validated via run_params take precedence at runtime; these are
    # the admin-editable template defaults snapshotted into the run result.
    nodes[-1]["config_overrides"] = {
        "min_planner_agents": 1,
        "max_planner_agents": 5,
        "coverage_threshold_percent": 90,
        "max_review_iterations": 3,
        "continue_on_exhaustion": True,
    }
    _edge(req_analyzer, tc_generator)

    # Layer 5 — tag executable flag on each case
    classifier = _add_node(
        "at-api-test-level-classifier",
        "pure_python",
        "test_level_classifier",
        "Test Level Classifier",
        "Tag every case with test_level + executable",
        timeout=120,
        retry=0,
    )
    _edge(tc_generator, classifier)

    # Layer 6 — execute API tests deterministically via httpx (pure-Python).
    test_runner = _add_node(
        "at-api-test-runner",
        "pure_python",
        "api_test_runner",
        "API Test Runner",
        "httpx-based runner: execute each executable case, capture response",
        timeout=900,
        retry=0,
    )
    _edge(classifier, test_runner)

    # Layer 7 — generate runnable pytest+httpx files
    artifact = _add_node(
        "at-api-artifact",
        "pure_python",
        "artifact_pipeline",
        "Artifact Pipeline",
        "Generate unit-test files + spec markdown",
        timeout=600,
        retry=1,
    )
    _edge(test_runner, artifact)

    # Layer 8 — final report (formerly coverage_analyzer + root_cause +
    # report_generator)
    report_gen = _add_node(
        "at-api-report-gen",
        "agent",
        "report_generator",
        "Report Generator",
        "Synthesise coverage, findings, and final QA report",
        timeout=600,
        retry=0,
    )
    _edge(artifact, report_gen)

    # Layer 9 — export HTML + DOCX
    export_node = _add_node(
        "at-api-export-html-docx",
        "pure_python",
        "export_html_docx",
        "Export HTML + DOCX",
        "Render HTML + DOCX, upload to MinIO",
        timeout=180,
        retry=1,
    )
    _edge(report_gen, export_node)

    # Layer 10 — verify 3 components (fail-fast)
    verifier_node = _add_node(
        "at-api-report-verifier",
        "pure_python",
        "report_verifier",
        "Report Verifier",
        "Check 3-component completeness before download",
        timeout=60,
        retry=0,
    )
    _edge(export_node, verifier_node)

    # Layer 11 — OUTPUT
    out_node = _add_node(
        "at-api-output",
        "output",
        None,
        "📤 Output",
        "Download links + verification result",
        timeout=30,
        retry=0,
    )
    _edge(verifier_node, out_node)

    return {
        "template_id": "automation-testing-api",
        "name": "Automation Testing API",
        "description": (
            "API-only pipeline: MD spec → requirement enrichment → rule-based "
            "test case generation → executable filter → API execution → unit "
            "test files → final report → verified HTML/DOCX download"
        ),
        "version": 5,
        "is_builtin": False,
        "is_archived": False,
        "tags": ["automation-testing", "api", "md"],
        "nodes": nodes,
        "edges": edges,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fingerprint-guarded migration: upgrade an unchanged shipped v4 template to v5
# (adaptive-api-testing-pipeline). A user-customised DAG is never overwritten.
# ─────────────────────────────────────────────────────────────────────────────

# Fingerprint of the shipped v4 ``at-api-tc-generator`` node — the only thing
# the v5 migration changes. We match on the node's pre-upgrade identity so a
# DAG whose generator node a user has retitled/rewired is left untouched.
_SHIPPED_V4_TC_GENERATOR = {
    "node_id": "at-api-tc-generator",
    "agent_id": "api_test_case_generator",
    "node_type": "pure_python",
}


def _is_unchanged_shipped_v4_generator(nodes: list[dict[str, Any]]) -> bool:
    """True only when the generator node still matches the shipped v4 identity."""
    for node in nodes:
        if node.get("node_id") != _SHIPPED_V4_TC_GENERATOR["node_id"]:
            continue
        return all(
            node.get(key) == value
            for key, value in _SHIPPED_V4_TC_GENERATOR.items()
            if key != "node_id"
        )
    return False


async def migrate_automation_testing_api_to_v5() -> None:
    """Swap the rule-based generator node for the adaptive planner, in place.

    Idempotent and safe:
      * Fresh installs are seeded at v5 by :func:`seed_pipeline_templates`.
      * A deployed, unchanged v4 template is upgraded to v5 (node agent_id +
        label + timeout updated, version bumped).
      * A template at v5+ is a no-op.
      * A customised v4 DAG (generator node retitled/rewired) is left untouched
        with an actionable warning so an operator can migrate it deliberately.
    """
    template_id = "automation-testing-api"
    existing = await crud.get_pipeline_template(template_id)
    if existing is None:
        return  # seeding will create v5 directly

    data = existing.model_dump() if hasattr(existing, "model_dump") else dict(existing)
    current_version = int(data.get("version") or 0)
    if current_version >= 5:
        return  # already migrated

    nodes = data.get("nodes") or []
    if not _is_unchanged_shipped_v4_generator(nodes):
        logger.warning(
            "Template '%s' (v%d) has a customised test-case generator node; "
            "skipping automatic v5 adaptive-planner migration. Re-point the "
            "'at-api-tc-generator' node's agent_id to 'adaptive_api_test_planner' "
            "manually to adopt the multi-agent planner.",
            template_id, current_version,
        )
        return

    target = _build_automation_testing_api_template()
    # update_pipeline_template owns the version field (it auto-increments to
    # doc.version + 1), so we deliberately do not pass an explicit version —
    # an unchanged shipped v4 template therefore lands at v5.
    updated = await crud.update_pipeline_template(
        template_id,
        {
            "nodes": target["nodes"],
            "edges": target["edges"],
            "description": target["description"],
        },
    )
    new_version = getattr(updated, "version", current_version + 1)
    logger.info(
        "Migrated template '%s' v%d → v%d (adaptive multi-agent planner).",
        template_id, current_version, new_version,
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
    await seed_llm_profiles()
    await seed_agent_configs()
    await seed_stage_configs()
    await seed_pipeline_templates()  # NEW V3
