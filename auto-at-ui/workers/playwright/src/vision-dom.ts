import { visualButtonSemantics } from "./vision-button-semantics.js";
import { randomUUID } from "node:crypto";
import type { ElementHandle, Page } from "@playwright/test";
import { canonical, requireVision, safeLocatorValue, validateVision,
  type CodexBoundObservation, type CodexDomElement, type CodexElementBinding,
  type VisualLocatorDescriptor, type VisualWorkerObserveDom } from "./vision-contract.js";
import { equivalentState, inspectState, interactionScope, logStateMismatch, type RuntimeState } from "./vision-checkpoints.js";
import { groundLocator, resolveDescriptor } from "./vision-locators.js";
import { logVisionEvent, visionLogScope } from "./vision-observability.js";
import { contextSignature, targetSignature, targetActionSignature } from "./vision-revalidation.js";

export type DomSnapshot = { data: CodexBoundObservation; state: RuntimeState; page: Page;
  document: ElementHandle<Element>;
  contextSignature: string; targetSignatures: Map<string, string>;
  actionSignatures?: Map<string, string>;
  anonymousTargets: Map<string, ElementHandle<Element>> };

// Browser traversal is deliberately separate from inspectState's private form capture.
// Only bounded candidate geometry and already-filtered labels leave this callback.
export async function observeDom(page: Page, request: VisualWorkerObserveDom): Promise<DomSnapshot> {
  const before = await inspectState(page);
  const documentRoot = await page.locator("html").elementHandle();
  requireVision(documentRoot, "state_changed_during_observation");
  const anonymousTargets = new Map<string, ElementHandle<Element>>();
  let completed = false;
  try {
  const context = await contextSignature(page);
  requireVision(before.fingerprint === request.expected_state_fingerprint, "state_mismatch");
  const viewport = page.viewportSize(); requireVision(viewport, "viewport_unavailable");
  const capturedAt = new Date().toISOString();
  const visualButtons = interactionScope(page) === "visual_buttons" ? await page.evaluate(visualButtonSemantics) : [];
  const found = await page.evaluate(({ limit, sensitive, scope, visualButtons }) => {
    const buttonMap = new Map(visualButtons.map(item => [document.querySelector(item.path), item]));
    // Keep overlap, but do not step over a control clipped by the lower edge.
    // This geometry-only hint stays in the private worker projection, not model input.
    let nextScrollDelta = scope === "visual_buttons" ? Math.min(2000, Math.max(1, Math.floor(innerHeight * .8))) : null;
    if (nextScrollDelta !== null) for (const el of buttonMap.keys()) {
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      if (rect.top >= 0 && rect.top < innerHeight && rect.bottom > innerHeight && rect.height <= innerHeight)
        nextScrollDelta = Math.min(nextScrollDelta, Math.max(1, Math.floor(rect.top)));
    }
    const candidates: Array<{ x: number; y: number; name: string; role: string; input_type: string | null;
      editable: boolean; button_path: string | null; button_kind: "native" | "styled_link" | "custom" | null }> = [];
    // Closed roots are not discoverable through standard DOM APIs: report this coverage
    // limitation conservatively, even when no custom host exposes their presence.
    const unsupported = new Set<"iframe" | "closed_shadow" | "canvas" | "unbound_target">(["closed_shadow"]);
    const secret = new RegExp(sensitive, "i");
    let visited = 0, truncated = false, skipped = 0;
    const skipReasons: Record<string, number> = {};
    const traversal = {
      skip(reason: string) { skipped++; skipReasons[reason] = (skipReasons[reason] ?? 0) + 1; },
      visit(root: Document | ShadowRoot, dx = 0, dy = 0, depth = 0) {
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
        if (!visible || (!buttonMap.has(el) && !el.matches('button,a[href],input,textarea,select,[role="button"],[role="link"],[role="tab"],[role="checkbox"],[role="textbox"],[contenteditable="true"]'))) continue;
        let transparent = false;
        for (let ancestor: Element | null = el; ancestor;) {
          if (Number(doc.defaultView!.getComputedStyle(ancestor).opacity) === 0) transparent = true;
          ancestor = ancestor.parentElement ?? (ancestor.getRootNode() instanceof ShadowRoot
            ? (ancestor.getRootNode() as ShadowRoot).host : null);
        }
        if (transparent) continue;
        if (scope === "visual_buttons" && !buttonMap.has(el)) continue;
        if (scope === "buttons" && !(el.getAttribute("role") === "button" || (!el.hasAttribute("role") &&
            el.matches('button,input[type="button"],input[type="submit"],input[type="reset"]')))) continue;
        const input = el as HTMLInputElement;
        const tag = el.tagName.toLowerCase(), type = el.getAttribute("type")?.toLowerCase() ?? "text";
        if (type === "password" || type === "hidden") { this.skip("private_input"); continue; }
        if (input.disabled || el.getAttribute("aria-disabled") === "true") { this.skip("disabled"); continue; }
        const formControl = el.matches("input,textarea,select,[contenteditable]");
        const labelled = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).map(id => doc.getElementById(id)?.textContent ?? "").join(" ").trim();
        const labels = Array.from(input.labels ?? []).map(label => label.textContent?.trim() ?? "");
        const rawNames = [el.getAttribute("aria-label"), labelled, ...labels, el.getAttribute("title"), formControl ? null : el.textContent?.trim()];
        // Check all labels and identity attributes before truncation; sensitive controls are omitted.
        const identity = [...rawNames, el.getAttribute("data-testid"), el.getAttribute("id"), el.getAttribute("name")];
        if (identity.some(value => value && (secret.test(value) || /[\x00-\x1f]/.test(value)))) { this.skip("sensitive_identity"); continue; }
        const name = (rawNames.find(value => value?.trim()) ?? "").trim();
        if ([...name].length > 120) { this.skip("name_length_limit"); continue; }
        const role = el.getAttribute("role") ?? ({ button: "button", a: "link", textarea: "textbox", select: "combobox" }[tag] ||
          (tag === "input" ? ({ checkbox: "checkbox", radio: "radio", button: "button", submit: "button", number: "spinbutton" }[type] || "textbox") : "textbox"));
        if (!/^[a-z]{1,32}$/.test(role)) { this.skip("unsupported_role"); continue; }
        let buttonPath: string | null = buttonMap.get(el)?.path ?? null;
        if (scope === "buttons" && tag === "button" && !name && doc === document &&
            el.getRootNode() === document && !["id", "data-testid", "name"].some(key => el.getAttribute(key))) {
          const parts: string[] = [];
          let node: Element | null = el;
          while (node && node.tagName !== "HTML" && parts.length < 25) {
            const parent: Element | null = node.parentElement;
            if (!parent) break;
            const siblings = Array.from(parent.children).filter(other => other.tagName === node!.tagName);
            parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(node) + 1})`);
            node = parent;
          }
          const path = `html > ${parts.join(" > ")}`;
          if (node?.tagName === "HTML" && parts.length <= 24 && path.length <= 1024) buttonPath = path;
        }
        const types = ["text", "search", "email", "tel", "url", "number", "checkbox", "radio", "button", "submit", "reset", "range", "date", "time"];
        candidates.push({ x: rect.left + dx + rect.width / 2, y: rect.top + dy + rect.height / 2,
          role: buttonMap.get(el)?.kind === "custom" ? "generic" : role, name, button_path: buttonPath, button_kind: buttonMap.get(el)?.kind ?? null, input_type: tag === "input" ? types.includes(type) ? type : "other" : null,
          editable: (el.matches('input:not([readonly]),textarea:not([readonly]),[contenteditable="true"]') && !input.readOnly) });
      }
    } };
    traversal.visit(document);
    return { candidates, unsupported: [...unsupported], truncated, skipped, skipReasons, nextScrollDelta,
      // This transport flag means there is another vertical viewport to inspect.
      scrollable: Math.ceil(scrollY + innerHeight) < document.documentElement.scrollHeight - 1 };
  }, { limit: request.max_elements, scope: interactionScope(page), visualButtons, sensitive: String.raw`\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,}\b|https?:\/\/|\[redacted\]` });
  const elements: CodexDomElement[] = [], bindings: CodexElementBinding[] = [];
  const targetSignatures = new Map<string, string>();
  const actionSignatures = new Map<string, string>();
  const unsupported = new Set(found.unsupported);
  let truncated = found.truncated, skipped = found.skipped;
  const skipReasons = found.skipReasons;
  const skip = (reason: string) => { skipped++; skipReasons[reason] = (skipReasons[reason] ?? 0) + 1; };
  const base = { schema_version: "v1", tenant_id: request.tenant_id, project_id: request.project_id,
    session_id: request.session_id, fencing_token: request.fencing_token, observation_id: randomUUID(),
    snapshot_id: request.snapshot_id, state_fingerprint: before.fingerprint, captured_at: capturedAt, viewport,
    elements, truncated, unsupported: [], scrollable: found.scrollable, skipped_count: skipped };
  const ground = async (candidate: typeof found.candidates[number]) => {
    if (candidate.name && !safeLocatorValue(candidate.name)) return { candidate, grounded: null };
    const groundCandidate = async () => {
      let { x, y } = candidate;
      let expected: VisualLocatorDescriptor | undefined;
      if (candidate.button_path) {
        expected = validateVision<VisualLocatorDescriptor>("VisualLocatorDescriptor", {
          schema_version: candidate.button_kind ? 'v3' : 'v2', strategy: 'dom_path', value: candidate.button_path,
        });
        const box = await resolveDescriptor(page, expected).boundingBox();
        if (box) { x = box.x + box.width / 2; y = box.y + box.height / 2; }
      }
      return groundLocator(page, x / (viewport.width - 1), y / (viewport.height - 1),
        false, expected, interactionScope(page) === "buttons" && candidate.role === "button" && !candidate.name);
    };
    let grounded = await groundCandidate();
    if (candidate.button_path && grounded.reason_code === 'unsupported_target') {
      // Read-only retry of a point sampled while an anonymous button animated.
      // No model reservation or physical browser action has occurred yet.
      grounded = await groundCandidate();
    }
    const [signature, actionSignature, editable] = await Promise.all([
      grounded.target ? targetSignature(grounded.target) : null,
      grounded.target ? targetActionSignature(grounded.target) : null,
      candidate.editable && grounded.locator ? grounded.locator.isEditable() : false,
    ]).catch(async error => { await grounded.target?.dispose(); throw error; });
    return { candidate, grounded, signature, actionSignature, editable };
  };
  // Independent read-only grounding runs in small batches. Serial protocol round
  // trips used most of a carousel's quiet interval before the final state check.
  collection: for (let offset = 0; offset < found.candidates.length; offset += 8) {
    const batch = await Promise.allSettled(found.candidates.slice(offset, offset + 8).map(ground));
    const retained = new Set<ElementHandle<Element>>();
    try {
      for (const item of batch) {
        if (item.status === "rejected") throw item.reason;
        const { candidate, grounded } = item.value;
        if (!grounded) { skip("sensitive_identity"); continue; }
      if (grounded.status !== "verified" || !grounded.descriptor || !grounded.bounding_box) {
        const reason = grounded.reason_code;
        // Export fixed categories only, never candidate labels or locator strings.
        skip(reason && ["no_grounded_locator", "multiple_matches", "target_not_actionable",
          "unsupported_target", "target_outside_viewport", "sensitive_locator_identity",
          "ambiguous_scope", "unsupported_shadow_scope", "cross_origin_frame", "unsupported_frame_scope"].includes(reason)
          ? reason : "unbound_target");
        unsupported.add("unbound_target"); continue;
      }
      const element = validateVision<CodexDomElement>("CodexDomElement", {
        element_id: `e_${randomUUID().replaceAll("-", "")}`, role: candidate.role, name: candidate.name, button_kind: candidate.button_kind,
        input_type: candidate.input_type, enabled: true,
        editable: item.value.editable ?? false,
      });
      // Reserve room for final indicators before publishing an element.
      if (Buffer.byteLength(canonical({ ...base, elements: [...elements, element], truncated: true,
        unsupported: ["iframe", "closed_shadow", "canvas", "unbound_target"], skipped_count: 5000 })) > request.max_bytes) {
        truncated = true; break collection;
      }
      elements.push(element);
      bindings.push({ element_id: element.element_id, descriptor: grounded.descriptor, bounds: grounded.bounding_box });
      if (grounded.target) {
        targetSignatures.set(element.element_id, item.value.signature!);
        actionSignatures.set(element.element_id, item.value.actionSignature!);
        anonymousTargets.set(element.element_id, grounded.target); retained.add(grounded.target);
      }
      }
    } finally {
      await Promise.all(batch.map(item => {
        const target = item.status === "fulfilled" ? item.value.grounded?.target : null;
        return target && !retained.has(target) ? target.dispose() : undefined;
      }));
    }
  }
  const after = await inspectState(page);
  if (!equivalentState(before, after)) logStateMismatch(before, after, "dom_collection");
  requireVision(equivalentState(before, after), "state_changed_during_observation");
  requireVision(context === await contextSignature(page), "state_changed_during_observation");
  const data = validateVision<CodexBoundObservation>("CodexBoundObservation", {
    observation: { ...base, truncated, unsupported: [...unsupported], skipped_count: Math.min(skipped, 5000) }, bindings,
    next_scroll_delta_y: found.nextScrollDelta,
  });
  requireVision(Buffer.byteLength(canonical(data.observation)) <= request.max_bytes, "dom_byte_limit");
  if (skipped || truncated) {
    const scope = visionLogScope.getStore();
    logVisionEvent("warn", "vision.dom.coverage_limited", "DOM observation omitted controls; coverage is incomplete.",
      scope?.context, { ...scope?.fields, session_id: request.session_id, snapshot_id: request.snapshot_id,
        interaction_scope: interactionScope(page), observed_count: elements.length, skipped_count: skipped,
        skip_reasons: skipReasons, truncated, scrollable: found.scrollable });
  }
  completed = true;
  return { data, state: before, page, document: documentRoot, anonymousTargets, targetSignatures,
    actionSignatures, contextSignature: context };
  } finally {
    if (!completed) await Promise.allSettled([
      documentRoot.dispose(), ...[...anonymousTargets.values()].map(target => target.dispose()),
    ]);
  }
}

export async function verifySnapshotTarget(snapshot: DomSnapshot, target: ElementHandle<Element>, elementId: string) {
  const original = snapshot.anonymousTargets.get(elementId);
  if (original && await target.evaluate((node, old) => node === old && node.isConnected, original)
    .catch(() => false)) return;
  // Existing restoration permits stable semantic descriptors on a verified,
  // equivalent checkpoint after document navigation. Within the same document,
  // an identical replacement cannot inherit the original live-node identity.
  const binding = snapshot.data.bindings.find(item => item.element_id === elementId);
  requireVision(binding && binding.descriptor.strategy !== "dom_path" &&
    !await snapshot.document.evaluate(el => el.isConnected).catch(() => false), "stale_dom_target");
}

export async function resolveDomTarget(snapshot: DomSnapshot, page: Page, elementId: string, stableTimeout?: number) {
  requireVision(snapshot.page === page && equivalentState(snapshot.state, await inspectState(page)), "stale_dom_snapshot");
  const binding = snapshot.data.bindings.find(item => item.element_id === elementId);
  requireVision(binding, "unknown_dom_element");
  const locator = resolveDescriptor(page, binding.descriptor);
  requireVision(await locator.count() === 1 && await locator.isVisible() && await locator.isEnabled(), "stale_dom_target");
  const target = await locator.elementHandle(); requireVision(target, "stale_dom_target");
  try {
    await verifySnapshotTarget(snapshot, target, elementId);
    if (stableTimeout !== undefined && binding.descriptor.schema_version === 'v3') {
      // Observe the retained node without clicking, scrolling or adopting a new
      // target. A moving center can otherwise miss between geometry and hit test.
      await target.waitForElementState('stable', { timeout: stableTimeout });
      await verifySnapshotTarget(snapshot, target, elementId);
      requireVision(equivalentState(snapshot.state, await inspectState(page)), 'stale_dom_snapshot');
      const resolved = await locator.elementHandle();
      try {
        requireVision(resolved && await resolved.evaluate((node, old) => node === old && node.isConnected,
          target).catch(() => false), 'stale_dom_target');
      } finally { await resolved?.dispose(); }
    }
  }
  finally { await target.dispose(); }
  const box = await locator.boundingBox(), viewport = page.viewportSize(); requireVision(box && viewport, "stale_dom_target");
  return { binding, x: (box.x + box.width / 2) / (viewport.width - 1), y: (box.y + box.height / 2) / (viewport.height - 1) };
}
