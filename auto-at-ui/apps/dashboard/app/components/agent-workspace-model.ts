export function agentWorkspaceTab(draftId: string | null): "generation" | "vision" {
  return draftId ? "generation" : "vision";
}
