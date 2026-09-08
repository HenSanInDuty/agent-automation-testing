import type { ElementHandle, Frame, FrameLocator, Locator, Page } from "@playwright/test";
import { safeLocatorValue, stableCss, validateVision, type VisualLocatorDescriptor,
  type VisualLocatorScope, type VisualBoundingBox } from "./vision-contract.js";

export type GroundedLocator = {
  status: "verified" | "ambiguous" | "not_found" | "stale" | "unsupported" | "redacted";
  reason_code: string | null; descriptor: VisualLocatorDescriptor | null;
  bounding_box: VisualBoundingBox | null; matched_count: number;
  target_match: boolean; actionable: boolean; verified_at: string | null;
  locator?: Locator; target?: ElementHandle<Element>;
};
const unresolved = (status: GroundedLocator["status"], reason: string, count = 0): GroundedLocator => ({
  status, reason_code: reason, descriptor: null, bounding_box: null, matched_count: count,
  target_match: false, actionable: false, verified_at: null,
});

export function resolveDescriptor(page: Page, descriptor: VisualLocatorDescriptor): Locator {
  let scope: Page | FrameLocator | Locator = page;
  for (const item of descriptor.scope) scope = item.kind === "iframe" ? scope.frameLocator(item.selector) : scope.locator(item.selector);
  if (descriptor.strategy === "role") return scope.getByRole(descriptor.role as Parameters<Page["getByRole"]>[0], { name: descriptor.value, exact: true });
  if (descriptor.strategy === "label") return scope.getByLabel(descriptor.value, { exact: true });
  if (descriptor.strategy === "test_id") return scope.getByTestId(descriptor.value);
  return scope.locator(descriptor.value);
}

async function hitTarget(page: Page, x: number, y: number): Promise<{
  target: ElementHandle<Element>; scope: VisualLocatorScope[];
} | string> {
  let frame: Frame = page.mainFrame();
  const scope: VisualLocatorScope[] = [];
  for (let depth = 0; depth < 9; depth++) {
    const handle = await frame.evaluateHandle(({ x, y }) => {
      let element = document.elementFromPoint(x, y);
      while (element?.shadowRoot) {
        const nested = element.shadowRoot.elementFromPoint(x, y);
        if (!nested || nested === element) break;
        element = nested;
      }
      if (element?.tagName === "IFRAME") return element;
      let current = element;
      while (current) {
        if (current.matches('button,a[href],input,textarea,select,[role="button"],[role="link"],[role="tab"],[role="checkbox"],[role="textbox"],[contenteditable="true"]')) return current;
        current = current.parentElement ?? ((current.getRootNode() as ShadowRoot).host || null);
      }
      return null;
    }, { x, y });
    const target = handle.asElement() as ElementHandle<Element> | null;
    if (!target) { await handle.dispose(); return "unsupported_target"; }
    const ancestry = await target.evaluate((element) => {
      const selectors = { forElement(el: Element): string | null {
        for (const attr of ["id", "data-testid", "name", "aria-label", "title"]) {
          const value = el.getAttribute(attr);
          if (value && !/["\\\r\n]/.test(value)) return `${el.tagName.toLowerCase()}[${attr}="${value}"]`;
        }
        return null;
      } };
      const shadows: (string | null)[] = [];
      let root = element.getRootNode();
      while (root instanceof ShadowRoot) { shadows.unshift(selectors.forElement(root.host)); root = root.host.getRootNode(); }
      const rect = element.getBoundingClientRect();
      return { shadows, iframe: element.tagName === "IFRAME", selector: selectors.forElement(element),
        left: rect.left + element.clientLeft, top: rect.top + element.clientTop,
        scaled: Math.abs(rect.width - (element as HTMLElement).offsetWidth) > 1 ||
          Math.abs(rect.height - (element as HTMLElement).offsetHeight) > 1 };
    });
    for (const selector of ancestry.shadows) {
      if (!selector || !stableCss.test(selector) || !safeLocatorValue(selector)) { await target.dispose(); return "unsupported_shadow_scope"; }
      scope.push({ kind: "shadow", selector });
    }
    if (!ancestry.iframe) return { target, scope };
    const child = await (target as ElementHandle<HTMLIFrameElement>).contentFrame();
    let sameOrigin = false;
    try { sameOrigin = !!child && new URL(child.url()).origin === new URL(frame.url()).origin; } catch { /* opaque frame */ }
    if (!sameOrigin || !child) { await target.dispose(); return "cross_origin_frame"; }
    if (ancestry.scaled || !ancestry.selector || !stableCss.test(ancestry.selector) || !safeLocatorValue(ancestry.selector)) {
      await target.dispose(); return "unsupported_frame_scope";
    }
    scope.push({ kind: "iframe", selector: ancestry.selector });
    x -= ancestry.left; y -= ancestry.top; frame = child;
    await target.dispose();
  }
  return "scope_limit";
}

async function uniqueScopes(page: Page, scopes: VisualLocatorScope[]): Promise<boolean> {
  let root: Page | FrameLocator | Locator = page;
  for (const scope of scopes) {
    if (await root.locator(scope.selector).count() !== 1) return false;
    root = scope.kind === "iframe" ? root.frameLocator(scope.selector) : root.locator(scope.selector);
  }
  return true;
}

export async function groundLocator(page: Page, x: number, y: number, editable = false,
  expected?: VisualLocatorDescriptor | null): Promise<GroundedLocator> {
  const viewport = page.viewportSize();
  if (!viewport) return unresolved("unsupported", "viewport_unavailable");
  const hit = await hitTarget(page, x * (viewport.width - 1), y * (viewport.height - 1));
  if (typeof hit === "string") return unresolved("unsupported", hit);
  const { target, scope } = hit;
  let keepTarget = false;
  try {
    if (scope.length > 8 || !await uniqueScopes(page, scope)) return unresolved("ambiguous", "ambiguous_scope");
    const details = await target.evaluate((el) => {
      const tag = el.tagName.toLowerCase(), type = el.getAttribute("type") ?? "text";
      const role = el.getAttribute("role") ?? ({ button: "button", a: "link", textarea: "textbox", select: "combobox" }[tag] ||
        (tag === "input" ? ({ checkbox: "checkbox", radio: "radio", button: "button", submit: "button", number: "spinbutton" }[type] || "textbox") : null));
      const labels = Array.from((el as HTMLInputElement).labels ?? []).map((label) => label.textContent?.trim() ?? "");
      const labelled = (el.getAttribute("aria-labelledby") ?? "").split(/\s+/).map((id) => el.ownerDocument.getElementById(id)?.textContent ?? "").join(" ").trim();
      // Candidate strings only: Playwright's accessibility engine must independently
      // resolve exactly this DOM element before a role/name can be verified.
      const names = [el.getAttribute("aria-label"), labelled, ...labels, el.textContent?.trim(), el.getAttribute("title")]
        .filter((value): value is string => !!value && value.length <= 240);
      const attributes = ["id", "data-testid", "name", "aria-label", "title"].map((key) => [key, el.getAttribute(key)]);
      return { role, names, labels, attributes, tag, password: type === "password", testId: el.getAttribute("data-testid") };
    });
    if (details.password) return unresolved("unsupported", "credential_input_unsupported");
    const candidates: VisualLocatorDescriptor[] = [];
    let redacted = false;
    const candidate = (strategy: VisualLocatorDescriptor["strategy"], value: string | null, role: string | null = null) => {
      if (!value) return;
      try { candidates.push(validateVision("VisualLocatorDescriptor", { strategy, value, role, scope })); }
      catch { redacted ||= !safeLocatorValue(value); }
    };
    if (expected) candidates.push(validateVision("VisualLocatorDescriptor", expected));
    else {
      if (details.role) for (const name of details.names) candidate("role", name, details.role);
      for (const label of details.labels) candidate("label", label);
      candidate("test_id", details.testId);
      for (const [attr, value] of details.attributes) if (value && !/["\\\r\n]/.test(value)) candidate("css", `${details.tag}[${attr}="${value}"]`);
    }
    let maxCount = 0;
    for (const descriptor of candidates) {
      if (!await uniqueScopes(page, descriptor.scope)) continue;
      const locator = resolveDescriptor(page, descriptor);
      const count = await locator.count(); maxCount = Math.max(maxCount, Math.min(count, 100_000));
      if (count !== 1 || !await locator.evaluate((element, source) => element === source, target).catch(() => false)) continue;
      if (!await locator.isVisible() || !await locator.isEnabled() || (editable && !await locator.isEditable()))
        return unresolved("not_found", "target_not_actionable", 1);
      const box = await locator.boundingBox();
      if (!box || box.x < 0 || box.y < 0 || box.x + box.width > viewport.width || box.y + box.height > viewport.height)
        return unresolved("unsupported", "target_outside_viewport", 1);
      keepTarget = true;
      return { status: "verified", reason_code: null, descriptor, locator, target,
        bounding_box: { x: box.x / viewport.width, y: box.y / viewport.height, width: box.width / viewport.width, height: box.height / viewport.height },
        matched_count: 1, target_match: true, actionable: true, verified_at: new Date().toISOString() };
    }
    return expected ? unresolved("stale", "locator_target_mismatch", maxCount) :
      maxCount > 1 ? unresolved("ambiguous", "multiple_matches", maxCount) :
      redacted ? unresolved("redacted", "sensitive_locator_identity") : unresolved("not_found", "no_grounded_locator", maxCount);
  } finally { if (!keepTarget) await target.dispose(); }
}
