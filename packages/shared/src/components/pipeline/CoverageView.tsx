"use client";

import * as React from "react";
import { Target, ShieldCheck, AlertTriangle } from "lucide-react";

import { cn } from "../../lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Types — lean view-models from backend CoverageSummary / PostExecutionCoverage.
// Requirement coverage = (requirements with ≥1 test case) / (total requirements).
// ─────────────────────────────────────────────────────────────────────────────

export interface PreCoverage {
  total_requirements: number;
  covered_requirements: number;
  coverage_percentage: number;
  uncovered_requirements?: string[];
  coverage_gaps?: string[];
}

export interface PostCoverage {
  total_requirements: number;
  covered_requirements: number;
  validated_requirements: number;
  coverage_percentage: number;
  /** % of requirements whose tests PASSED (covered ≠ validated). */
  validation_percentage: number;
  uncovered_requirements?: string[];
  failed_requirements?: string[];
}

export interface CoverageViewProps {
  pre?: PreCoverage | null;
  post?: PostCoverage | null;
}

// ─────────────────────────────────────────────────────────────────────────────
// Metric ring/bar
// ─────────────────────────────────────────────────────────────────────────────

function clampPct(n: number): number {
  if (!Number.isFinite(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n * 10) / 10));
}

function MetricCard({
  icon,
  title,
  pct,
  caption,
  barCls,
}: {
  icon: React.ReactNode;
  title: string;
  pct: number;
  caption: string;
  barCls: string;
}) {
  const v = clampPct(pct);
  return (
    <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-4">
      <div className="flex items-center gap-2 text-xs text-[#92a4c9]">
        <span className="flex items-center justify-center w-6 h-6 rounded-lg bg-[#1e2a3d] border border-[#22304a]">
          {icon}
        </span>
        <span className="font-medium">{title}</span>
        <span className="ml-auto text-lg font-bold text-white tabular-nums">{v}%</span>
      </div>
      <div className="mt-3 h-2 rounded-full bg-[#101622] overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", barCls)} style={{ width: `${v}%` }} />
      </div>
      <p className="mt-2 text-[11px] text-[#5e7196]">{caption}</p>
    </div>
  );
}

function GapList({ title, items, tone }: { title: string; items: string[]; tone: "amber" | "red" }) {
  if (!items.length) return null;
  const cls = tone === "red" ? "text-red-300 border-red-500/25 bg-red-500/[0.04]" : "text-amber-300 border-amber-500/25 bg-amber-500/[0.04]";
  return (
    <div className={cn("rounded-xl border p-3", cls)}>
      <p className="text-[11px] font-semibold uppercase tracking-wider mb-1.5 inline-flex items-center gap-1.5">
        <AlertTriangle className="w-3 h-3" /> {title} ({items.length})
      </p>
      <div className="flex flex-wrap gap-1">
        {items.map((r) => (
          <span key={r} className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-[#101622]/60 border border-[#2b3b55] text-[#92a4c9]">
            {r}
          </span>
        ))}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// CoverageView — prefers post-execution data (richer) when present.
// ─────────────────────────────────────────────────────────────────────────────

export function CoverageView({ pre, post }: CoverageViewProps) {
  // Requirement counts: prefer post-exec when available.
  const total = post?.total_requirements ?? pre?.total_requirements ?? 0;
  const covered = post?.covered_requirements ?? pre?.covered_requirements ?? 0;
  const coveragePct = post?.coverage_percentage ?? pre?.coverage_percentage ?? 0;

  const uncovered = post?.uncovered_requirements ?? pre?.uncovered_requirements ?? [];
  const gaps = pre?.coverage_gaps ?? [];
  const failedReqs = post?.failed_requirements ?? [];

  return (
    <div className="space-y-4">
      <div className={cn("grid gap-3", post ? "sm:grid-cols-2" : "grid-cols-1")}>
        <MetricCard
          icon={<Target className="w-3.5 h-3.5 text-[#5b9eff]" />}
          title="Requirement coverage"
          pct={coveragePct}
          caption={`${covered}/${total} requirements have at least one test case`}
          barCls="bg-[#135bec]"
        />
        {post && (
          <MetricCard
            icon={<ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />}
            title="Validated (tests passed)"
            pct={post.validation_percentage}
            caption={`${post.validated_requirements}/${post.total_requirements} requirements have passing tests`}
            barCls="bg-emerald-500"
          />
        )}
      </div>

      <GapList title="Uncovered requirements" items={uncovered} tone="amber" />
      <GapList title="Coverage gaps" items={gaps} tone="amber" />
      <GapList title="Failed requirements" items={failedReqs} tone="red" />
    </div>
  );
}

export default CoverageView;
