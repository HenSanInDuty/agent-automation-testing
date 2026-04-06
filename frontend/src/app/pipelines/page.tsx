import type { Metadata } from "next";
import { PipelineListPage } from "@/components/pipelines/PipelineListPage";

export const metadata: Metadata = {
  title: "Pipelines",
  description: "Manage your AI pipeline templates.",
};

export default function PipelinesRoutePage() {
  return <PipelineListPage />;
}
