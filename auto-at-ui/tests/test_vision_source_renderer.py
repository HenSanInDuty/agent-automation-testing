import asyncio
import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from agents.generation.vision_plan import plan_vision_test
from application.vision_source_renderer import locator_expression, render_vision_source
from auto_at.contracts.generation import (
    TestGenerationPlanningRequest as PlanningRequest,
)
from auto_at.contracts.generation import (
    VisionGroundedPlannerOutput,
    VisionPlanningSource,
    request_hash,
)
from auto_at.contracts.vision import VisualLocatorDescriptor, VisualLocatorScope
from test_vision_handoff import branch_fixture
from vision_trace_fixtures import evolve


def selection(package, **changes):
    return VisionGroundedPlannerOutput.model_validate(
        dict(
            title="Observed controls",
            selected_branch_ids=[b.id for b in package.branches if b.status == "ready"],
        )
        | changes
    )


def test_rendering_uses_verified_locator_per_sibling_and_records_provenance():
    _, snapshot, package = branch_fixture()
    output, refs = render_vision_source(
        selection(package), package, snapshot, {}, "https://fixture.test/"
    )
    source = output.playwright_test_source
    assert source.count("test(") == 2 and source.count("active.goto(") == 2
    tests = source.split("test(")[1:]
    assert 'name: "Branch A"' in tests[0] and "Branch B" not in tests[0]
    assert 'name: "Branch B"' in tests[1] and "Branch A" not in tests[1]
    assert refs == [o.id for o in snapshot["operations"]]
    assert "business outcomes remain unverified" in output.stop_conditions[0]


@pytest.mark.parametrize(
    "strategy,value,role,method",
    [
        ("role", 'Save "quoted" \\ value', "button", "getByRole"),
        ("label", "Full name", None, "getByLabel"),
        ("test_id", "submit", None, "getByTestId"),
        ("css", '[id="submit"]', None, "locator"),
    ],
)
def test_descriptor_strategies_are_escaped_and_scoped(strategy, value, role, method):
    descriptor = VisualLocatorDescriptor(
        strategy=strategy,
        value=value,
        role=role,
        scope=(
            VisualLocatorScope(kind="iframe", selector='[id="frame"]'),
            VisualLocatorScope(kind="shadow", selector='[id="host"]'),
        ),
    )
    expression = locator_expression(descriptor)
    assert '.frameLocator("[id=\\"frame\\"]").locator("[id=\\"host\\"]")' in expression
    assert f".{method}(" in expression and json.dumps(value) in expression


@pytest.mark.parametrize(
    "bad", ["unknown_branch", "reorder", "omit", "assertion", "sibling", "locator"]
)
def test_untrusted_or_mismatched_references_never_render(bad):
    _, snapshot, package = branch_fixture()
    planned = selection(package)
    if bad == "unknown_branch":
        planned.selected_branch_ids = [uuid4()]
    elif bad == "reorder":
        planned.selected_branch_ids.reverse()
    elif bad == "omit":
        planned.selected_branch_ids.pop()
    elif bad == "assertion":
        planned = selection(
            package,
            assertions=[
                dict(
                    branch_id=package.branches[0].id,
                    operation_id=uuid4(),
                    locator_id=uuid4(),
                    kind="visible",
                )
            ],
        )
    elif bad == "sibling":
        root, left, right = snapshot["operations"]
        snapshot["operations"] = (root, left, evolve(right, parent_operation_id=left.id))
    else:
        snapshot["locators"] = ()
    with pytest.raises(ValueError):
        render_vision_source(planned, package, snapshot, {}, "https://fixture.test/")


def test_model_can_only_select_refs_and_budget_failure_precedes_provider():
    scope, _, package = branch_fixture()
    request = PlanningRequest(
        correlation_id=uuid4(),
        project_id=scope.project_id,
        target_url="https://fixture.test/",
        redacted_request="Check",
        request_hash=request_hash("Check"),
        vision_source=VisionPlanningSource(
            session_id=scope.session_id, handoff_id=package.id, handoff_hash=package.content_hash
        ),
    )

    class Model:
        calls = 0

        async def ainvoke(self, payload, **kwargs):
            self.calls += 1
            assert "untrusted data" in payload["messages"][0]["content"]
            return {"choices": [{"message": {"content": selection(package).model_dump_json()}}]}

    model = Model()
    with pytest.raises(ValueError, match="evidence_budget"):
        asyncio.run(plan_vision_test(model, request, package, 1000, 1))
    assert model.calls == 0
    assert asyncio.run(plan_vision_test(model, request, package, 1000, 100_000)).title
    with pytest.raises(ValueError):
        selection(package, playwright_test_source="untrusted")


def test_rendered_source_loads_in_pinned_playwright(tmp_path):
    _, snapshot, package = branch_fixture(names=('Save "quote" \\ path', "B ` ${inert}"))
    output, _ = render_vision_source(
        selection(package), package, snapshot, {}, "https://fixture.test/"
    )
    worker = Path("workers/playwright").resolve()
    source = tmp_path / "grounded.spec.ts"
    source.write_text(output.playwright_test_source, encoding="utf-8")
    # Resolve the existing pinned worker dependency, never install a package.
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "'@playwright/test'",
            json.dumps((worker / "node_modules/@playwright/test/index.mjs").as_posix()),
        ),
        encoding="utf-8",
    )
    config = tmp_path / "fixture.config.cjs"
    config.write_text("module.exports = { testDir: '.', reporter: 'list' };", encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(worker / "node_modules/@playwright/test/cli.js"),
            "test",
            "--list",
            "--config",
            str(config),
        ],
        cwd=worker,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 tests" in result.stdout
