/**
 * Unit tests for ValidatorFailureChecklist component.
 *
 * NOTE: No test runner is configured in this repo yet (no vitest/jest setup).
 * These tests are written for vitest + @testing-library/react.
 * To run: add vitest + jsdom + @testing-library/react to packages/shared,
 * then run `vitest run` from packages/shared.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import {
  ValidatorFailureChecklist,
  parseMDSpecValidationError,
} from "../ValidatorFailureChecklist";
import type { MDSpecValidationErrorPayload } from "../../../types";

const baseError: MDSpecValidationErrorPayload = {
  error_type: "md_spec_validation",
  code: "MD_SPEC_MISSING_FIELDS",
  missing_sections: ["API Overview"],
  missing_fields: ["base_url", "authentication_method"],
  field_errors: [{ field: "endpoints", message: "At least one endpoint required" }],
  detail: "The specification document is missing required fields.",
};

describe("ValidatorFailureChecklist", () => {
  it("parses structured validation detail from an Error message", () => {
    expect(parseMDSpecValidationError(JSON.stringify(baseError))).toEqual(baseError);
  });

  it("ignores a generic error message", () => {
    expect(parseMDSpecValidationError("Network request failed")).toBeNull();
  });

  it("renders nothing when no error is provided", () => {
    const { container } = render(<ValidatorFailureChecklist />);
    expect(container.firstChild).toBeNull();
  });

  it("shows generic error for rawError when no structuredError", () => {
    render(<ValidatorFailureChecklist rawError="Pipeline failed unexpectedly." />);
    expect(screen.getByText("Pipeline failed unexpectedly.")).toBeDefined();
  });

  it("renders error code badge", () => {
    render(<ValidatorFailureChecklist structuredError={baseError} />);
    expect(screen.getByText("MD_SPEC_MISSING_FIELDS")).toBeDefined();
  });

  it("renders detail message", () => {
    render(<ValidatorFailureChecklist structuredError={baseError} />);
    expect(
      screen.getByText("The specification document is missing required fields."),
    ).toBeDefined();
  });

  it("renders missing section as checklist item", () => {
    render(<ValidatorFailureChecklist structuredError={baseError} />);
    expect(screen.getByText("API Overview")).toBeDefined();
  });

  it("renders missing fields as checklist items", () => {
    render(<ValidatorFailureChecklist structuredError={baseError} />);
    expect(screen.getByText("base_url")).toBeDefined();
    expect(screen.getByText("authentication_method")).toBeDefined();
  });

  it("renders field error with message hint", () => {
    render(<ValidatorFailureChecklist structuredError={baseError} />);
    expect(screen.getByText("endpoints")).toBeDefined();
    expect(screen.getByText("At least one endpoint required")).toBeDefined();
  });

  it("renders FastAPI field error detail hints", () => {
    const backendError = {
      ...baseError,
      field_errors: [
        {
          field: "endpoint.method",
          code: "MD_SPEC_MISSING_ENDPOINT",
          detail: "Endpoint method is required.",
        },
      ],
    } as unknown as MDSpecValidationErrorPayload;
    render(<ValidatorFailureChecklist structuredError={backendError} />);
    expect(screen.getByText("Endpoint method is required.")).toBeDefined();
  });

  it("shows counts in section headers", () => {
    render(<ValidatorFailureChecklist structuredError={baseError} />);
    expect(screen.getByText(/Missing Sections \(1\)/i)).toBeDefined();
    expect(screen.getByText(/Missing Fields \(2\)/i)).toBeDefined();
    expect(screen.getByText(/Field Errors \(1\)/i)).toBeDefined();
  });

  it("renders gracefully when no items (detail only)", () => {
    const noItems: MDSpecValidationErrorPayload = {
      error_type: "md_spec_validation",
      code: "MD_SPEC_EMPTY",
      detail: "Document appears to be empty.",
    };
    render(<ValidatorFailureChecklist structuredError={noItems} />);
    expect(screen.getByText("Document appears to be empty.")).toBeDefined();
    // No section headers when counts are 0
    expect(screen.queryByText(/Missing Sections/i)).toBeNull();
  });

  it("prefers structuredError over rawError when both provided", () => {
    render(
      <ValidatorFailureChecklist
        structuredError={baseError}
        rawError="fallback error text"
      />,
    );
    // Structured UI renders (code badge visible)
    expect(screen.getByText("MD_SPEC_MISSING_FIELDS")).toBeDefined();
    // Raw fallback not rendered
    expect(screen.queryByText("fallback error text")).toBeNull();
  });
});
