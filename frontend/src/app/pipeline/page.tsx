import type { Metadata } from "next";

import { PipelinePage } from "@/components/pipeline/PipelinePage";

// ─────────────────────────────────────────────────────────────────────────────
// Metadata
// ─────────────────────────────────────────────────────────────────────────────

export const metadata: Metadata = {
  title: "Pipeline",
  description:
    "Upload a requirements document and run the Auto-AT multi-agent pipeline.",
};

// ─────────────────────────────────────────────────────────────────────────────
// Route page
// ─────────────────────────────────────────────────────────────────────────────

export default function PipelineRoutePage() {
  return <PipelinePage />;
}
