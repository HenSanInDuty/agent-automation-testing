"use client";

import { useParams } from "next/navigation";
import { PipelineRunDetailPage } from "@auto-at/shared";

export default function UserPipelineRunDetailPage() {
  const params = useParams();
  const templateId = typeof params.id === "string" ? params.id : (params.id?.[0] ?? "");
  const runId = typeof params.runId === "string" ? params.runId : (params.runId?.[0] ?? "");

  return (
    <PipelineRunDetailPage templateId={templateId} runId={runId} />
  );
}
