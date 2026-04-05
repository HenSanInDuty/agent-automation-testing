import type { Metadata } from "next";
import { StageConfigList } from "@/components/admin/stages/StageConfigList";

export const metadata: Metadata = {
  title: "Stage Configs",
  description: "Manage pipeline stage configurations for Auto-AT.",
};

export default function StageConfigsPage() {
  return <StageConfigList />;
}
