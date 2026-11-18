/** Worker-owned visual affordances. No site names, CSS classes or label keywords. */
export type ButtonSemantic = { path: string; kind: "native" | "styled_link" | "custom" };

// Self-contained for page.evaluate and ElementHandle.evaluate (including tsx).
// Only structural paths and categories are returned; no page text or form values.
export function visualButtonSemantics(target?: Element | void): ButtonSemantic[] {
  const rules = {
    path(el: Element): string | null {
      const parts: string[] = [];
      let node: Element | null = el;
      while (node && node.tagName !== "HTML" && parts.length < 25) {
        const parent: Element | null = node.parentElement;
        if (!parent) return null;
        const siblings = Array.from(parent.children).filter(other => other.tagName === node!.tagName);
        parts.unshift(`${node.tagName.toLowerCase()}:nth-of-type(${siblings.indexOf(node) + 1})`);
        node = parent;
      }
      const path = `html > ${parts.join(" > ")}`;
      return node?.tagName === "HTML" && parts.length <= 24 && path.length <= 1024 ? path : null;
    },
    decorated(el: Element): boolean {
      const s = getComputedStyle(el);
      return s.backgroundImage !== "none" ||
        (parseFloat(s.borderRadius) >= 3 && (parseFloat(s.borderTopWidth) > 0 ||
          !["transparent", "rgba(0, 0, 0, 0)"].includes(s.backgroundColor)));
    },
    classify(el: Element): ButtonSemantic["kind"] | null {
      if (el.getRootNode() !== document) return null;
      // Reject decorative containers before layout/style/ancestor reads. This is
      // the same eligibility rule as below, without expensive geometry work.
      const native = el.matches('[role="button"],button:not([role]),input[type="button"],input[type="submit"],input[type="reset"]');
      const link = el.matches('a[href]');
      if (!native && (!el.matches('a[href],div,span') ||
          (!link && typeof (el as HTMLElement).onclick !== "function"))) return null;
      const r = el.getBoundingClientRect(), s = getComputedStyle(el);
      if (r.width <= 0 || r.height <= 0) return null;
      for (let p: Element | null = el; p; p = p.parentElement) {
        const style = getComputedStyle(p);
        if (style.display === "none" || style.visibility !== "visible" || +style.opacity === 0) return null;
      }
      if (native) return "native";
      // Pointer styling alone also occurs on articles and image galleries.
      // Require a compact, decorated action surface and exclude nested controls.
      if (!el.matches('a[href],div,span') || r.width > 480 || r.height > 280 ||
          r.width * r.height > 105000 || (el.textContent?.trim().length ?? 0) > 80 ||
          el.querySelector('a[href],button,input,textarea,select')) return null;
      if (!link && (typeof (el as HTMLElement).onclick !== "function" || s.cursor !== "pointer" ||
          el.parentElement?.closest('button,a[href],[role="button"]'))) return null;
      let decorated = this.decorated(el);
      const parent = el.parentElement;
      if (!decorated && link && s.position === "absolute" && parent) {
        const pr = parent.getBoundingClientRect();
        const overlay = Math.abs(r.x - pr.x) <= 3 && Math.abs(r.y - pr.y) <= 3 &&
          Math.abs(r.width - pr.width) <= 3 && Math.abs(r.height - pr.height) <= 3;
        // Transparent hit areas over a button sprite, common on game sites.
        decorated = overlay && (this.decorated(parent) || Array.from(parent.children).some(child =>
          child !== el && child.matches('img,svg') && getComputedStyle(child).pointerEvents === "none"));
      }
      return decorated ? link ? "styled_link" : "custom" : null;
    },
  };
  const result: ButtonSemantic[] = [];
  const elements = target ? [target] : Array.from(document.querySelectorAll('button,input,[role="button"],a[href],div,span'));
  for (const el of elements.slice(0, 5000)) {
    const kind = rules.classify(el), path = kind && rules.path(el);
    if (kind && path) result.push({ path, kind });
  }
  return result;
}
