import type { Metadata } from "next";
import { AgentList } from "@/components/admin/agents/AgentList";

export const metadata: Metadata = {
  title: "Agent Configs",
  description: "Manage CrewAI agent configurations for the Auto-AT pipeline.",
};

export default function AgentConfigsPage() {
  return <AgentList />;
}
