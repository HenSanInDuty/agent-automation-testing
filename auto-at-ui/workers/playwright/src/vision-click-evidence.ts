import type { ElementHandle } from "@playwright/test";

/** Capture the trusted pointer press before navigation destroys the document.
 * The caller publishes it only after the corresponding locator click succeeds. */
export async function observeClick(target: ElementHandle<Element>) {
  const handle = await target.evaluateHandle((element) => {
    let finish: (point: { x: number; y: number; width: number; height: number } | null) => void;
    const promise = new Promise<{ x: number; y: number; width: number; height: number } | null>((resolve) => { finish = resolve; });
    const doc = element.ownerDocument;
    const view = doc.defaultView!;
    // Object methods stay self-contained when tsx serializes this callback.
    const capture = {
      promise,
      listener(event: MouseEvent) {
        if (!event.isTrusted || !event.composedPath().includes(element) || view !== view.top) return;
        doc.removeEventListener("pointerdown", capture.listener, true);
        finish({ x: event.clientX, y: event.clientY, width: view.innerWidth, height: view.innerHeight });
      },
      cancel() { doc.removeEventListener("pointerdown", capture.listener, true); finish(null); },
    };
    doc.addEventListener("pointerdown", capture.listener, true);
    return capture;
  });
  const result = handle.evaluate((capture) => capture.promise).catch(() => null);
  return {
    result,
    async dispose() {
      await handle.evaluate((capture) => capture.cancel()).catch(() => undefined);
      await handle.dispose();
    },
  };
}
