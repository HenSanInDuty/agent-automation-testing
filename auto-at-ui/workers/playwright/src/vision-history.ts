import type { Page } from "@playwright/test";
import { digest, requireVision } from "./vision-contract.js";
import { equivalentState, inspectState, type RuntimeState } from "./vision-checkpoints.js";

// Browser history and complete URLs remain private, scoped to the original Page.
export type HistoryCheckpoint = { page: Page; entryId: number; urlHash: string };

export async function captureHistory(page: Page, state: RuntimeState, method?: string): Promise<HistoryCheckpoint | null> {
  if (method !== "GET") return null;
  const cdp = await page.context().newCDPSession(page).catch(() => null);
  if (!cdp) return null;
  try {
    const history = await cdp.send("Page.getNavigationHistory");
    const entry = history.entries[history.currentIndex];
    if (!entry || entry.transitionType === "form_submit" || digest(entry.url) !== state.url_fingerprint ||
        !equivalentState(state, await inspectState(page))) return null;
    return { page, entryId: entry.id, urlHash: state.url_fingerprint };
  } catch { return null; }
  finally { await cdp.detach().catch(() => undefined); }
}

export async function validateHistory(saved: HistoryCheckpoint | null | undefined, page: Page, fromEntryId?: number): Promise<number> {
  requireVision(saved && saved.page === page && !page.isClosed(), "history_checkpoint_unavailable");
  const cdp = await page.context().newCDPSession(page);
  try {
    const history = await cdp.send("Page.getNavigationHistory");
    const index = history.entries.findIndex(entry => entry.id === saved.entryId);
    const current = history.entries[history.currentIndex];
    requireVision(index >= 0 && index < history.currentIndex &&
      digest(history.entries[index].url) === saved.urlHash &&
      history.entries[index].transitionType !== "form_submit" && current &&
      (fromEntryId === undefined || current.id === fromEntryId), "history_checkpoint_unavailable");
    return current.id;
  } finally { await cdp.detach().catch(() => undefined); }
}

export async function returnToHistory(saved: HistoryCheckpoint, page: Page, fromEntryId: number, timeout: number): Promise<void> {
  // Recheck immediately before selecting one saved entry; never issue repeated Back.
  const deadline = Date.now() + timeout;
  await validateHistory(saved, page, fromEntryId);
  const cdp = await page.context().newCDPSession(page);
  try {
    requireVision(Date.now() < deadline, "history_restore_timeout");
    await cdp.send("Page.navigateToHistoryEntry", { entryId: saved.entryId });
    for (;;) {
      requireVision(Date.now() < deadline, "history_restore_timeout");
      const history = await cdp.send("Page.getNavigationHistory");
      if (history.entries[history.currentIndex]?.id === saved.entryId) break;
      await page.waitForTimeout(10);
    }
    await page.waitForLoadState("domcontentloaded", { timeout: Math.max(1, deadline - Date.now()) });
  } finally { await cdp.detach().catch(() => undefined); }
}
