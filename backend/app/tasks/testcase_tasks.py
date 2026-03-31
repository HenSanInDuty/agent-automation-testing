from __future__ import annotations

"""
tasks/testcase_tasks.py
───────────────────────
Task-factory functions for the Test Case Generation crew (10 agents).

Each function accepts a CrewAI Agent (already built by AgentFactory) plus
any required input data and returns a ``crewai.Task`` instance.

Task execution order in TestcaseCrew (Sequential Process):
    1. requirement_analyzer   – analyse & enrich requirements
    2. scope_classifier       – classify test scope & risk
    3. data_model_agent       – build test data model
    4. rule_parser            – extract & formalise validation rules
    5. test_condition_agent   – apply EP & BVA to produce test conditions
    6. dependency_agent       – map requirement dependencies
    7. test_case_generator    – generate complete test cases
    8. automation_agent       – write automation scripts
    9. coverage_agent_pre     – pre-execution coverage analysis
   10. report_agent_pre       – test design report

Usage::

    from app.tasks.testcase_tasks import make_requirement_analyzer_task
    task = make_requirement_analyzer_task(agent, requirements_json)
"""

import json
import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

# ── Optional crewai import ────────────────────────────────────────────────────
try:
    from crewai import Task  # type: ignore[import-untyped]

    _CREWAI_AVAILABLE = True
except ImportError:
    Task = None  # type: ignore[assignment,misc]
    _CREWAI_AVAILABLE = False

if TYPE_CHECKING:
    from crewai import Agent  # type: ignore[import-untyped]
    from crewai import Task as TaskType  # type: ignore[import-untyped]


# ─────────────────────────────────────────────────────────────────────────────
# Guard helper
# ─────────────────────────────────────────────────────────────────────────────


def _require_crewai() -> None:
    if not _CREWAI_AVAILABLE or Task is None:
        raise ImportError(
            "crewai is not installed. "
            "On Linux/macOS run: uv add crewai. "
            "On Windows use Docker / WSL2 for Phase 2+ crew execution."
        )


def _compact_json(data: Any, max_items: int = 5) -> str:
    """
    Serialise *data* to a compact JSON string.
    If *data* is a list longer than *max_items*, only the first items are
    included and a summary line is appended to keep prompts manageable.
    """
    if isinstance(data, list) and len(data) > max_items:
        preview = data[:max_items]
        tail_count = len(data) - max_items
        return (
            json.dumps(preview, indent=2, ensure_ascii=False)
            + f"\n… and {tail_count} more items (omitted for brevity)"
        )
    return json.dumps(data, indent=2, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# Task 1 – Requirement Analyzer
# ─────────────────────────────────────────────────────────────────────────────


def make_requirement_analyzer_task(
    agent: "Agent",
    requirements_json: list[dict[str, Any]],
) -> "TaskType":
    """
    Task 1: Analyse and enrich raw requirements extracted by the Ingestion crew.

    Takes a list of raw ``RequirementItem`` dicts (from IngestionOutput) and
    produces a normalised, metadata-enriched version ready for downstream tasks.

    Args:
        agent:             The ``requirement_analyzer`` CrewAI Agent.
        requirements_json: List of raw requirement dicts from IngestionOutput.

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    req_count = len(requirements_json)
    reqs_str = _compact_json(requirements_json, max_items=8)

    return Task(
        description=f"""
You are analysing {req_count} software requirement(s) extracted from a user-provided
specification document. Your job is to enrich and normalise each requirement so that
all downstream test-generation agents have a clean, unambiguous foundation to work from.

For EACH requirement:
  1. Normalise the title to a concise noun phrase (≤ 15 words).
  2. Expand the description to be self-contained — add implied context but do NOT invent
     facts. If something is ambiguous, keep it and flag it in the ``notes`` field.
  3. Classify the type:
       functional        — a behaviour the system must exhibit
       non_functional    — a quality attribute (performance, security, usability, …)
       constraint        — a restriction on design or implementation
       assumption        — an assumed condition outside the system's control
  4. Assign priority: high | medium | low   (based on business impact language).
  5. Extract domain tags and technical keywords as a list of short strings.
  6. Flag any ambiguities, missing information, or conflicting statements in ``notes``.

Input requirements:
{reqs_str}

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {{
    "id": "REQ-001",
    "title": "<concise noun phrase>",
    "description": "<full, self-contained description>",
    "type": "functional|non_functional|constraint|assumption",
    "priority": "high|medium|low",
    "tags": ["tag1", "tag2"],
    "notes": "<ambiguities or empty string>"
  }}
]

IMPORTANT:
  - Preserve the original ``id`` field from the input.
  - Return EXACTLY {req_count} objects — one per input requirement.
  - Do NOT add markdown fences, prose, or explanation around the JSON.
""",
        expected_output=(
            f"A JSON array of {req_count} enriched requirement objects. "
            "Each object must have: id, title, description, type, priority, tags, notes."
        ),
        agent=agent,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 2 – Scope Classifier
# ─────────────────────────────────────────────────────────────────────────────


def make_scope_classifier_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 2: Classify each requirement by test layer, scenario categories, and risk.

    Uses the output of Task 1 (requirement_analyzer) via *context_tasks*.

    Args:
        agent:         The ``scope_classifier`` CrewAI Agent.
        context_tasks: List containing the requirement_analyzer task as context.

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Using the enriched requirements from the previous task, classify each requirement
for test planning purposes.

For EACH requirement, determine:

1. TEST LAYER — which test layer(s) this requirement primarily belongs to:
     api         — HTTP/REST API validation
     ui          — Browser/frontend UI interaction
     integration — Cross-service or cross-module integration
     unit        — Low-level unit/function behaviour

2. SCENARIO CATEGORIES — which test scenario categories are needed (pick all that apply):
     positive    — valid happy-path scenarios
     negative    — invalid inputs or forbidden actions
     edge_case   — unusual but valid boundary situations
     boundary    — values exactly at min/max limits

3. RISK LEVEL — business and technical risk:
     high   — failure has significant business impact or involves security/data integrity
     medium — moderate impact; recoverable failure
     low    — cosmetic or non-critical feature

4. ESTIMATED TEST COUNT — approximate number of test cases needed for this requirement
   (integer ≥ 1). High-risk requirements should receive proportionally more tests.

5. RATIONALE — 1–2 sentence justification for your risk and layer decisions.

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {
    "requirement_id": "REQ-001",
    "test_layer": "api|ui|integration|unit",
    "categories": ["positive", "negative"],
    "risk_level": "high|medium|low",
    "estimated_test_count": 5,
    "rationale": "<brief justification>"
  }
]

IMPORTANT:
  - Include one entry per requirement from the previous task.
  - Prefer "api" for backend requirements, "ui" for frontend/UX requirements.
  - Every requirement should have at least "positive" in categories.
  - High-risk requirements must also include "negative" and at least one of
    "edge_case" or "boundary".
  - Return ONLY the JSON array with no extra text.
""",
        expected_output=(
            "A JSON array with one scope classification object per requirement. "
            "Each object must have: requirement_id, test_layer, categories (array), "
            "risk_level, estimated_test_count, rationale."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 3 – Data Model Agent
# ─────────────────────────────────────────────────────────────────────────────


def make_data_model_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 3: Build a comprehensive test data model for all input fields.

    Uses outputs of Tasks 1–2 via *context_tasks*.

    Args:
        agent:         The ``data_model_agent`` CrewAI Agent.
        context_tasks: Context tasks (analyzer + scope classifier outputs).

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Using the enriched requirements and their scope classifications, build a comprehensive
test data model. For every API parameter, form field, or data entity mentioned in the
requirements, generate a structured set of test values covering:

  1. VALID VALUES:
       - typical realistic value (e.g. "alice@example.com" for email)
       - boundary-minimum value  (shortest/smallest allowed)
       - boundary-maximum value  (longest/largest allowed)

  2. INVALID VALUES:
       - null / None
       - empty string ""
       - wrong data type (e.g. string where integer expected)
       - out-of-range value (below min or above max)
       - excessively long string (e.g. 1000-char string)
       - special characters & Unicode (e.g. "'; DROP TABLE users;--", "日本語", emojis)
       - SQL injection pattern
       - XSS pattern

  3. METADATA:
       - data_type: string | integer | float | boolean | date | email | uuid | array | object
       - constraints: human-readable summary of the validation rules for this field

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {
    "entity": "<field or parameter name>",
    "requirement_id": "REQ-001",
    "data_type": "string|integer|float|boolean|date|email|uuid|array|object",
    "constraints": "<validation rules summary>",
    "valid_values": ["<typical>", "<boundary_min>", "<boundary_max>"],
    "invalid_values": [null, "", "<wrong_type>", "<out_of_range>", "<too_long>",
                       "<special_chars>", "<sql_injection>", "<xss>"],
    "notes": "<any caveats or open questions>"
  }
]

IMPORTANT:
  - Include at least one entry per testable field/parameter found in the requirements.
  - Each ``invalid_values`` list must contain at least 4 entries.
  - Null should appear as JSON null (not the string "null").
  - Return ONLY the JSON array with no extra text or markdown.
""",
        expected_output=(
            "A JSON array of test data model entries — one per testable field/parameter. "
            "Each entry must have: entity, requirement_id, data_type, constraints, "
            "valid_values (array ≥ 3 items), invalid_values (array ≥ 4 items), notes."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 4 – Rule Parser
# ─────────────────────────────────────────────────────────────────────────────


def make_rule_parser_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 4: Extract and formalise all validation rules from the requirements.

    Uses Tasks 1–3 outputs as context.

    Args:
        agent:         The ``rule_parser`` CrewAI Agent.
        context_tasks: Context tasks providing enriched requirements & data model.

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Parse every natural-language validation rule contained in the requirements and
convert each one into a precise, machine-readable constraint object.

Look for linguistic patterns such as:
  - "must be", "must not", "cannot", "shall", "is required"
  - "must be between X and Y", "cannot exceed N", "at least N characters"
  - "must match pattern", "must be unique", "must be one of [A, B, C]"
  - "is only allowed when", "depends on", "is mutually exclusive with"

For EACH rule found, produce:

  RULE FIELDS:
    rule_id        – sequential identifier: RULE-001, RULE-002, …
    requirement_id – which requirement this rule comes from
    rule_type      – one of:
                       format        — pattern/regex constraint
                       range         — min/max numeric or length constraint
                       required      — field presence constraint
                       unique        — uniqueness constraint
                       dependency    — rule that applies conditionally on another field
                       business_logic — domain-specific business rule
                       enum          — value must be from a fixed set
    description    – plain-English restatement of the rule
    formal_expression – pseudo-code or regex that precisely captures the rule
                        (e.g. "len(value) >= 8 and len(value) <= 100",
                              "re.match(r'^[a-zA-Z0-9_]+$', value)")
    violation_message – the error message a user/system should receive if broken

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {
    "rule_id": "RULE-001",
    "requirement_id": "REQ-001",
    "rule_type": "format|range|required|unique|dependency|business_logic|enum",
    "description": "<plain-English restatement>",
    "formal_expression": "<pseudo-code or regex>",
    "violation_message": "<error message when rule is broken>"
  }
]

IMPORTANT:
  - Every field constraint from the data model should map to at least one rule.
  - If a constraint yields multiple rules (e.g. "must be 8–100 chars"),
    create separate RULE entries for the lower and upper bounds.
  - Return ONLY the JSON array with no markdown or extra text.
""",
        expected_output=(
            "A JSON array of formalised rule objects. Each object must have: "
            "rule_id, requirement_id, rule_type, description, "
            "formal_expression, violation_message."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 5 – Test Condition Agent
# ─────────────────────────────────────────────────────────────────────────────


def make_test_condition_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 5: Apply equivalence partitioning and boundary value analysis to
    produce atomic test conditions.

    Uses Tasks 1–4 outputs as context.

    Args:
        agent:         The ``test_condition_agent`` CrewAI Agent.
        context_tasks: Context tasks (requirements, scope, data model, rules).

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Apply two standard testing techniques to every rule and data-model entry in order
to produce a complete, non-redundant set of ATOMIC test conditions.

TECHNIQUE 1 — EQUIVALENCE PARTITIONING (EP):
  Divide each input domain into classes where all values in a class are
  expected to behave identically. Identify:
    - Valid equivalence class (VEC)  — inputs the system should accept
    - Invalid equivalence class (IEC) — inputs the system should reject

TECHNIQUE 2 — BOUNDARY VALUE ANALYSIS (BVA):
  For every range or length constraint, generate conditions at:
    - min        (e.g. exactly at minimum allowed)
    - min - 1    (one below minimum — invalid)
    - max        (exactly at maximum allowed)
    - max + 1    (one above maximum — invalid)

For each condition, record:
  condition_id    – sequential identifier: COND-001, COND-002, …
  rule_id         – which rule or data-model entity this condition tests
  condition_type  – one of:
                      valid_partition     — a valid equivalence class representative
                      invalid_partition   — an invalid equivalence class representative
                      boundary_min        — value exactly at lower bound (valid)
                      boundary_min_minus1 — value one below lower bound (invalid)
                      boundary_max        — value exactly at upper bound (valid)
                      boundary_max_plus1  — value one above upper bound (invalid)
  description     – what this condition tests, in plain English
  test_data       – the specific value or example to use (string representation)
  expected_behavior – "accept" if the system should process this input,
                      "reject"  if the system should return an error

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {
    "condition_id": "COND-001",
    "rule_id": "RULE-001",
    "condition_type": "valid_partition|invalid_partition|boundary_min|boundary_min_minus1|boundary_max|boundary_max_plus1",
    "description": "<what this condition tests>",
    "test_data": "<specific value>",
    "expected_behavior": "accept|reject"
  }
]

IMPORTANT:
  - Every rule must have at least one valid_partition AND one invalid_partition condition.
  - Range/length rules must additionally have all four BVA boundary conditions.
  - Conditions must be atomic: each tests exactly one aspect of one rule.
  - Return ONLY the JSON array with no markdown, prose, or explanation.
""",
        expected_output=(
            "A JSON array of atomic test conditions derived from EP and BVA. "
            "Each object must have: condition_id, rule_id, condition_type, "
            "description, test_data, expected_behavior."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 6 – Dependency Agent
# ─────────────────────────────────────────────────────────────────────────────


def make_dependency_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 6: Map dependencies between requirements and determine test execution order.

    Uses Tasks 1–5 outputs as context.

    Args:
        agent:         The ``dependency_agent`` CrewAI Agent.
        context_tasks: Context tasks (requirements, scope, data model, rules, conditions).

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Analyse all requirements and identify dependency relationships that affect
how test cases must be ordered during execution.

DEPENDENCY TYPES to identify:
  prerequisite    — Req A cannot be tested until Req B is verified
                    (e.g. "login" must pass before "view profile" is tested)
  data_dependency — Req A's test needs data created by Req B's test
                    (e.g. "edit user" needs a user created by "create user" test)
  sequence        — Req A and Req B represent a workflow where order matters
                    but both can be tested independently
  exclusion       — Req A and Req B test mutually exclusive features;
                    they must NOT be combined in the same test run

For each dependency found, record:
  source_req          – the requirement that depends on another
  target_req          – the requirement that must be satisfied first
  dependency_type     – one of the four types above
  description         – plain-English explanation
  test_ordering_impact – how this dependency affects the test execution order

Additionally, derive:
  execution_order     – a flat, topologically-sorted list of requirement IDs
                        (requirements with no dependencies first)
  independent_groups  – groups of requirements that have no dependencies between
                        them and can be tested in parallel
                        (array of arrays of requirement IDs)

OUTPUT FORMAT — respond with a single JSON object and NOTHING else:
{
  "dependencies": [
    {
      "source_req": "REQ-002",
      "target_req": "REQ-001",
      "dependency_type": "prerequisite|data_dependency|sequence|exclusion",
      "description": "<plain-English explanation>",
      "test_ordering_impact": "<how this affects test execution order>"
    }
  ],
  "execution_order": ["REQ-001", "REQ-003", "REQ-002"],
  "independent_groups": [["REQ-001", "REQ-003"], ["REQ-002"]]
}

IMPORTANT:
  - If there are no dependencies, return an empty ``dependencies`` array and
    list all requirements in both ``execution_order`` and one ``independent_group``.
  - Return ONLY the JSON object with no markdown, prose, or explanation.
""",
        expected_output=(
            "A JSON object with keys: dependencies (array of dependency objects), "
            "execution_order (array of requirement IDs in safe execution order), "
            "independent_groups (array of arrays for parallel execution)."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 7 – Test Case Generator
# ─────────────────────────────────────────────────────────────────────────────


def make_test_case_generator_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 7: Generate the actual test cases using all prior analysis.

    This is the core task of the TestcaseCrew, consuming all previous task
    outputs to produce complete, actionable test cases.

    Args:
        agent:         The ``test_case_generator`` CrewAI Agent.
        context_tasks: All prior tasks (1–6) as context.

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Using ALL previous analysis (enriched requirements, scope classifications, test data
model, formalised rules, test conditions, and dependency map), generate COMPLETE and
ACTIONABLE test cases.

Each test case must be:
  - TRACEABLE   — links to exactly one requirement via ``requirement_id``
  - ATOMIC       — tests exactly one behaviour or condition
  - SELF-CONTAINED — includes all setup information needed to run it
  - COMPLETE      — has unambiguous steps and a verifiable expected result

REQUIRED FIELDS for every test case:
  id               – TC-001, TC-002, … (sequential)
  requirement_id   – maps to a RequirementItem id (e.g. REQ-001)
  title            – concise action phrase (e.g. "POST /users with valid data → 201")
  description      – brief description of what this test verifies
  preconditions    – any setup state required before executing the test
  steps            – ordered list of actions with step_number, action, expected_result
  expected_result  – the overall acceptance criterion for the entire test case
  test_type        – api | ui | integration | unit
  category         – positive | negative | edge_case | boundary
  priority         – high | medium | low

ADDITIONAL FIELDS for API tests (include whenever applicable):
  api_endpoint     – relative path (e.g. "/api/v1/users")
  http_method      – GET | POST | PUT | PATCH | DELETE
  request_headers  – dict of headers to include (omit if only standard headers needed)
  request_body     – JSON body as a dict (null for GET/DELETE)
  expected_status_code – expected HTTP status code (e.g. 200, 201, 400, 401, 404)

ADDITIONAL FIELDS for UI tests:
  ui_page          – page or route being tested (e.g. "/login")
  ui_selector      – CSS selector or element description for the primary UI element

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {
    "id": "TC-001",
    "requirement_id": "REQ-001",
    "title": "<concise action phrase>",
    "description": "<what this test verifies>",
    "preconditions": "<required setup state or 'None'>",
    "steps": [
      {"step_number": 1, "action": "<what to do>", "expected_result": "<what should happen>"}
    ],
    "expected_result": "<overall acceptance criterion>",
    "test_type": "api|ui|integration|unit",
    "category": "positive|negative|edge_case|boundary",
    "priority": "high|medium|low",
    "tags": ["<tag>"],
    "api_endpoint": "/api/v1/...",
    "http_method": "GET|POST|PUT|PATCH|DELETE",
    "request_headers": null,
    "request_body": null,
    "expected_status_code": 200
  }
]

IMPORTANT:
  - Generate test cases for ALL test conditions produced in Task 5.
  - Respect the dependency execution order from Task 6 when numbering test cases.
  - Return ONLY the JSON array with no markdown or extra explanation.
""",
        expected_output=(
            "A JSON array of complete test case objects. Each object must have at minimum: "
            "id, requirement_id, title, description, preconditions, steps (array with "
            "step_number/action/expected_result), expected_result, test_type, category, "
            "priority. API tests must also include api_endpoint, http_method, "
            "request_body, expected_status_code."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 8 – Automation Agent
# ─────────────────────────────────────────────────────────────────────────────


def make_automation_agent_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 8: Generate Python automation scripts for each test case.

    Uses all prior tasks as context, especially the test cases from Task 7.

    Args:
        agent:         The ``automation_agent`` CrewAI Agent.
        context_tasks: All prior tasks as context.

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
For every test case generated in the previous task, write an executable Python
automation script using the pytest + httpx stack (for API tests) or
pytest + playwright (for UI tests).

SCRIPT REQUIREMENTS:
  1. Each script must be importable and executable with `pytest` without modification
     (except replacing BASE_URL with the actual endpoint).
  2. Include all required imports at the top.
  3. Use a ``BASE_URL`` constant that defaults to ``os.getenv("TEST_BASE_URL", "http://localhost:8000")``.
  4. Each test function is named ``test_<id_lower>`` (e.g. ``test_tc001``).
  5. Use ``assert`` statements to validate:
       - HTTP status code
       - Response body fields (where specified in the test case)
       - Any other acceptance criteria
  6. Include inline comments explaining each non-trivial step.
  7. Add docstring to each test function with: test case title, requirement ID, category.

AUTOMATION SCRIPT OBJECT:
  test_case_id        – e.g. "TC-001"
  language            – "python"
  framework           – "pytest_httpx" | "pytest_playwright"
  script              – full Python source code as a single string
  imports_required    – list of pip package names needed (e.g. ["httpx", "pytest"])
  estimated_duration_ms – rough execution time estimate in milliseconds

OUTPUT FORMAT — respond with a JSON array and NOTHING else:
[
  {
    "test_case_id": "TC-001",
    "language": "python",
    "framework": "pytest_httpx|pytest_playwright",
    "script": "import os\\nimport httpx\\nimport pytest\\n\\nBASE_URL = os.getenv(\\"TEST_BASE_URL\\", \\"http://localhost:8000\\")\\n\\n\\ndef test_tc001():\\n    \\"\\"\\"TC-001: ...\\"\\"\\"\\n    ...",
    "imports_required": ["httpx", "pytest"],
    "estimated_duration_ms": 500
  }
]

IMPORTANT:
  - Generate a script entry for EVERY test case from the previous task.
  - Escape all double-quotes inside the ``script`` string value with \\".
  - Escape all newlines inside the ``script`` string value with \\n.
  - Return ONLY the JSON array with no markdown or extra explanation.
""",
        expected_output=(
            "A JSON array of automation script objects — one per test case. "
            "Each object must have: test_case_id, language, framework, "
            "script (executable Python source), imports_required, estimated_duration_ms."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 9 – Coverage Agent (Pre-execution)
# ─────────────────────────────────────────────────────────────────────────────


def make_coverage_pre_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 9: Pre-execution coverage analysis of the generated test suite.

    Computes coverage metrics against the original requirements before any
    test execution takes place.

    Args:
        agent:         The ``coverage_agent_pre`` CrewAI Agent.
        context_tasks: All prior tasks as context.

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Analyse the generated test suite against the original requirements to calculate
pre-execution coverage metrics. This is a design-time quality check performed
before any tests are actually run.

COVERAGE DIMENSIONS to compute:

  1. REQUIREMENT COVERAGE
       - total_requirements     : how many requirements were analysed
       - covered_requirements   : how many have at least one test case
       - coverage_percentage    : (covered / total) × 100 rounded to 1 decimal
       - uncovered_requirements : list of requirement IDs with zero test cases

  2. CATEGORY COVERAGE
       For each requirement, check whether all relevant categories from the scope
       classification (positive / negative / edge_case / boundary) have at least
       one test case. List any gaps.

  3. RISK COVERAGE
       - Are all HIGH-risk requirements covered?
       - Do high-risk requirements have proportionally more test cases than low-risk ones?
       - List any high-risk requirements with fewer than 3 test cases.

  4. AUTOMATION COVERAGE
       - total_automated         : test cases that have an automation script
       - automation_percentage   : (automated / total_test_cases) × 100

  5. COVERAGE GAPS — list any specific gaps identified (e.g.
       "REQ-003 has no negative test cases", "REQ-007 is uncovered entirely")

OUTPUT FORMAT — respond with a single JSON object and NOTHING else:
{
  "total_requirements": 10,
  "covered_requirements": 9,
  "coverage_percentage": 90.0,
  "uncovered_requirements": ["REQ-005"],
  "total_test_cases": 25,
  "by_type": {"functional": 7, "non_functional": 2},
  "by_priority": {"high": 5, "medium": 3, "low": 1},
  "by_category": {"positive": 15, "negative": 10, "edge_case": 5, "boundary": 8},
  "total_automated": 20,
  "automation_percentage": 80.0,
  "risk_coverage": {
    "high_risk_covered": true,
    "high_risk_requirements": ["REQ-001", "REQ-003"],
    "under_tested_high_risk": []
  },
  "coverage_gaps": ["REQ-005 has no test cases of any type"]
}

IMPORTANT:
  - Compute all percentages mathematically from the actual test case data.
  - Return ONLY the JSON object with no markdown or extra explanation.
""",
        expected_output=(
            "A JSON coverage metrics object with: total_requirements, covered_requirements, "
            "coverage_percentage, uncovered_requirements, total_test_cases, by_type, "
            "by_priority, by_category, total_automated, automation_percentage, "
            "risk_coverage, coverage_gaps."
        ),
        agent=agent,
        context=context_tasks,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Task 10 – Report Agent (Pre-execution / Design Report)
# ─────────────────────────────────────────────────────────────────────────────


def make_report_pre_task(
    agent: "Agent",
    context_tasks: list["TaskType"],
) -> "TaskType":
    """
    Task 10: Produce the test design report summarising all prior analysis.

    This is the final task of the TestcaseCrew and its output becomes the
    ``TestCaseOutput`` stored in the database.

    Args:
        agent:         The ``report_agent_pre`` CrewAI Agent.
        context_tasks: All prior tasks as context (tasks 1–9).

    Returns:
        A ``crewai.Task`` instance.
    """
    _require_crewai()

    return Task(
        description="""
Produce the final test design report that consolidates ALL previous agent outputs
into a single comprehensive JSON document. This report will be stored in the database
and displayed to the user via the frontend dashboard.

The report must be COMPLETE — it should include the actual test cases and all
analysis artifacts, not just summary statistics.

REQUIRED TOP-LEVEL FIELDS:

  test_cases          – the complete array of test cases from Task 7
                        (include every test case with all its fields)
  total_test_cases    – integer count of test cases
  coverage_summary    – the coverage metrics object from Task 9
  automation_readiness – summary of automation script generation:
                          { total_automated, automation_percentage, frameworks_used }
  design_notes        – list of important observations, warnings, or recommendations
                        noted during the design phase (strings)
  risks               – list of identified risk items:
                        e.g. "REQ-003 has only 1 test case despite HIGH risk rating"
  recommendations     – list of actionable recommendations for the QA team:
                        e.g. "Add negative test cases for REQ-007 input validation"
  executive_summary   – 3–4 sentence overview suitable for a non-technical stakeholder

OUTPUT FORMAT — respond with a single JSON object and NOTHING else:
{
  "executive_summary": "<3-4 sentence stakeholder-friendly summary>",
  "test_cases": [ ... ],
  "total_test_cases": 25,
  "coverage_summary": { ... },
  "automation_readiness": {
    "total_automated": 20,
    "automation_percentage": 80.0,
    "frameworks_used": ["pytest_httpx"]
  },
  "design_notes": ["..."],
  "risks": ["..."],
  "recommendations": ["..."]
}

IMPORTANT:
  - ``test_cases`` must contain the FULL array from Task 7, not a subset or summary.
  - ``coverage_summary`` must be the EXACT object from Task 9.
  - Design notes, risks, and recommendations must be actionable and specific.
  - Return ONLY the JSON object with no markdown fences or extra explanation.
""",
        expected_output=(
            "A JSON object with: executive_summary, test_cases (full array), "
            "total_test_cases, coverage_summary, automation_readiness, "
            "design_notes, risks, recommendations."
        ),
        agent=agent,
        context=context_tasks,
    )
