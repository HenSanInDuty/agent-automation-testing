import assert from "node:assert/strict";
import test from "node:test";
import type { VisionTaskAssessment } from "../generation-types";
import { assessmentBadge, completionNote, taskAssessmentAdvisoryNotice, taskAssessmentFacts, taskAssessmentLabel, taskAssessmentSourceLabel, taskAssessmentStopNote, taskAssessmentTone, taskCheckLabel, validTaskAssessment } from "./vision-task-assessment-model.ts";
import { visionFailureMessage } from "./vision-provider-model.ts";

const assessment: VisionTaskAssessment = {
  schema_version: "v1", status: "achieved", summary: "Done", checks: [{ expectation: "Cart has 1 item", status: "met", evidence: "Badge shows 1" }],
  source: "agent", stop_reason: "agent_done", facts: { actions_completed: 4, actions_failed: 1, actions_blocked_or_skipped: 2 }, advisory: true,
};

test("status labels and tones are plain and distinct", () => {
  assert.equal(taskAssessmentLabel("achieved"), "Task achieved");
  assert.equal(taskAssessmentLabel("not_achieved"), "Task not achieved (page finding)");
  assert.equal(taskAssessmentLabel("blocked"), "Blocked");
  assert.equal(taskAssessmentLabel("inconclusive"), "Inconclusive");
  assert.equal(taskAssessmentLabel("something_new"), "something new");
  assert.deepEqual(["achieved", "not_achieved", "blocked", "inconclusive"].map(taskAssessmentTone), ["success", "danger", "warning", "neutral"]);
  assert.equal(taskAssessmentTone("something_new"), "neutral");
  assert.equal(taskCheckLabel("not_met"), "Not met");
  assert.equal(taskCheckLabel("not_checked"), "Not checked");
});

test("facts sentence and source label", () => {
  assert.equal(taskAssessmentFacts(assessment.facts), "4 actions completed, 1 failed or rejected, 2 blocked or skipped");
  assert.equal(taskAssessmentSourceLabel("agent"), "Reported by the agent");
  assert.equal(taskAssessmentSourceLabel("controller"), "Reported by the platform");
  assert.match(taskAssessmentAdvisoryNotice, /not a test verdict/);
});

test("step limit explains the exhausted model call budget", () => {
  assert.match(taskAssessmentStopNote({ status: "inconclusive", stop_reason: "agent_step_limit" })!, /model call budget ran out/);
  assert.match(taskAssessmentStopNote({ status: "achieved", stop_reason: "agent_step_limit" })!, /budget/);
  assert.match(taskAssessmentStopNote({ status: "blocked", stop_reason: "agent_stopped" })!, /no safe action/);
  assert.equal(taskAssessmentStopNote({ status: "achieved", stop_reason: "agent_done" }), null);
});

test("an assessment replaces failure copy; without one existing behaviour is kept", () => {
  assert.equal(completionNote("agent_done", assessment, visionFailureMessage), undefined);
  assert.equal(completionNote(null, null, visionFailureMessage), undefined);
  assert.match(completionNote("agent_done", null, visionFailureMessage)!, /agent finished/);
  assert.match(completionNote("provider_timeout", null, visionFailureMessage)!, /did not respond/);
  assert.equal(completionNote("unknown_reason", undefined, visionFailureMessage), "unknown reason");
  assert.match(completionNote("provider_timeout", { status: 5 }, visionFailureMessage)!, /did not respond/);
});

test("badge helper ignores malformed or missing assessments", () => {
  assert.deepEqual(assessmentBadge(assessment), { label: "Task achieved", tone: "success" });
  assert.equal(assessmentBadge(null), null);
  assert.equal(assessmentBadge(undefined), null);
  assert.equal(validTaskAssessment("achieved"), null);
  assert.equal(validTaskAssessment({ status: "achieved" }), null);
});
