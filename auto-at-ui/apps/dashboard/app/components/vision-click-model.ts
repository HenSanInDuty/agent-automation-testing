import type { ExecutedClick, VisualLocator, VisualOperation } from "../generation-types";

export function confirmedClickTarget(operation: VisualOperation | undefined, locator: VisualLocator | undefined, frameId?: string | null): VisualLocator["bounding_box"] {
  const click = confirmedClick(operation, frameId);
  const box = locator?.bounding_box;
  if (!click || !box || locator?.status !== "verified" || locator.id !== operation?.locator_id || locator.operation_id !== operation?.id ||
    ![box.x, box.y, box.width, box.height].every(Number.isFinite) || box.width <= 0 || box.height <= 0 ||
    box.x < 0 || box.y < 0 || box.x + box.width > 1 || box.y + box.height > 1) return null;
  const x = click.x * (click.viewport_width - 1) / click.viewport_width;
  const y = click.y * (click.viewport_height - 1) / click.viewport_height;
  return x >= box.x && x <= box.x + box.width && y >= box.y && y <= box.y + box.height ? box : null;
}

export function clickTargetPosition(click: ExecutedClick, box: NonNullable<VisualLocator["bounding_box"]>, image: { width: number; height: number }, container: { width: number; height: number }) {
  const origin = clickMarkerPosition({ ...click, x: 0, y: 0 }, image, container);
  if (!origin) return null;
  const scale = Math.min(container.width / image.width, container.height / image.height);
  return { left: origin.left + box.x * image.width * scale, top: origin.top + box.y * image.height * scale, width: box.width * image.width * scale, height: box.height * image.height * scale };
}

export function confirmedClick(operation: VisualOperation | undefined, frameId?: string | null): ExecutedClick | null {
  const click = operation?.executed_click;
  if (!operation || !click || operation.action_kind !== "click" || !["completed", "failed"].includes(operation.status) ||
    operation.before.availability !== "retained" || !frameId || frameId !== operation.before.id ||
    click.before_frame_id !== frameId) return null;
  if (![click.x, click.y].every((value) => Number.isFinite(value) && value >= 0 && value <= 1) ||
    ![click.viewport_width, click.viewport_height].every((value) => Number.isSafeInteger(value) && value > 1 && value <= 16384) ||
    !Number.isFinite(Date.parse(click.confirmed_at))) return null;
  return click;
}

export function clickMarkerPosition(click: ExecutedClick, image: { width: number; height: number }, container: { width: number; height: number }): { left: number; top: number } | null {
  if (![image.width, image.height, container.width, container.height].every((value) => Number.isFinite(value) && value > 0) ||
    Math.abs(image.width / image.height - click.viewport_width / click.viewport_height) > 0.001) return null;
  const scale = Math.min(container.width / image.width, container.height / image.height);
  const width = image.width * scale, height = image.height * scale;
  return {
    left: (container.width - width) / 2 + click.x * (click.viewport_width - 1) / click.viewport_width * width,
    top: (container.height - height) / 2 + click.y * (click.viewport_height - 1) / click.viewport_height * height,
  };
}

export type ClickPreviewHistory = { initialized: boolean; following: boolean; seen: Set<string> };
export function advanceClickPreview(items: VisualOperation[], history: ClickPreviewHistory, following: boolean): { history: ClickPreviewHistory; operation: VisualOperation | null } {
  const candidates = items.filter((item) => confirmedClick(item, item.before.id));
  const seen = new Set(history.seen);
  let operation: VisualOperation | null = null;
  for (const item of candidates) {
    if (history.initialized && history.following && following && !seen.has(item.id) &&
      (!operation || operation.sequence < item.sequence)) operation = item;
    seen.add(item.id);
  }
  return { history: { initialized: history.initialized || items.length > 0, following, seen }, operation };
}
