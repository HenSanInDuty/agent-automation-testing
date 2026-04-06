import type { Metadata } from "next";
import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  GitBranch,
  Layers,
  Terminal,
  Info,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Stage Configs — Deprecated",
  description:
    "Stage Configs have been replaced by DAG Pipeline Templates in V3.",
};

// ─────────────────────────────────────────────────────────────────────────────
// StageConfigsDeprecatedPage
// ─────────────────────────────────────────────────────────────────────────────

export default function StageConfigsDeprecatedPage() {
  return (
    <div className="max-w-2xl mx-auto py-12 px-4">
      {/* ── Banner ── */}
      <div className="flex items-start gap-4 p-5 rounded-xl bg-[#2d1f0a] border border-[#f59e0b]/30 mb-8">
        <div className="shrink-0 w-10 h-10 rounded-lg bg-[#f59e0b]/10 border border-[#f59e0b]/20 flex items-center justify-center mt-0.5">
          <AlertTriangle
            className="w-5 h-5 text-[#f59e0b]"
            aria-hidden="true"
          />
        </div>
        <div>
          <h2 className="text-base font-semibold text-[#fcd34d] mb-1">
            Stage Configs are deprecated in V3
          </h2>
          <p className="text-sm text-[#fcd34d]/70 leading-relaxed">
            The stage-based pipeline configuration has been superseded by the
            new{" "}
            <strong className="text-[#fcd34d]">DAG Pipeline Templates</strong>{" "}
            system. All{" "}
            <code className="px-1.5 py-0.5 rounded bg-[#f59e0b]/10 text-[11px] font-mono">
              /admin/stage-configs
            </code>{" "}
            API endpoints now return{" "}
            <code className="px-1.5 py-0.5 rounded bg-[#f59e0b]/10 text-[11px] font-mono">
              410 Gone
            </code>
            .
          </p>
        </div>
      </div>

      {/* ── What changed ── */}
      <div className="mb-8">
        <h3 className="text-sm font-semibold uppercase tracking-widest text-[#3d5070] mb-4">
          What changed in V3
        </h3>
        <div className="space-y-3">
          {[
            {
              before:
                "Fixed four sequential stages (Ingestion → Test Case → Execution → Reporting)",
              after:
                "Flexible DAG templates — any number of nodes, any topology, parallel execution",
            },
            {
              before: "Stage configs managed via /admin/stages",
              after:
                "Pipeline templates managed via /pipelines (visual builder)",
            },
            {
              before: "Agent ↔ stage association (agent_configs.stage field)",
              after: "Agent nodes placed freely on the DAG canvas",
            },
            {
              before: "Stage-level timeout / enabled flags",
              after: "Per-node timeout, retry count, and enabled flag",
            },
          ].map(({ before, after }, i) => (
            <div
              key={i}
              className="flex flex-col sm:flex-row items-start gap-2 sm:gap-3 p-4 rounded-xl bg-[#18202F] border border-[#2b3b55]"
            >
              {/* Before */}
              <div className="flex-1 flex items-start gap-2.5">
                <div className="shrink-0 mt-0.5">
                  <Layers
                    className="w-4 h-4 text-[#ef4444]/60"
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#ef4444]/60 mb-0.5">
                    V2 (removed)
                  </p>
                  <p className="text-xs text-[#92a4c9]">{before}</p>
                </div>
              </div>

              {/* Arrow */}
              <ArrowRight
                className="shrink-0 w-4 h-4 text-[#3d5070] hidden sm:block mt-5"
                aria-hidden="true"
              />

              {/* After */}
              <div className="flex-1 flex items-start gap-2.5">
                <div className="shrink-0 mt-0.5">
                  <GitBranch
                    className="w-4 h-4 text-[#22c55e]/60"
                    aria-hidden="true"
                  />
                </div>
                <div>
                  <p className="text-[10px] font-semibold uppercase tracking-wider text-[#22c55e]/60 mb-0.5">
                    V3 (replacement)
                  </p>
                  <p className="text-xs text-[#92a4c9]">{after}</p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ── CTA ── */}
      <div className="p-5 rounded-xl bg-[#135bec]/10 border border-[#135bec]/20 mb-8">
        <h3 className="text-sm font-semibold text-white mb-2 flex items-center gap-2">
          <GitBranch className="w-4 h-4 text-[#5b9eff]" aria-hidden="true" />
          Use Pipeline Templates instead
        </h3>
        <p className="text-sm text-[#92a4c9] mb-4 leading-relaxed">
          Create and manage your AI pipeline DAGs from the{" "}
          <strong className="text-white">Pipelines</strong> page. You can drag
          agents onto the canvas, wire them together, validate the DAG, and run
          it — all from one place.
        </p>
        <Link
          href="/pipelines"
          className="inline-flex items-center gap-2 h-9 px-4 rounded-lg text-sm font-medium bg-[#135bec] text-white hover:bg-[#1a6aff] transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-offset-2 focus-visible:ring-offset-[#101622]"
        >
          <GitBranch className="w-4 h-4" aria-hidden="true" />
          Go to Pipelines
          <ArrowRight className="w-3.5 h-3.5" aria-hidden="true" />
        </Link>
      </div>

      {/* ── Migration guide ── */}
      <div className="mb-8">
        <h3 className="text-sm font-semibold text-white mb-3 flex items-center gap-2">
          <Terminal className="w-4 h-4 text-[#92a4c9]" aria-hidden="true" />
          Run the migration script
        </h3>
        <p className="text-sm text-[#92a4c9] mb-3 leading-relaxed">
          The migration script automatically converts your V2 stage configs and
          agent configs into a V3 pipeline template called{" "}
          <code className="px-1.5 py-0.5 rounded bg-[#2b3b55] text-[11px] font-mono text-[#5b9eff]">
            auto-testing
          </code>
          .
        </p>
        <div className="rounded-xl bg-[#0d1220] border border-[#2b3b55] overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#2b3b55]">
            <div className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-[#ef4444]/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#f59e0b]/50" />
              <span className="w-2.5 h-2.5 rounded-full bg-[#22c55e]/50" />
            </div>
            <span className="text-[11px] text-[#3d5070] font-mono ml-1">
              backend/
            </span>
          </div>
          <pre className="px-4 py-4 text-xs font-mono text-[#92a4c9] leading-6 overflow-x-auto">
            <span className="text-[#3d5070]"># Dry-run first (no writes)</span>
            {"\n"}
            <span className="text-[#5b9eff]">$</span>{" "}
            <span className="text-white">
              uv run python scripts/migrate_v2_to_v3.py --dry-run
            </span>
            {"\n\n"}
            <span className="text-[#3d5070]"># Apply migration</span>
            {"\n"}
            <span className="text-[#5b9eff]">$</span>{" "}
            <span className="text-white">
              uv run python scripts/migrate_v2_to_v3.py
            </span>
            {"\n\n"}
            <span className="text-[#3d5070]">
              # Force-overwrite existing template
            </span>
            {"\n"}
            <span className="text-[#5b9eff]">$</span>{" "}
            <span className="text-white">
              uv run python scripts/migrate_v2_to_v3.py --force
            </span>
          </pre>
        </div>
      </div>

      {/* ── Info note ── */}
      <div className="flex items-start gap-3 p-4 rounded-xl bg-[#18202F] border border-[#2b3b55]">
        <Info
          className="w-4 h-4 text-[#3d5070] shrink-0 mt-0.5"
          aria-hidden="true"
        />
        <p className="text-xs text-[#3d5070] leading-relaxed">
          Your existing{" "}
          <code className="px-1 py-0.5 rounded bg-[#2b3b55] font-mono text-[10px]">
            stage_configs
          </code>{" "}
          and{" "}
          <code className="px-1 py-0.5 rounded bg-[#2b3b55] font-mono text-[10px]">
            agent_configs
          </code>{" "}
          documents in MongoDB are untouched. The migration script reads them
          and creates a new{" "}
          <code className="px-1 py-0.5 rounded bg-[#2b3b55] font-mono text-[10px]">
            pipeline_templates
          </code>{" "}
          document. Old V2 pipeline run history remains accessible under{" "}
          <strong className="text-[#92a4c9]">Pipeline Runs</strong>.
        </p>
      </div>
    </div>
  );
}
