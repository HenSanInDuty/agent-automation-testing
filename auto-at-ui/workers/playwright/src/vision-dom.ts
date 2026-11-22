import { visualButtonSemantics } from "./vision-button-semantics.js";
import { randomUUID } from "node:crypto";
import type { ElementHandle, Page } from "@playwright/test";
import { canonical, requireVision, safeLocatorValue, validateVision,
  type CodexBoundObservation, type CodexDomElement, type CodexElementBinding,
  type VisualLocatorDescriptor, type VisualWorkerObserveDom } from "./vision-contract.js";
import { BOX_CENTER_TOLERANCE_PX, equivalentState, inspectState, interactionScope, logStateMismatch, type RuntimeState } from "./vision-checkpoints.js";
import { groundLocator, resolveDescriptor } from "./vision-locators.js";
import { logVisionEvent, visionLogScope } from "./vision-observability.js";
import { contextSignature, targetSignature, targetActionSignature } from "./vision-revalidation.js";

// ADR 045: a visual button inside an autoplay carousel can slide while it is observed. Grounding then hits another
// layer at the moving centre. For those reasons only, wait for the node's own box to stop and ground once more.
// A2: a node that moved and stopped outside the viewport means the visible control set changed under the walk
// (swiper `loop` shows another copy), so the DOM walk and grounding are repeated once, after the page has stopped.
// ponytail: fixed 1200 ms ceiling / 50 ms poll (carousel slide ~600 ms); raise it, or read the animation's own
// remaining time, if a live site shows slides that stay in motion longer than this.
const MOTION_WAIT_MS = 1200, MOTION_POLL_MS = 50, MOTION_READ_MS = 250, MOTION_STILL_PX = 0.5;
const MOTION_REASONS = new Set(["unsupported_target", "locator_target_mismatch", "target_outside_viewport"]);

export type DomSnapshot = { data: CodexBoundObservation; state: RuntimeState; page: Page;
  document: ElementHandle<Element>;
  contextSignature: string; targetSignatures: Map<string, string>;
  actionSignatures?: Map<string, string>;
  anonymousTargets: Map<string, ElementHandle<Element>> };

// Browser traversal is deliberately separate from inspectState's private form capture.
// Only bounded candidate geometry and already-filtered labels leave this callback.
// `agentDomPath` (capability `agent-dom-path-v1`, agent mode only): controls without an accessible name
// get a main-document `dom_path` locator (any button/link/custom control), so they can be bound and
// clicked. Named controls keep their role/label locators and are unchanged; off = old behaviour.
export async function observeDom(page: Page, request: VisualWorkerObserveDom,
  options: { agentDomPath?: boolean; held?: RuntimeState } = {}): Promise<DomSnapshot> {
  const agentPaths = options.agentDomPath === true;
  const before = await inspectState(page);
  const documentRoot = await page.locator("html").elementHandle();
  requireVision(documentRoot, "state_changed_during_observation");
  const anonymousTargets = new Map<string, ElementHandle<Element>>();
  let completed = false;
  try {
  const context = await contextSignature(page);
  // ADR 042: the expected hash must be the state the worker holds (the one it published); the fresh inspection
  // may only differ from it by tolerated presentation drift. Without a held state (direct callers) the hash is exact.
  const held = options.held;
  if (held) requireVision(held.fingerprint === request.expected_state_fingerprint && equivalentState(held, before), "state_mismatch");
  else requireVision(before.fingerprint === request.expected_state_fingerprint, "state_mismatch");
  const viewport = page.viewportSize(); requireVision(viewport, "viewport_unavailable");
  const capturedAt = new Date().toISOString();
  // A function so that A2 can repeat the walk once; the first call is the unchanged single walk.
  const traverse = async () => {
  const visualButtons = interactionScope(page) === "visual_buttons" || agentPaths ? await page.evaluate(visualButtonSemantics) : [];
  return page.evaluate(({ limit, sensitive, scope, visualButtons, agentPaths }) => {
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
      editable: boolean; button_path: string | null; button_kind: "native" | "styled_link" | "custom" | null;
      path_version?: "v2" | "v3" }> = [];
    const standard = 'button,a[href],input,textarea,select,[role="button"],[role="link"],[role="tab"],[role="checkbox"],[role="textbox"],[contenteditable="true"]';
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
        if (!visible || (!buttonMap.has(el) && !el.matches(standard))) continue;
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
        // Agent paths: a visual-only candidate (div/span) with a name is not an agent control today.
        if (agentPaths && scope === "all" && name && buttonMap.has(el) && !el.matches(standard)) continue;
        let buttonPath: string | null = scope === "all" && agentPaths && name ? null : buttonMap.get(el)?.path ?? null;
        let pathVersion: "v2" | "v3" | undefined;
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
        if (agentPaths && scope === "all" && !name && !buttonPath && doc === document && el.getRootNode() === document &&
            ["button", "a", "div", "span", "input"].includes(tag)) {
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
          if (node?.tagName === "HTML" && parts.length >= 2 && parts.length <= 24 && path.length <= 1024) buttonPath = path;
        }
        if (agentPaths && scope === "all" && buttonPath) pathVersion = tag === "button" ? "v2" : "v3";
        const types = ["text", "search", "email", "tel", "url", "number", "checkbox", "radio", "button", "submit", "reset", "range", "date", "time"];
        candidates.push({ x: rect.left + dx + rect.width / 2, y: rect.top + dy + rect.height / 2,
          role: buttonMap.get(el)?.kind === "custom" ? "generic" : role, name, button_path: buttonPath,
          button_kind: scope === "all" && agentPaths && name ? null : buttonMap.get(el)?.kind ?? null, path_version: pathVersion, input_type: tag === "input" ? types.includes(type) ? type : "other" : null,
          editable: (el.matches('input:not([readonly]),textarea:not([readonly]),[contenteditable="true"]') && !input.readOnly) });
      }
    } };
    traversal.visit(document);
    return { candidates, unsupported: [...unsupported], truncated, skipped, skipReasons, nextScrollDelta,
      // This transport flag means there is another vertical viewport to inspect.
      scrollable: Math.ceil(scrollY + innerHeight) < document.documentElement.scrollHeight - 1 };
  }, { limit: request.max_elements, scope: interactionScope(page), visualButtons, agentPaths, sensitive: String.raw`\b(?:password|passwd|secret|token|api[_ -]?key|authorization|cookie)\b|[\w.+-]+@[\w.-]+\.[a-z]{2,}|\b\d{7,}\b|https?:\/\/|\[redacted\]` });
  };
  let found = await traverse();
  const elements: CodexDomElement[] = [], bindings: CodexElementBinding[] = [];
  const targetSignatures = new Map<string, string>();
  const actionSignatures = new Map<string, string>();
  let unsupported = new Set(found.unsupported);
  let truncated = found.truncated, skipped = found.skipped;
  let skipReasons = found.skipReasons;
  const skip = (reason: string) => { skipped++; skipReasons[reason] = (skipReasons[reason] ?? 0) + 1; };
  const base = { schema_version: "v1", tenant_id: request.tenant_id, project_id: request.project_id,
    session_id: request.session_id, fencing_token: request.fencing_token, observation_id: randomUUID(),
    snapshot_id: request.snapshot_id, state_fingerprint: held?.fingerprint ?? before.fingerprint, captured_at: capturedAt, viewport,
    elements, truncated, unsupported: [], scrollable: found.scrollable, skipped_count: skipped };
  const motion = { waits: 0, regrounded: 0, retraversals: 0, invalidated: false };
  // Phase 02: candidates of the first walk that motion made lose their binding; checked against the final walk.
  const lost: Array<{ role: string; name: string; button_kind: string | null; reason: string }> = [];
  const ground = async (candidate: typeof found.candidates[number]) => {
    if (candidate.name && !safeLocatorValue(candidate.name)) return { candidate, grounded: null };
    const expected = candidate.button_path ? validateVision<VisualLocatorDescriptor>("VisualLocatorDescriptor", {
      schema_version: candidate.path_version ?? (candidate.button_kind ? 'v3' : 'v2'), strategy: 'dom_path', value: candidate.button_path,
    }) : undefined;
    let invalidates = false;
    const groundCandidate = async () => {
      let { x, y } = candidate;
      if (expected) {
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
    // One wait per observation: the repeated walk (retraversals 1) grounds once and keeps a failure as a skip.
    if (expected && interactionScope(page) === "visual_buttons" && motion.retraversals === 0 &&
        grounded.reason_code && MOTION_REASONS.has(grounded.reason_code)) {
      // Read-only: only the node's own box is polled. Settle cannot see this motion (visual-button entries carry no geometry).
      const deadline = Date.now() + MOTION_WAIT_MS;
      // Each read has its own timeout, bounded by the time left: a removed node must not hold the batch for 30 s.
      const read = () => resolveDescriptor(page, expected)
        .boundingBox({ timeout: Math.max(1, Math.min(MOTION_READ_MS, deadline - Date.now())) }).catch(() => null);
      let previous = await read(), current = previous, moving = false, still = false;
      while (previous && !still && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, MOTION_POLL_MS));
        current = await read();
        if (!current) break;
        still = Math.abs(current.x - previous.x) <= MOTION_STILL_PX && Math.abs(current.y - previous.y) <= MOTION_STILL_PX &&
          Math.abs(current.width - previous.width) <= MOTION_STILL_PX && Math.abs(current.height - previous.height) <= MOTION_STILL_PX;
        moving ||= !still; previous = current;
      }
      const displaced = !!current && (Math.abs(current.x + current.width / 2 - candidate.x) > BOX_CENTER_TOLERANCE_PX ||
        Math.abs(current.y + current.height / 2 - candidate.y) > BOX_CENTER_TOLERANCE_PX);
      const moved = moving || displaced;
      if (moved) motion.waits++;
      // A box that moved and is still now was not where the walk saw it, even if it came back to the same place.
      if (still && moved) {
        grounded = await groundCandidate();
        if (grounded.status === "verified") motion.regrounded++;
        // Stopped outside the viewport: the walk no longer describes what is visible.
        else if (current && !(current.x >= 0 && current.y >= 0 && current.x + current.width <= viewport.width &&
          current.y + current.height <= viewport.height)) motion.invalidated = invalidates = true;
      }
    }
    const [signature, actionSignature, editable] = await Promise.all([
      grounded.target ? targetSignature(grounded.target) : null,
      grounded.target ? targetActionSignature(grounded.target) : null,
      candidate.editable && grounded.locator ? grounded.locator.isEditable() : false,
    ]).catch(async error => { await grounded.target?.dispose(); throw error; });
    return { candidate, grounded, signature, actionSignature, editable, invalidates };
  };
  // Independent read-only grounding runs in small batches. Serial protocol round
  // trips used most of a carousel's quiet interval before the final state check.
  for (;;) {
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
          const code = reason && ["no_grounded_locator", "multiple_matches", "target_not_actionable",
            "unsupported_target", "target_outside_viewport", "sensitive_locator_identity",
            "ambiguous_scope", "unsupported_shadow_scope", "cross_origin_frame", "unsupported_frame_scope"].includes(reason)
            ? reason : "unbound_target";
          skip(code);
          if (item.value.invalidates && motion.retraversals === 0) lost.push({ ...candidate, reason: code });
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
    // A2: the controls seen by the walk were not the ones on show once the page stopped. The page is still now, so
    // walk and ground once more (the next autoplay slide is seconds away). Never a third time.
    // ponytail: one repeat per observation; a site that keeps changing its visible set after that stays a skip.
    if (!motion.invalidated || motion.retraversals > 0) break;
    await Promise.all([...anonymousTargets.values()].map(target => target.dispose()));
    anonymousTargets.clear(); targetSignatures.clear(); actionSignatures.clear();
    elements.length = 0; bindings.length = 0; motion.invalidated = false; motion.retraversals++;
    found = await traverse();
    base.scrollable = found.scrollable; unsupported = new Set(found.unsupported);
    truncated = found.truncated; skipped = found.skipped; skipReasons = found.skipReasons;
  }
  // Phase 02: the repeated walk replaced the first walk's skips. A first-walk candidate that motion invalidated and
  // that has no bound twin now is still a miss: count it with its original reason, so coverage_limited is logged.
  // Twin = same role, name and kind, the fields the fingerprint's identity covers (vision-checkpoints.ts:162-168).
  const twins = elements.map(item => [item.role, item.name, item.button_kind].join(" "));
  for (const miss of lost) {
    const at = twins.indexOf([miss.role, miss.name, miss.button_kind].join(" "));
    if (at >= 0) twins.splice(at, 1);
    else { skip(miss.reason); unsupported.add("unbound_target"); }
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
  const scope = visionLogScope.getStore();
  if (motion.regrounded || motion.retraversals) logVisionEvent("info", "vision.dom.motion_regrounded",
    "Visual buttons that moved during observation were grounded after they stopped.", scope?.context,
    { ...scope?.fields, session_id: request.session_id, snapshot_id: request.snapshot_id,
      motion_waits: motion.waits, motion_regrounded: motion.regrounded, motion_retraversals: motion.retraversals });
  if (skipped || truncated) {
    logVisionEvent("warn", "vision.dom.coverage_limited", "DOM observation omitted controls; coverage is incomplete.",
      scope?.context, { ...scope?.fields, session_id: request.session_id, snapshot_id: request.snapshot_id,
        interaction_scope: interactionScope(page), observed_count: elements.length, skipped_count: skipped,
        skip_reasons: skipReasons, truncated, scrollable: found.scrollable,
        motion_waits: motion.waits, motion_regrounded: motion.regrounded, motion_retraversals: motion.retraversals });
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
