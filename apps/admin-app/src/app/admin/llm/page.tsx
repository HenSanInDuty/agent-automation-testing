import type { Metadata } from "next";
import { LLMProfileList } from "@/components/admin/llm/LLMProfileList";

export const metadata: Metadata = {
  title: "LLM Profiles",
  description: "Manage LLM provider profiles for the Auto-AT pipeline.",
};

export default function LLMProfilesPage() {
  return <LLMProfileList />;
}
