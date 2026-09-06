import assert from "node:assert/strict";
import test from "node:test";

import { orderedReplayFrames, replayMarkerPosition } from "./vision-replay-model.ts";

test("replay frames are ordered by capture sequence and markers scale with the image", () => {
  const frames = orderedReplayFrames([
    { id: "b", sequence: 2 }, { id: "a", sequence: 1 }, { id: "c", sequence: 2 },
  ] as never);

  assert.deepEqual(frames.map((frame) => frame.id), ["a", "b", "c"]);
  assert.deepEqual(replayMarkerPosition({ x: 320, y: 180 }, { width: 640, height: 360 }), {
    left: "50%", top: "50%",
  });
  assert.deepEqual(replayMarkerPosition({ x: -1, y: 999 }, { width: 100, height: 100 }), {
    left: "0%", top: "100%",
  });
  assert.equal(replayMarkerPosition({ x: 1, y: 1 }, { width: 0, height: 1 }), null);
  assert.equal(replayMarkerPosition({ x: Number.NaN, y: 1 }, { width: 1, height: 1 }), null);
});
