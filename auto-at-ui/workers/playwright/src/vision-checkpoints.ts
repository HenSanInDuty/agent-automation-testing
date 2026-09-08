import type { Page } from "@playwright/test";
import { digest, canonical, type VisualCheckpoint } from "./vision-contract.js";

export type RuntimeState = {
  fingerprint: string; url_fingerprint: string; semantic_fingerprint: string;
  form_presence_fingerprint: string; scroll_x: number; scroll_y: number;
  // This field is never returned by the worker transport or written to disk.
  privateForms: string;
};
export async function inspectState(page: Page): Promise<RuntimeState> {
  const observed = await page.evaluate(() => {
    const semantics: unknown[] = [], forms: unknown[] = [], presence: unknown[] = [];
    let nodes = 0;
    // Object methods stay self-contained when tsx serializes this browser callback.
    const traversal = { visit(root: Document | ShadowRoot, path: string) {
      for (const el of Array.from(root.querySelectorAll("*"))) {
        if (++nodes > 5000) throw new Error("state_structure_limit");
        const rect = el.getBoundingClientRect();
        const attrs = Array.from(el.attributes).filter((a) => !["value", "style"].includes(a.name)).map((a) => [a.name, a.value.slice(0, 240)]);
        const text = Array.from(el.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => node.textContent?.slice(0, 240));
        semantics.push([path, el.tagName, attrs, text, rect.width > 0 && rect.height > 0, Math.round(el.scrollLeft), Math.round(el.scrollTop)]);
        if (el.matches("input,textarea,select,[contenteditable=true]")) {
          const input = el as HTMLInputElement;
          presence.push([path, el.tagName, input.type, input.name, input.disabled, input.readOnly]);
          forms.push([input.value ?? el.textContent, input.checked, (el as HTMLSelectElement).selectedIndex]);
        }
        if (el.shadowRoot) this.visit(el.shadowRoot, `${path}/shadow/${nodes}`);
        if (el instanceof HTMLIFrameElement) {
          try { if (el.contentDocument) this.visit(el.contentDocument, `${path}/frame/${nodes}`); } catch { /* unsupported opaque frame */ }
        }
      }
    } };
    traversal.visit(document, "page");
    return { semantics, forms, presence, scroll_x: Math.round(scrollX), scroll_y: Math.round(scrollY) };
  });
  const state = { url_fingerprint: digest(page.url()), semantic_fingerprint: digest(canonical(observed.semantics)),
    form_presence_fingerprint: digest(canonical(observed.presence)), scroll_x: observed.scroll_x, scroll_y: observed.scroll_y };
  // The public fingerprint intentionally omits values; equality checks values in RAM too.
  return { ...state, fingerprint: digest(canonical(state)), privateForms: canonical(observed.forms) };
}
export const equivalentState = (a: RuntimeState, b: RuntimeState): boolean => a.fingerprint === b.fingerprint && a.privateForms === b.privateForms;
export function checkpointMetadata(id: string, stateId: string, ancestors: string[], state: RuntimeState): VisualCheckpoint {
  return { id, state_id: stateId, ancestor_operation_ids: ancestors,
    url_fingerprint: state.url_fingerprint, semantic_fingerprint: state.semantic_fingerprint,
    scroll_x: state.scroll_x, scroll_y: state.scroll_y, form_presence_fingerprint: state.form_presence_fingerprint };
}

export async function settleState(page: Page, deadline: number): Promise<{ state: RuntimeState; settled: boolean }> {
  let previous = await inspectState(page);
  let stableSamples = 0;
  while (Date.now() + 80 < deadline) {
    await page.waitForTimeout(80);
    const current = await inspectState(page);
    stableSamples = equivalentState(current, previous) ? stableSamples + 1 : 0;
    previous = current;
    if (stableSamples >= 2 && await page.evaluate(() => document.readyState !== "loading")) return { state: current, settled: true };
  }
  return { state: previous, settled: false };
}
