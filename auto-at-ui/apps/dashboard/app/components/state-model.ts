export type ViewState = "empty" | "loading" | "error";

export function stateAccessibility(state: ViewState): { ariaLabel: string; busy?: true; role?: "alert" } {
  if (state === "loading") return { ariaLabel: "Loading state", busy: true };
  if (state === "error") return { ariaLabel: "Error state", role: "alert" };
  return { ariaLabel: "Empty state" };
}
