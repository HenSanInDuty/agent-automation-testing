/**
 * Unit tests for PlanningReviewSummary component.
 *
 * NOTE: No test runner is configured in this repo yet (no vitest/jest setup).
 * These tests are written for vitest + @testing-library/react.
 * To run: add vitest + jsdom + @testing-library/react to packages/shared,
 * then run `vitest run` from packages/shared.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { PlanningReviewSummary } from "../PlanningReviewSummary";
import type { PlannerComplexity, PlannerReviewGate } from "../../../types";

const baseComplexity: PlannerComplexity = {
  score: 3.5,
  signals: { api_count: 2, auth_complexity: 1 },
  agent_count: 3,
  selected_roles: ["positive", "negative_schema", "auth_security"],
  rationale: "Medium API surface with auth present.",
};

const baseReviewGate: PlannerReviewGate = {
  coverage_threshold_percent: 90,
  max_review_iterations: 3,
  continue_on_exhaustion: true,
  iterations: [
    {
      iteration: 1,
      case_count: 12,
      coverage: {
        total_required: 10,
        covered_required: 9,
        coverage_percent: 90,
        gaps: [],
        unknown_obligation_ids: [],
      },
      review: { verdict: "approve", evidence: "Coverage sufficient." },
      accepted: true,
    },
  ],
  selected_iteration: 1,
  final_coverage_percent: 90,
  final_verdict: "approve",
  accepted: true,
  coverage_gate_exhausted: false,
  warnings: [],
};

describe("PlanningReviewSummary", () => {
  it("renders nothing when no planning data is provided", () => {
    const { container } = render(<PlanningReviewSummary />);
    expect(container.firstChild).toBeNull();
  });

  it("renders agent count from complexity", () => {
    // "3" is styled in a nested span, so the phrase spans multiple text nodes;
    // assert on the rendered container's combined text content.
    const { container } = render(<PlanningReviewSummary complexity={baseComplexity} />);
    expect(container.textContent).toContain("3 agents selected");
  });

  it("renders complexity score", () => {
    render(<PlanningReviewSummary complexity={baseComplexity} />);
    expect(screen.getByText(/3\.5/)).toBeDefined();
  });

  it("renders selected roles as chips", () => {
    render(<PlanningReviewSummary complexity={baseComplexity} />);
    expect(screen.getByText("positive")).toBeDefined();
    expect(screen.getByText("negative_schema")).toBeDefined();
  });

  it("renders final coverage percent and threshold", () => {
    render(<PlanningReviewSummary reviewGate={baseReviewGate} />);
    expect(screen.getByText(/90\.0%/)).toBeDefined();
    expect(screen.getByText(/90% req\./)).toBeDefined();
  });

  it("renders approve verdict badge", () => {
    render(<PlanningReviewSummary reviewGate={baseReviewGate} />);
    expect(screen.getByText("Approve")).toBeDefined();
  });

  it("shows exhaustion warning when coverage_gate_exhausted is true", () => {
    const exhaustedGate: PlannerReviewGate = {
      ...baseReviewGate,
      coverage_gate_exhausted: true,
    };
    render(<PlanningReviewSummary reviewGate={exhaustedGate} />);
    expect(screen.getByText(/review gate exhausted/i)).toBeDefined();
  });

  it("does not show exhaustion warning when not exhausted", () => {
    render(<PlanningReviewSummary reviewGate={baseReviewGate} />);
    expect(screen.queryByText(/review gate exhausted/i)).toBeNull();
  });

  it("renders planner warnings", () => {
    render(
      <PlanningReviewSummary plannerWarnings={["Coverage gap: POST /auth"]} />,
    );
    expect(screen.getByText("Coverage gap: POST /auth")).toBeDefined();
  });
});
