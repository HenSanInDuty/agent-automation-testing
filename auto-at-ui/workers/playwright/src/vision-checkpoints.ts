import { visualButtonSemantics } from "./vision-button-semantics.js";
import type { Page } from "@playwright/test";
import { digest, canonical, type VisualCheckpoint } from "./vision-contract.js";
import { logVisionDiagnostic } from "./vision-observability.js";

export type RuntimeState = {
  fingerprint: string; url_fingerprint: string; semantic_fingerprint: string;
  interaction_fingerprint: string;
  form_presence_fingerprint: string; scroll_x: number; scroll_y: number;
  // This field is never returned by the worker transport or written to disk.
  privateForms: string;
};
const scopes = new WeakMap<Page, "all" | "buttons" | "visual_buttons">();
export function setInteractionScope(page: Page, scope: "all" | "buttons" | "visual_buttons") { scopes.set(page, scope); }
export function interactionScope(page: Page): "all" | "buttons" | "visual_buttons" { return scopes.get(page) ?? "all"; }
export async function inspectState(page: Page, includeSemantics = true): Promise<RuntimeState> {
  const scope = interactionScope(page);
  const visualButtons = scope === "visual_buttons" ? await page.evaluate(visualButtonSemantics) : [];
  const observed = await page.evaluate(({ scope, visualButtons, includeSemantics }) => {
    const buttonPaths = new Map(visualButtons.map(item => [document.querySelector(item.path), item.path]));
    const semantics: unknown[] = [], interactions: unknown[] = [], forms: unknown[] = [], presence: unknown[] = [];
    let nodes = 0;
    // Object methods stay self-contained when tsx serializes this browser callback.
    type Clip = { left: number; top: number; right: number; bottom: number };
    const traversal = { visit(root: Document | ShadowRoot, path: string, clip: Clip, offsetX = 0, offsetY = 0) {
      let scopes = 0;
      for (const el of Array.from(root.querySelectorAll("*"))) {
        if (++nodes > 5000) throw new Error("state_structure_limit");
        // Optional sample readiness only needs the unchanged interaction/private
        // guard. Skip passive semantics, never forms, frames or shadow traversal.
        if (!includeSemantics && scope === "visual_buttons" && !buttonPaths.has(el) &&
            !el.shadowRoot && !el.matches('iframe,input,textarea,select,[contenteditable=true],dialog,[role="dialog"],[aria-modal="true"],main,form,section[id]')) continue;
        const rect = el.getBoundingClientRect();
        const bounds = { left: Math.max(clip.left, rect.left + offsetX), top: Math.max(clip.top, rect.top + offsetY),
          right: Math.min(clip.right, rect.right + offsetX), bottom: Math.min(clip.bottom, rect.bottom + offsetY) };
        const style = el.ownerDocument.defaultView!.getComputedStyle(el);
        const visible = bounds.right > bounds.left && bounds.bottom > bounds.top && style.visibility === "visible";
        // Proposals come from a viewport screenshot. Offscreen carousels and
        // hidden tracking nodes must not invalidate that image's checkpoint.
        // Keep visible attributes/text and clipped geometry: moving a control,
        // revealing an overlay or changing its identity still invalidates it.
        if (visible) {
          const attrs = Array.from(el.attributes).filter((a) => !["value", "style"].includes(a.name)).map((a) => [a.name, a.value.slice(0, 240)]);
          const text = Array.from(el.childNodes).filter((node) => node.nodeType === Node.TEXT_NODE).map((node) => node.textContent?.slice(0, 240));
          const labelled = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/)
            .map((id) => el.ownerDocument.getElementById(id)?.textContent?.slice(0, 240) ?? "");
          if (includeSemantics) semantics.push([path, el.tagName, attrs, text, labelled,
            Object.values(bounds).map(Math.round), Math.round(el.scrollLeft), Math.round(el.scrollTop)]);
          // Keep full semantics for outcome reporting, but do not require passive
          // clocks, carousel images or opaque framework attributes to stop changing.
          // The interaction fingerprint retains identities, geometry and hit tests
          // for controls; changes that can invalidate a proposed action still fail.
          const control = el.matches('button,a[href],input,textarea,select,summary,iframe,[role="button"],[role="link"],[role="tab"],[role="checkbox"],[role="radio"],[role="switch"],[role="textbox"],[role="combobox"],[role="menuitem"],[contenteditable="true"],[tabindex]') ||
            (!el.matches("html,body") && (typeof (el as HTMLElement).onclick === "function" || style.cursor === "pointer"));
          const button = el.getAttribute("role") === "button" || (!el.hasAttribute("role") &&
            el.matches('button,input[type="button"],input[type="submit"],input[type="reset"]'));
          if (control && (scope === "all" || (scope === "buttons" && button) || buttonPaths.has(el) || el.tagName === "IFRAME")) {
            const input = el as HTMLInputElement;
            const identity = ["id", "data-testid", "name", "role", "type", "href", "target", "download",
              "aria-label", "aria-labelledby", "title", "alt", "aria-expanded", "aria-checked", "aria-selected", "aria-pressed",
              "aria-disabled", "aria-busy", "aria-controls", "contenteditable", "tabindex", "data-state", "data-status"]
              .map(key => [key, el.getAttribute(key)]);
            const labels = Array.from(input.labels ?? []).map(label => label.textContent);
            const label = el.matches("input,textarea,select,[contenteditable=true]") ? null : el.textContent;
            // Anonymous main-document buttons use v2 live-node bindings. Their
            // animated size/position is resolved again at dispatch, never reused
            // as model coordinates. Keep their structural identity and hit tests.
            const anonymous = scope === "buttons" && el.tagName === "BUTTON" &&
              el.getRootNode() === document && !label?.trim() && !labels.some(Boolean) &&
              !labelled.some(value => value.trim()) && !["id", "data-testid", "name", "aria-label", "title"]
                .some(key => el.getAttribute(key));
            let anonymousPath: string | null = buttonPaths.get(el) ?? null;
            if (anonymous) {
              const parts: string[] = [];
              let node: Element | null = el;
              while (node && node.tagName !== "HTML" && parts.length < 25) {
                const parent: Element | null = node.parentElement;
                if (!parent) break;
                const siblings = Array.from(parent.children).filter(other => other.tagName === node!.tagName);
                parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(node) + 1})`);
                node = parent;
              }
              if (node?.tagName === "HTML") anonymousPath = `html > ${parts.join(" > ")}`;
            }
            let transparent = false;
            for (let ancestor: Element | null = el; ancestor;) {
              if (Number(el.ownerDocument.defaultView!.getComputedStyle(ancestor).opacity) === 0) transparent = true;
              ancestor = ancestor.parentElement ?? (ancestor.getRootNode() instanceof ShadowRoot ? (ancestor.getRootNode() as ShadowRoot).host : null);
            }
            const hit = [[0.5, 0.5], [0.1, 0.1], [0.9, 0.1], [0.1, 0.9], [0.9, 0.9]].map(([x, y]) => {
              let top = el.ownerDocument.elementFromPoint(
                bounds.left - offsetX + (bounds.right - bounds.left) * x,
                bounds.top - offsetY + (bounds.bottom - bounds.top) * y);
              while (top?.shadowRoot) {
                const inner = top.shadowRoot.elementFromPoint(
                  bounds.left - offsetX + (bounds.right - bounds.left) * x,
                  bounds.top - offsetY + (bounds.bottom - bounds.top) * y);
                if (!inner || inner === top) break;
                top = inner;
              }
              return !!top && (el === top || el.contains(top));
            });
            if (scope === "visual_buttons" && buttonPaths.has(el)) {
              // All visual-button actions carry v3 live-node bindings. Animation
              // and interchangeable copies of a video affordance do not stale
              // unrelated proposals. Each target still gets fresh bounds, scope,
              // occlusion and exact-node verification before the physical click.
              interactions.push([path, el.tagName, identity, labels, labelled, label,
                input.disabled, input.readOnly, style.pointerEvents]);
            } else interactions.push([path, el.tagName, identity, labels, labelled, label,
              anonymousPath ?? Object.values(bounds).map(Math.round), input.disabled, input.readOnly,
              transparent, style.pointerEvents, anonymousPath ? hit.slice(0, 1) : hit]);
          } else if (el.matches('dialog,[role="dialog"],[aria-modal="true"],main,form,section[id]')) {
            // Opening a non-interactive modal/landmark is still a state transition.
            interactions.push([path, el.tagName, el.id, el.getAttribute("role"), el.getAttribute("aria-modal")]);
          }
        }
        // Form presence and values remain page-wide, including hidden/offscreen
        // inputs. Values never leave worker memory or enter public fingerprints.
        if (el.matches("input,textarea,select,[contenteditable=true]")) {
          const input = el as HTMLInputElement;
          presence.push([path, el.tagName, input.type, input.name, input.disabled, input.readOnly]);
          forms.push([input.value ?? el.textContent, input.checked, (el as HTMLSelectElement).selectedIndex]);
        }
        if (el.shadowRoot) this.visit(el.shadowRoot, `${path}/shadow/${scopes++}`, clip, offsetX, offsetY);
        if (el instanceof HTMLIFrameElement) {
          if (el.contentDocument) this.visit(el.contentDocument, `${path}/frame/${scopes++}`, bounds,
            rect.left + offsetX + el.clientLeft, rect.top + offsetY + el.clientTop);
        }
      }
    } };
    traversal.visit(document, "page", { left: 0, top: 0, right: innerWidth, bottom: innerHeight });
    return { semantics, interactions: scope === "visual_buttons"
      ? [...new Set(interactions.map(item => JSON.stringify(item)))].sort() : interactions,
      forms, presence, scroll_x: Math.round(scrollX), scroll_y: Math.round(scrollY) };
  }, { scope, visualButtons, includeSemantics });
  const state = { url_fingerprint: digest(page.url()), semantic_fingerprint: digest(canonical(observed.semantics)),
    interaction_fingerprint: digest(canonical(observed.interactions)),
    form_presence_fingerprint: digest(canonical(observed.presence)), scroll_x: observed.scroll_x, scroll_y: observed.scroll_y };
  // Version the hash policy without changing the opaque wire fingerprint shape.
  // Full visual semantics remain separate; form values are compared only in RAM.
  const interactionState = { url_fingerprint: state.url_fingerprint,
    interaction_fingerprint: state.interaction_fingerprint, form_presence_fingerprint: state.form_presence_fingerprint,
    scroll_x: state.scroll_x, scroll_y: state.scroll_y };
  return { ...state, fingerprint: digest(canonical({ policy: scope === "visual_buttons" ? "visual-buttons-v1" : scope === "buttons" ? "buttons-v2" : "interaction-v1", ...interactionState })), privateForms: canonical(observed.forms) };
}
export const equivalentState = (a: RuntimeState, b: RuntimeState): boolean => a.fingerprint === b.fingerprint && a.privateForms === b.privateForms;
export function logStateMismatch(before: RuntimeState, after: RuntimeState, stage: string): void {
  logVisionDiagnostic("vision.state.mismatch", "Page state changed before dispatch; no browser action was executed.", {
    failure_stage: stage, code: "state_mismatch",
    url_changed: before.url_fingerprint !== after.url_fingerprint,
    interaction_changed: before.interaction_fingerprint !== after.interaction_fingerprint,
    visual_semantics_changed: before.semantic_fingerprint !== after.semantic_fingerprint,
    form_presence_changed: before.form_presence_fingerprint !== after.form_presence_fingerprint,
    form_values_changed: before.privateForms !== after.privateForms,
    scroll_changed: before.scroll_x !== after.scroll_x || before.scroll_y !== after.scroll_y,
  });
}
export function checkpointMetadata(id: string, stateId: string, ancestors: string[], state: RuntimeState, url?: string): VisualCheckpoint {
  let pageUrl: string | null = null;
  if (url) {
    const parsed = new URL(url);
    if (["http:", "https:"].includes(parsed.protocol)) {
      parsed.username = ""; parsed.password = ""; parsed.search = ""; parsed.hash = "";
      if (parsed.href.length <= 2000) pageUrl = parsed.href;
    }
  }
  return { id, state_id: stateId, ancestor_operation_ids: ancestors,
    url_fingerprint: state.url_fingerprint, semantic_fingerprint: state.semantic_fingerprint,
    scroll_x: state.scroll_x, scroll_y: state.scroll_y, form_presence_fingerprint: state.form_presence_fingerprint, page_url: pageUrl, url_restore_allowed: false };
}

export async function settleState(page: Page, deadline: number, quietMs = 160, includeSemantics = true): Promise<{ state: RuntimeState; settled: boolean }> {
  let previous: RuntimeState | undefined;
  let interrupted: unknown;
  let stableSince = Date.now();
  const started = stableSince;
  let samples = 0, stateChanges = 0, contextResets = 0, longestStableMs = 0;
  let visibleChanges = 0, urlChanges = 0, formValueChanges = 0, formPresenceChanges = 0, scrollChanges = 0;
  let documentReady: boolean | null = null;
  let documentBusy: boolean | null = null;
  while (Date.now() < deadline) {
    try {
      const current = await inspectState(page, includeSemantics);
      samples++;
      if (previous && !equivalentState(current, previous)) {
        stateChanges++;
        if (current.semantic_fingerprint !== previous.semantic_fingerprint) visibleChanges++;
        if (current.url_fingerprint !== previous.url_fingerprint) urlChanges++;
        if (current.privateForms !== previous.privateForms) formValueChanges++;
        if (current.form_presence_fingerprint !== previous.form_presence_fingerprint) formPresenceChanges++;
        if (current.scroll_x !== previous.scroll_x || current.scroll_y !== previous.scroll_y) scrollChanges++;
      }
      if (!previous || !equivalentState(current, previous)) { stableSince = Date.now(); documentReady = null; documentBusy = null; }
      previous = current;
      longestStableMs = Math.max(longestStableMs, Date.now() - stableSince);
      if (Date.now() < deadline && Date.now() - stableSince >= quietMs) {
        const readiness = await page.evaluate(() => ({ ready: document.readyState !== "loading",
          busy: Array.from(document.querySelectorAll('[aria-busy="true"]')).some(el => {
            const rect = el.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0 && rect.right > 0 && rect.bottom > 0 &&
              rect.left < innerWidth && rect.top < innerHeight && getComputedStyle(el).visibility === "visible";
          }) }));
        documentReady = readiness.ready; documentBusy = readiness.busy;
        if (documentReady && !documentBusy && Date.now() < deadline) return { state: current, settled: true };
      }
    } catch (error) {
      // A redirect replaces the execution context while a read is in flight.
      // Retry only that read, reset the quiet interval and keep the same deadline.
      if (!(error instanceof Error) || !error.message.includes("Execution context was destroyed")) throw error;
      interrupted = error; previous = undefined; stableSince = Date.now(); documentReady = null; documentBusy = null; contextResets++;
    }
    if (Date.now() + 80 >= deadline) break;
    await page.waitForTimeout(80);
  }
  // Compare private state only in memory; export counts, never values or fingerprints.
  const reason = documentReady === false && longestStableMs >= quietMs ? "document_loading" :
    documentBusy === true ? "document_busy" :
    stateChanges > 0 ? "state_kept_changing" : contextResets > 0 ? "execution_context_replaced" :
      samples === 0 ? "no_observation" : "insufficient_quiet_window";
  logVisionDiagnostic("vision.state.settle_timeout",
    `Page did not stay stable for ${quietMs} ms within ${Math.max(0, deadline - started)} ms: ${reason}. ` +
    `Observed ${stateChanges} state changes (${visibleChanges} visible DOM/layout, ${formValueChanges} form values, ${urlChanges} URL).`,
    { failure_stage: "page_settle", code: "settle_timeout", reason, timeout_ms: Math.max(0, deadline - started),
      quiet_required_ms: quietMs, longest_observed_stable_ms: longestStableMs,
      duration_ms: Date.now() - started, samples, state_changes: stateChanges,
      visible_state_changes: visibleChanges, url_changes: urlChanges, form_value_changes: formValueChanges,
      form_presence_changes: formPresenceChanges, scroll_changes: scrollChanges,
      context_resets: contextResets, document_ready: documentReady, document_busy: documentBusy });
  if (!previous) throw interrupted ?? new Error("settle_timeout");
  return { state: previous, settled: false };
}
