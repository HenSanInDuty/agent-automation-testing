import assert from "node:assert/strict";
import test from "node:test";
import type { ExecutedClick, VisualOperation } from "../generation-types";
import { advanceClickPreview, clickMarkerPosition, confirmedClick, type ClickPreviewHistory } from "./vision-click-model.ts";

const click: ExecutedClick = { x: 640 / 1279, y: 360 / 719, viewport_width: 1280, viewport_height: 720, before_frame_id: "before", confirmed_at: "2026-10-19T00:00:00Z" };
const step = (id: string, sequence = 1): VisualOperation => ({ id, sequence, action_kind: "click", status: "completed", executed_click: click, before: { id: "before", availability: "retained", reason_code: null } } as VisualOperation);
test("only confirmed clicks on their retained before frame are eligible", () => {
  assert.equal(confirmedClick(step("a"), "before"), click);
  assert.equal(confirmedClick({ ...step("a"), status: "failed" }, "before"), click);
  for (const patch of [{ status: "unknown" }, { status: "rejected" }, { status: "executing" }, { action_kind: "type" }, { executed_click: null }]) {
    assert.equal(confirmedClick({ ...step("a"), ...patch }, "before"), null);
  }
  assert.equal(confirmedClick(step("a"), "after"), null);
  assert.equal(confirmedClick({ ...step("a"), before: { id: "before", availability: "deleted", reason_code: "deleted" } }, "before"), null);
  for (const patch of [{ x: NaN }, { y: Infinity }, { x: -1 }, { viewport_width: 0 }, { before_frame_id: "other" }, { confirmed_at: "invalid" }]) {
    assert.equal(confirmedClick({ ...step("a"), executed_click: { ...click, ...patch } }, "before"), null);
  }
});

test("projection accounts for both letterbox directions, viewport edges and DPR", () => {
  assert.deepEqual(clickMarkerPosition(click, { width: 1280, height: 720 }, { width: 800, height: 600 }), { left: 400, top: 300 });
  assert.deepEqual(clickMarkerPosition(click, { width: 2560, height: 1440 }, { width: 800, height: 600 }), { left: 400, top: 300 });
  assert.deepEqual(clickMarkerPosition({ ...click, x: 0, y: 0 }, { width: 1280, height: 720 }, { width: 800, height: 600 }), { left: 0, top: 75 });
  assert.deepEqual(clickMarkerPosition({ ...click, x: 0, y: 0 }, { width: 1280, height: 720 }, { width: 1000, height: 360 }), { left: 180, top: 0 });
  assert.deepEqual(clickMarkerPosition({ ...click, x: 1, y: 1 }, { width: 1280, height: 720 }, { width: 1280, height: 720 }), { left: 1279, top: 719 });
  assert.equal(clickMarkerPosition(click, { width: 1, height: 1 }, { width: 800, height: 600 }), null);
  assert.equal(clickMarkerPosition(click, { width: 1280, height: 720 }, { width: 0, height: 0 }), null);
});

test("bootstrap and resume skip backlog; finalization at the same sequence and batches preview once", () => {
  let history: ClickPreviewHistory = { initialized: false, following: false, seen: new Set() };
  const update = (items: VisualOperation[], follow = true) => {
    const next = advanceClickPreview(items, history, follow); history = next.history; return next.operation?.id ?? null;
  };
  assert.equal(update([]), null);
  assert.equal(update([step("old"), { ...step("pending", 2), status: "executing" }]), null);
  assert.equal(update([step("old"), step("pending", 2)]), "pending");
  assert.equal(update([step("old"), step("pending", 2)]), null);
  assert.equal(update([step("a", 3), step("b", 4)]), "b");
  assert.equal(update([step("c", 5)], false), null);
  assert.equal(update([step("c", 5), step("d", 6)]), null);
  assert.equal(update([step("d", 6), step("e", 7)]), "e");
});
