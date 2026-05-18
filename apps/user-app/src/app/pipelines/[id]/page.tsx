"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  ArrowLeft,
  Play,
  History,
  Layers,
  Tag,
  Hash,
} from "lucide-react";

import { usePipelineTemplate } from "@auto-at/shared";
import type { PipelineNodeConfig } from "@auto-at/shared";

// ─────────────────────────────────────────────────────────────────────────────
// Page
// ─────────────────────────────────────────────────────────────────────────────

export default function PipelineDetailPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : (params.id?.[0] ?? "");

  const { data: template, isLoading, isError, error } = usePipelineTemplate(id);

  if (isLoading) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8 animate-pulse">
        <div className="h-6 w-1/3 rounded bg-[#2b3b55] mb-4" />
        <div className="h-10 w-2/3 rounded bg-[#2b3b55] mb-2" />
        <div className="h-4 w-full rounded bg-[#2b3b55]" />
      </div>
    );
  }

  if (isError || !template) {
    return (
      <div className="max-w-4xl mx-auto px-4 py-8 text-center">
        <p className="text-sm text-red-400">
          {error?.message ?? "Failed to load pipeline template."}
        </p>
        <Link href="/pipelines" className="mt-4 inline-block text-xs text-[#92a4c9] hover:text-white underline">
          Back to pipelines
        </Link>
      </div>
    );
  }

  const nodes = template.nodes ?? [];
  const tags: string[] = (template as { tags?: string[] }).tags ?? [];

  return (
    <div className="max-w-4xl mx-auto px-4 py-8 flex flex-col gap-6">
      {/* Back link */}
      <Link
        href="/pipelines"
        className="inline-flex items-center gap-1.5 text-sm text-[#92a4c9] hover:text-white transition-colors w-fit"
      >
        <ArrowLeft className="w-4 h-4" />
        All pipelines
      </Link>

      {/* Header card */}
      <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] p-6">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div>
            <h1 className="text-xl font-bold text-white">{template.name}</h1>
            {template.description && (
              <p className="mt-1 text-sm text-[#92a4c9]">{template.description}</p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-1 text-xs text-[#3d5070]">
                <Layers className="w-3.5 h-3.5" />
                {template.node_count ?? nodes.length} nodes
              </span>
              {template.version && (
                <span className="inline-flex items-center gap-1 text-xs text-[#3d5070]">
                  <Hash className="w-3.5 h-3.5" />
                  v{template.version}
                </span>
              )}
              {tags.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <Tag className="w-3.5 h-3.5 text-[#3d5070]" />
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-[#2b3b55] text-[#92a4c9]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* CTA buttons */}
          <div className="flex items-center gap-2 shrink-0">
            <Link href={`/pipelines/${id}/run`}>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg text-sm font-medium bg-[#135bec] hover:bg-[#1a6df0] text-white transition-colors duration-150"
              >
                <Play className="w-3.5 h-3.5" aria-hidden="true" />
                Run
              </button>
            </Link>
            <Link href={`/pipelines/${id}/runs`}>
              <button
                type="button"
                className="inline-flex items-center gap-1.5 h-9 px-4 rounded-lg text-sm font-medium bg-[#1e2a3d] hover:bg-[#2b3b55] text-[#92a4c9] hover:text-white border border-[#2b3b55] transition-colors duration-150"
              >
                <History className="w-3.5 h-3.5" aria-hidden="true" />
                History
              </button>
            </Link>
          </div>
        </div>
      </div>

      {/* Stages / Nodes table */}
      {nodes.length > 0 && (
        <div className="rounded-xl border border-[#2b3b55] bg-[#18202F] overflow-hidden">
          <div className="px-4 py-3 border-b border-[#2b3b55]">
            <h2 className="text-sm font-semibold text-white">Nodes</h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-[#2b3b55] bg-[#101622]/60">
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Node ID
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Label
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Type
                  </th>
                  <th className="px-4 py-2.5 text-xs font-semibold text-[#3d5070] uppercase tracking-wider whitespace-nowrap">
                    Agent ID
                  </th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node: PipelineNodeConfig) => (
                  <tr
                    key={node.node_id}
                    className="border-b border-[#2b3b55] last:border-0 hover:bg-[#1e2a3d] transition-colors"
                  >
                    <td className="px-4 py-3 font-mono text-xs text-[#92a4c9]">
                      {node.node_id}
                    </td>
                    <td className="px-4 py-3 text-sm text-white">
                      {node.label}
                    </td>
                    <td className="px-4 py-3">
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-[#2b3b55] text-[#92a4c9]">
                        {node.node_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-[#3d5070]">
                      {node.agent_id ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
