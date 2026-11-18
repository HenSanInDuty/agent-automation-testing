import type { ElementHandle, Page } from "@playwright/test";
import { canonical, digest, requireVision } from "./vision-contract.js";
import type { DomSnapshot } from "./vision-dom.js";

// Private comparison material stays in worker RAM, never in model input or logs.
export async function targetActionSignature(target: ElementHandle<Element>): Promise<string> {
  return digest(await target.evaluate(el => JSON.stringify([
    el.tagName, Array.from(el.attributes).filter(a => !["style", "class"].includes(a.name))
      .map(a => [a.name, a.value]).sort(),
    el.textContent, (el as HTMLAnchorElement).href, (el as HTMLInputElement).disabled,
    (el as HTMLInputElement).readOnly, (el as HTMLInputElement).form?.action,
    (el as HTMLInputElement).form?.method,
  ])));
}

export async function targetSignature(target: ElementHandle<Element>): Promise<string> {
  return digest(await target.evaluate(el => {
    const ancestors: unknown[] = [];
    for (let node: Element | null = el; node;) {
      ancestors.push([node.tagName, Array.from(node.attributes)
        .filter(a => a.name !== "style" && (node === el || a.name !== "class"))
        .map(a => [a.name, a.value]).sort(),
      Array.from(node.childNodes).filter(n => n.nodeType === Node.TEXT_NODE).map(n => n.textContent)]);
      node = node.parentElement ?? (node.getRootNode() instanceof ShadowRoot
        ? (node.getRootNode() as ShadowRoot).host : null);
    }
    return JSON.stringify([ancestors, el.textContent, el.ownerDocument.URL,
      (el as HTMLAnchorElement).href, (el as HTMLInputElement).form?.action,
      (el as HTMLInputElement).form?.method]);
  }));
}

export async function contextSignature(page: Page): Promise<string> {
  return digest(await page.evaluate(() => JSON.stringify(
    Array.from(document.querySelectorAll('dialog,[role="dialog"],[aria-modal="true"],main,form,section[id],h1,h2,h3'))
      .filter(el => { const r = el.getBoundingClientRect(), s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && r.bottom > 0 && r.top < innerHeight &&
          s.visibility === "visible" && s.display !== "none"; })
      .map(el => [el.tagName, Array.from(el.attributes).filter(a => !["style", "class"].includes(a.name))
        .map(a => [a.name, a.value]).sort(), el.matches("h1,h2,h3") ? el.textContent : null]),
  )));
}

export async function revalidateDom(previous: DomSnapshot, fresh: DomSnapshot, ids: string[]): Promise<void> {
  const a = previous.state, b = fresh.state;
  requireVision(previous.page === fresh.page && a.url_fingerprint === b.url_fingerprint &&
    a.scroll_x === b.scroll_x && a.scroll_y === b.scroll_y &&
    a.form_presence_fingerprint === b.form_presence_fingerprint && a.privateForms === b.privateForms &&
    previous.contextSignature === fresh.contextSignature, "stale_dom_context");
  for (const key of ["tenant_id", "project_id", "session_id", "fencing_token"] as const)
    requireVision(previous.data.observation[key] === fresh.data.observation[key], "stale_dom_context");
  // A context-only scan must not adopt a reload at the same URL or a new document.
  requireVision(await fresh.document.evaluate((el, old) => el === old && el.isConnected,
    previous.document).catch(() => false), "stale_dom_context");
  const remap = new Map<string, string>();
  for (const id of ids) {
    const old = previous.data.bindings.find(item => item.element_id === id);
    const oldNode = previous.anonymousTargets.get(id);
    requireVision(old && oldNode, "stale_dom_target");
    const matches = fresh.data.bindings.filter(item => canonical(item.descriptor) === canonical(old.descriptor));
    requireVision(matches.length === 1, "stale_dom_target");
    const match = matches[0], node = fresh.anonymousTargets.get(match.element_id);
    requireVision(node && await node.evaluate((el, original) => el === original && el.isConnected, oldNode)
      .catch(() => false), "stale_dom_target");
    requireVision(previous.targetSignatures.get(id) === fresh.targetSignatures.get(match.element_id), "stale_dom_target");
    const oldElement = previous.data.observation.elements.find(item => item.element_id === id)!;
    const element = fresh.data.observation.elements.find(item => item.element_id === match.element_id)!;
    requireVision(canonical({ ...oldElement, element_id: null }) === canonical({ ...element, element_id: null }), "stale_dom_target");
    remap.set(match.element_id, id);
  }
  // Preserve model IDs only after worker verification. Frames, snapshot and geometry are fresh.
  for (const item of [...fresh.data.bindings, ...fresh.data.observation.elements]) {
    const original = item.element_id, mapped = remap.get(original);
    if (!mapped) continue;
    item.element_id = mapped;
    if (fresh.anonymousTargets.has(original)) {
      fresh.anonymousTargets.set(mapped, fresh.anonymousTargets.get(original)!);
      fresh.anonymousTargets.delete(original);
      fresh.targetSignatures.set(mapped, fresh.targetSignatures.get(original)!);
      fresh.targetSignatures.delete(original);
      if (fresh.actionSignatures?.has(original)) {
        fresh.actionSignatures.set(mapped, fresh.actionSignatures.get(original)!);
        fresh.actionSignatures.delete(original);
      }
    }
  }
}
