import { randomUUID } from "node:crypto";
import type { Page } from "@playwright/test";
import { canonical, requireVision, safeLocatorValue, validateVision,
  type CodexBoundObservation, type CodexDomElement, type CodexElementBinding,
  type VisualWorkerObserveDom } from "./vision-contract.js";
import { equivalentState, inspectState, type RuntimeState } from "./vision-checkpoints.js";
import { groundLocator, resolveDescriptor } from "./vision-locators.js";

export type DomSnapshot = { data: CodexBoundObservation; state: RuntimeState; page: Page };

// Browser traversal is deliberately separate from inspectState's private form capture.
// Only bounded candidate geometry and already-filtered labels leave this callback.
export async function observeDom(page: Page, request: VisualWorkerObserveDom): Promise<DomSnapshot> {
  const before = await inspectState(page);
  requireVision(before.fingerprint === request.expected_state_fingerprint, "state_mismatch");
  const viewport = page.viewportSize(); requireVision(viewport, "viewport_unavailable");
  const capturedAt = new Date().toISOString();
  const found = await page.evaluate(({ limit, sensitive }) => {
    const candidates: Array<{ x: number; y: number; name: string; role: string; input_type: string | null; editable: boolean }> = [];
    // Closed roots are not discoverable through standard DOM APIs: report this coverage
    // limitation conservatively, even when no custom host exposes their presence.
    const unsupported = new Set<"iframe" | "closed_shadow" | "canvas" | "unbound_target">(["closed_shadow"]);
    const secret = new RegExp(sensitive, "i");
    let visited = 0, truncated = false, skipped = 0;
    const traversal = { visit(root: Document | ShadowRoot, dx = 0, dy = 0, depth = 0) {
      if (depth > 8) { truncated = true; return; }
      const doc = root.nodeType === Node.DOCUMENT_NODE ? root as Document : root.ownerDocument!;
      const walker = doc.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
      let node: Node | null;
      while ((node = walker.nextNode())) {
        if (++visited > 5000 || candidates.length >= limit) { truncated = true; return; }
        const el = node as Element, rect = el.getBoundingClientRect();
        const style = doc.defaultView!.getComputedStyle(el);
        const visible = rect.width > 0 && rect.height > 0 && style.visibility === "visible" &&
          style.display !== "none" && Number(style.opacity) !== 0 && rect.left + dx >= 0 &&
          rect.top + dy >= 0 && rect.right + dx <= innerWidth && rect.bottom + dy <= innerHeight;
        if (el.shadowRoot) this.visit(el.shadowRoot, dx, dy, depth + 1);
        // Closed roots cannot be inspected; custom hosts conservatively report missing coverage.
        else if (visible && el.tagName.includes("-")) unsupported.add("closed_shadow");
        if (el.tagName === "CANVAS" && visible) unsupported.add("canvas");
        if (el.tagName === "IFRAME" && visible) {
          const frame = el as HTMLIFrameElement;
          if (frame.contentDocument) this.visit(frame.contentDocument, dx + rect.left + frame.clientLeft, dy + rect.top + frame.clientTop, depth + 1);
          else unsupported.add("iframe");
        }
        if (!visible || !el.matches('button,a[href],input,textarea,select,[role="button"],[role="link"],[role="tab"],[role="checkbox"],[role="textbox"],[contenteditable="true"]')) continue;
        const input = el as HTMLInputElement;
        const tag = el.tagName.toLowerCase(), type = el.getAttribute("type")?.toLowerCase() ?? "text";
        if (type === "password" || type === "hidden" || input.disabled || el.getAttribute("aria-disabled") === "true") { skipped++; continue; }
        const formControl = el.matches("input,textarea,select,[contenteditable]");
        const labelled = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).map(id => doc.getElementById(id)?.textContent ?? "").join(" ").trim();
        const labels = Array.from(input.labels ?? []).map(label => label.textContent?.trim() ?? "");
        const rawNames = [el.getAttribute("aria-label"), labelled, ...labels, el.getAttribute("title"), formControl ? null : el.textContent?.trim()];
        // Check all labels and identity attributes before truncation; sensitive controls are omitted.
        const identity = [...rawNames, el.getAttribute("data-testid"), el.getAttribute("id"), el.getAttribute("name")];
        if (identity.some(value => value && (secret.test(value) || /[\x00-\x1f]/.test(value)))) { skipped++; continue; }
        const name = (rawNames.find(value => value?.trim()) ?? "").trim();
        if ([...name].length > 120) { skipped++; continue; }
        const role = el.getAttribute("role") ?? ({ button: "button", a: "link", textarea: "textbox", select: "combobox" }[tag] ||
          (tag === "input" ? ({ checkbox: "checkbox", radio: "radio", button: "button", submit: "button", number: "spinbutton" }[type] || "textbox") : "textbox"));
        if (!/^[a-z]{1,32}$/.test(role)) { skipped++; continue; }
        const types = ["text", "search", "email", "tel", "url", "number", "checkbox", "radio", "button", "submit", "reset", "range", "date", "time"];
        candidates.push({ x: rect.left + dx + rect.width / 2, y: rect.top + dy + rect.height / 2,
          role, name, input_type: tag === "input" ? types.includes(type) ? type : "other" : null,
          editable: (el.matches('input:not([readonly]),textarea:not([readonly]),[contenteditable="true"]') && !input.readOnly) });
      }
    } };
    traversal.visit(document);
    return { candidates, unsupported: [...unsupported], truncated, skipped,
      scrollable: document.documentElement.scrollHeight > innerHeight || document.documentElement.scrollWidth > innerWidth };
  }, { limit: request.max_elements, sensitive: String.raw`\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,}\b|https?:\/\/|\[redacted\]` });
  const elements: CodexDomElement[] = [], bindings: CodexElementBinding[] = [];
  const unsupported = new Set(found.unsupported);
  let truncated = found.truncated, skipped = found.skipped;
  const base = { schema_version: "v1", tenant_id: request.tenant_id, project_id: request.project_id,
    session_id: request.session_id, fencing_token: request.fencing_token, observation_id: randomUUID(),
    snapshot_id: request.snapshot_id, state_fingerprint: before.fingerprint, captured_at: capturedAt, viewport,
    elements, truncated, unsupported: [], scrollable: found.scrollable, skipped_count: skipped };
  for (const candidate of found.candidates) {
    if (candidate.name && !safeLocatorValue(candidate.name)) { skipped++; continue; }
    const grounded = await groundLocator(page, candidate.x / (viewport.width - 1), candidate.y / (viewport.height - 1));
    try {
      if (grounded.status !== "verified" || !grounded.descriptor || !grounded.bounding_box) {
        skipped++; unsupported.add("unbound_target"); continue;
      }
      const element = validateVision<CodexDomElement>("CodexDomElement", {
        element_id: `e_${randomUUID().replaceAll("-", "")}`, role: candidate.role, name: candidate.name,
        input_type: candidate.input_type, enabled: true,
        editable: candidate.editable && await grounded.locator!.isEditable(),
      });
      // Reserve room for final indicators before publishing an element.
      if (Buffer.byteLength(canonical({ ...base, elements: [...elements, element], truncated: true,
        unsupported: ["iframe", "closed_shadow", "canvas", "unbound_target"], skipped_count: 5000 })) > request.max_bytes) {
        truncated = true; break;
      }
      elements.push(element);
      bindings.push({ element_id: element.element_id, descriptor: grounded.descriptor, bounds: grounded.bounding_box });
    } finally { await grounded.target?.dispose(); }
  }
  requireVision(equivalentState(before, await inspectState(page)), "state_changed_during_observation");
  const data = validateVision<CodexBoundObservation>("CodexBoundObservation", {
    observation: { ...base, truncated, unsupported: [...unsupported], skipped_count: Math.min(skipped, 5000) }, bindings,
  });
  requireVision(Buffer.byteLength(canonical(data.observation)) <= request.max_bytes, "dom_byte_limit");
  return { data, state: before, page };
}

export async function resolveDomTarget(snapshot: DomSnapshot, page: Page, elementId: string) {
  requireVision(snapshot.page === page && equivalentState(snapshot.state, await inspectState(page)), "stale_dom_snapshot");
  const binding = snapshot.data.bindings.find(item => item.element_id === elementId);
  requireVision(binding, "unknown_dom_element");
  const locator = resolveDescriptor(page, binding.descriptor);
  requireVision(await locator.count() === 1 && await locator.isVisible() && await locator.isEnabled(), "stale_dom_target");
  const box = await locator.boundingBox(), viewport = page.viewportSize(); requireVision(box && viewport, "stale_dom_target");
  return { binding, x: (box.x + box.width / 2) / (viewport.width - 1), y: (box.y + box.height / 2) / (viewport.height - 1) };
}
