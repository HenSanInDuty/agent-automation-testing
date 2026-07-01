"use client";

/**
 * PlanningReviewSummary
 * ─────────────────────
 * Additive component rendered inside ResultsViewer when the adaptive test
 * planner node has run. Shows complexity, selected agents, review iterations,
 * coverage score, senior verdict, and exhaustion warning.
 *
 * All props are optional — renders nothing when no planning data is present.
 * Does NOT change ResultsViewer public props.
 */

import * as React from "react";
import { AlertTriangle, CheckCircle2, XCircle, Users, BarChart3, RefreshCw } from "lucide-react";
import { cn } from "../../lib/utils";
import type { PlannerComplexity, PlannerReviewGate } from "../../types";

export interface PlanningReviewSummaryProps {
  complexity?: PlannerComplexity | null;
  reviewGate?: PlannerReviewGate | null;
  plannerWarnings?: string[];
  /** Extra class applied to the root element. */
  className?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Verdict badge
// ─────────────────────────────────────────────────────────────────────────────

function VerdictBadge({ verdict }: { verdict: "approve" | "revise" | "reject" | null | undefined }) {
  if (!verdict) return null;
  const styles = {
    approve: "bg-emerald-500/10 text-emerald-300 border-emerald-500/25",
    revise: "bg-yellow-500/10 text-yellow-300 border-yellow-500/25",
    reject: "bg-red-500/10 text-red-300 border-red-500/25",
  };
  const Icon = verdict === "approve" ? CheckCircle2 : verdict === "reject" ? XCircle : AlertTriangle;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium border",
        styles[verdict],
      )}
    >
      <Icon className="w-3 h-3" aria-hidden="true" />
      {verdict.charAt(0).toUpperCase() + verdict.slice(1)}
    </span>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Main component
// ─────────────────────────────────────────────────────────────────────────────

export function PlanningReviewSummary({
  complexity,
  reviewGate,
  plannerWarnings,
  className,
}: PlanningReviewSummaryProps) {
  // Render nothing when no planning metadata is present (legacy runs)
  if (!complexity && !reviewGate && (!plannerWarnings || plannerWarnings.length === 0)) {
    return null;
  }

  const iterationCount = reviewGate?.iterations?.length ?? 0;
  const finalCoverage = reviewGate?.final_coverage_percent;
  const threshold = reviewGate?.coverage_threshold_percent;
  const exhausted = reviewGate?.coverage_gate_exhausted === true;
  const warnings = [
    ...(plannerWarnings ?? []),
    ...(reviewGate?.warnings ?? []),
  ];

  return (
    <div
      className={cn(
        "rounded-xl border border-[#2b3b55] bg-[#141c2c]/60 p-4 space-y-3",
        className,
      )}
      aria-label="Planning and review summary"
    >
      <div className="flex items-center gap-2 mb-1">
        <RefreshCw className="w-3.5 h-3.5 text-[#92a4c9]" aria-hidden="true" />
        <h4 className="text-xs font-semibold text-[#92a4c9] uppercase tracking-wider">
          Planning Summary
        </h4>
      </div>

      {/* ── Complexity / Agents ────────────────────────────────────────────── */}
      {complexity && (
        <div className="flex flex-wrap gap-3">
          <div className="flex items-center gap-1.5">
            <Users className="w-3.5 h-3.5 text-[#5b9eff]" aria-hidden="true" />
            <span className="text-xs text-[#92a4c9]">
              <span className="text-white font-medium">{complexity.agent_count}</span>
              {" agents selected"}
            </span>
          </div>
          <div className="flex items-center gap-1.5">
            <BarChart3 className="w-3.5 h-3.5 text-[#5b9eff]" aria-hidden="true" />
            <span className="text-xs text-[#92a4c9]">
              Complexity score{" "}
              <span className="text-white font-medium">{complexity.score.toFixed(1)}</span>
            </span>
          </div>
          {complexity.selected_roles.length > 0 && (
            <div className="flex flex-wrap gap-1">
              {complexity.selected_roles.map((role) => (
                <span
                  key={role}
                  className="px-1.5 py-0.5 rounded text-[10px] bg-[#1e2a3d] border border-[#2b3b55] text-[#92a4c9]"
                >
                  {role}
                </span>
              ))}
            </div>
          )}
          {complexity.rationale && (
            <p className="w-full text-[11px] text-[#7a8baa] italic">
              {complexity.rationale}
            </p>
          )}
        </div>
      )}

      {/* ── Review gate ───────────────────────────────────────────────────── */}
      {reviewGate && (
        <div className="flex flex-wrap gap-3 pt-2 border-t border-[#2b3b55]">
          <div className="text-xs text-[#92a4c9]">
            <span className="text-[#5e7196]">Iterations: </span>
            <span className="text-white font-medium">{iterationCount}</span>
          </div>
          {finalCoverage != null && (
            <div className="text-xs text-[#92a4c9]">
              <span className="text-[#5e7196]">Coverage: </span>
              <span
                className={cn(
                  "font-medium",
                  finalCoverage >= (threshold ?? 0) ? "text-emerald-300" : "text-yellow-300",
                )}
              >
                {finalCoverage.toFixed(1)}%
              </span>
              {threshold != null && (
                <span className="text-[#3d5070]"> / {threshold}% req.</span>
              )}
            </div>
          )}
          <VerdictBadge verdict={reviewGate.final_verdict} />
        </div>
      )}

      {/* ── Exhaustion warning ────────────────────────────────────────────── */}
      {exhausted && (
        <div className="flex items-start gap-2 rounded-lg border border-yellow-500/25 bg-yellow-500/[0.06] p-2.5">
          <AlertTriangle className="w-3.5 h-3.5 text-yellow-300 shrink-0 mt-0.5" aria-hidden="true" />
          <p className="text-[11px] text-yellow-200 leading-snug">
            Review gate exhausted — results accepted with partial coverage. Check coverage tab for gaps.
          </p>
        </div>
      )}

      {/* ── Planner warnings ──────────────────────────────────────────────── */}
      {warnings.length > 0 && (
        <ul className="space-y-1">
          {warnings.map((w, i) => (
            <li key={i} className="flex items-start gap-1.5 text-[11px] text-yellow-200/80">
              <AlertTriangle className="w-3 h-3 text-yellow-400 shrink-0 mt-0.5" aria-hidden="true" />
              {w}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default PlanningReviewSummary;
