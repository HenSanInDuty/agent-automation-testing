import assert from "node:assert/strict";
import test from "node:test";

import { defaultTrajectoryPath, orderedAlternatives, orderedReplayFrames, replayMarkerPosition, trajectoryPathForEdge } from "./vision-replay-model.ts";
import { representativeTrajectory } from "./fixtures/vision-trajectory.ts";

test("replay frames are ordered by capture sequence and markers scale with the image", () => {
  const frames = orderedReplayFrames([
    { id: "b", sequence: 2 }, { id: "a", sequence: 1 }, { id: "c", sequence: 2 },
  ] as never);

  assert.deepEqual(frames.map((frame) => frame.id), ["a", "b", "c"]);
  assert.deepEqual(replayMarkerPosition({ x: .5, y: .5 }), {
    left: "50%", top: "50%",
  });
  assert.deepEqual(replayMarkerPosition({ x: -1, y: 999 }), {
    left: "0%", top: "100%",
  });
  assert.equal(replayMarkerPosition({ x: Number.NaN, y: 1 }), null);
});

test("trajectory selects observed branches and retains siblings as alternatives", () => {
  const trajectory = {
    states: [{ id: "root", parent_id: null, sequence: 1 }, { id: "child", parent_id: "root", sequence: 2 }],
    edges: [
      { id: "failed", parent_state_id: "root", child_state_id: null, confidence: .99, status: "failed", action: { kind: "click" } },
      { id: "observed", parent_state_id: "root", child_state_id: "child", confidence: .5, status: "observed", action: { kind: "click" } },
    ],
  } as never;
  assert.deepEqual(defaultTrajectoryPath(trajectory).map((edge) => edge.id), ["observed"]);
  assert.deepEqual(orderedAlternatives(trajectory, "root").map((edge) => edge.id), ["failed", "observed"]);
});

test("representative fixture covers sibling, terminal, failed, and missing-frame evidence", () => {
  assert.deepEqual(defaultTrajectoryPath(representativeTrajectory).map((edge) => edge.id), ["click-observed"]);
  assert.equal(orderedAlternatives(representativeTrajectory, "root").length, 4);
  assert.equal(representativeTrajectory.states[1].frame_id, null);
  assert.equal(representativeTrajectory.edges.find((edge) => edge.id === "failed-capture")?.outcome_code, "capture_failed");
});

test("alternative selection builds a different path and malformed cycles terminate", () => {
  assert.deepEqual(trajectoryPathForEdge(representativeTrajectory, "failed-capture").map((e) => e.id), ["failed-capture"]);
  const cyclic = structuredClone(representativeTrajectory);
  cyclic.edges[0].child_state_id = "root";
  assert.equal(defaultTrajectoryPath(cyclic).length, 1);
  assert.equal(trajectoryPathForEdge(cyclic, "click-observed").length, 1);
});
