"use client";

/**
 * ValidatorFailureChecklist
 * ─────────────────────────
 * Renders a structured MD spec validation failure as a checklist with contract
 * guidance. Falls back to a plain error message for legacy runs / other
 * error_types.
 *
 * Used by PipelineRunPage to surface the MDSpecValidationErrorPayload returned
 * by the fail-fast validator guard node.
 */

import * as React from "react";
import { XCircle, AlertCircle } from "lucide-react";
import { cn } from "../../lib/utils";
import type { MDSpecValidationErrorPayload } from "../../types";

export interface ValidatorFailureChecklistProps {
  /** Parsed structured error; if null/undefined falls back to rawError. */
  structuredError?: MDSpecValidationErrorPayload | null;
  /** Raw error string shown when structuredError is absent. */
  rawError?: string | null;
  className?: string;
}

/** Parse the structured MD validation detail preserved by the API client. */
export function parseMDSpecValidationError(
  value: unknown,
): MDSpecValidationErrorPayload | null {
  let candidate = value;
  if (typeof candidate === "string") {
    try {
      candidate = JSON.parse(candidate);
    } catch {
      return null;
    }
  }
  if (
    candidate &&
    typeof candidate === "object" &&
    "error_type" in candidate &&
    candidate.error_type === "md_spec_validation"
  ) {
    return candidate as MDSpecValidationErrorPayload;
  }
  return null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Generic fallback
// ─────────────────────────────────────────────────────────────────────────────

function GenericError({ message }: { message: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-red-500/25 bg-red-500/[0.06] p-3">
      <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
      <p className="text-xs text-red-300 leading-relaxed font-mono whitespace-pre-wrap">
        {message}
      </p>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Checklist item
// ─────────────────────────────────────────────────────────────────────────────

function ChecklistItem({
  label,
  hint,
}: {
  label: string;
  hint?: string;
}) {
  return (
    <li className="flex items-start gap-2">
      <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0 mt-0.5" aria-hidden="true" />
      <div className="flex flex-col leading-snug">
        <span className="text-xs text-red-200 font-medium">{label}</span>
        {hint && (
          <span className="text-[11px] text-[#7a8baa] mt-0.5">{hint}</span>
        )}
      </div>
    </li>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function ValidatorFailureChecklist({
  structuredError,
  rawError,
  className,
}: ValidatorFailureChecklistProps) {
  // Prefer structured error, fall back to raw string
  if (!structuredError) {
    if (!rawError) return null;
    return (
      <div className={className}>
        <GenericError message={rawError} />
      </div>
    );
  }

  const { missing_sections = [], missing_fields = [], field_errors = [], detail } = structuredError;
  const hasItems = missing_sections.length > 0 || missing_fields.length > 0 || field_errors.length > 0;

  return (
    <div
      className={cn(
        "rounded-xl border border-red-500/25 bg-red-500/[0.04] p-4 space-y-3",
        className,
      )}
      role="alert"
      aria-label="Specification validation failure"
    >
      {/* Header */}
      <div className="flex items-center gap-2">
        <XCircle className="w-4 h-4 text-red-400 shrink-0" aria-hidden="true" />
        <p className="text-xs font-semibold text-red-300">
          Specification Validation Failed
        </p>
        <code className="ml-auto text-[10px] font-mono text-[#5e7196] bg-[#1e2a3d] px-1.5 py-0.5 rounded border border-[#2b3b55]">
          {structuredError.code}
        </code>
      </div>

      {/* Detail message */}
      <p className="text-[11px] text-[#92a4c9] leading-relaxed">{detail}</p>

      {/* Checklist of corrections required */}
      {hasItems && (
        <div className="space-y-2">
          {missing_sections.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-red-400/80 mb-1.5">
                Missing Sections ({missing_sections.length})
              </p>
              <ul className="space-y-1.5">
                {missing_sections.map((s) => (
                  <ChecklistItem
                    key={s}
                    label={s}
                    hint={`Add a section titled "${s}" to your document`}
                  />
                ))}
              </ul>
            </div>
          )}

          {missing_fields.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-red-400/80 mb-1.5">
                Missing Fields ({missing_fields.length})
              </p>
              <ul className="space-y-1.5">
                {missing_fields.map((f) => (
                  <ChecklistItem
                    key={f}
                    label={f}
                    hint="Required field must be present and non-empty"
                  />
                ))}
              </ul>
            </div>
          )}

          {field_errors.length > 0 && (
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-wider text-red-400/80 mb-1.5">
                Field Errors ({field_errors.length})
              </p>
              <ul className="space-y-1.5">
                {field_errors.map((fe, i) => (
                  <ChecklistItem
                    key={`${fe.field}-${i}`}
                    label={fe.field}
                    hint={
                      fe.message ??
                      ("detail" in fe && typeof fe.detail === "string"
                        ? fe.detail
                        : undefined)
                    }
                  />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ValidatorFailureChecklist;
