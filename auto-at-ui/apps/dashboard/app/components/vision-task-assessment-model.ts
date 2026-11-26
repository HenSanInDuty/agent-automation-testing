import type { VisionTaskAssessment } from "../generation-types";
import type { StatusTone } from "./status-model";

type Assessment = VisionTaskAssessment;

export const taskAssessmentAdvisoryNotice = "Advisory assessment by the agent. It is not a test verdict; a deterministic test run decides pass/fail.";

const statusLabels: Record<Assessment["status"], string> = {
  achieved: "Task achieved",
  not_achieved: "Task not achieved (page finding)",
  blocked: "Blocked",
  inconclusive: "Inconclusive",
};
const statusTones: Record<Assessment["status"], StatusTone> = { achieved: "success", not_achieved: "danger", blocked: "warning", inconclusive: "neutral" };
const checkLabels: Record<Assessment["checks"][number]["status"], string> = { met: "Met", not_met: "Not met", not_checked: "Not checked" };
const checkTones: Record<Assessment["checks"][number]["status"], StatusTone> = { met: "success", not_met: "danger", not_checked: "muted" };

/** Unknown values (a newer backend) fall back to a neutral, readable label instead of throwing. */
export function taskAssessmentLabel(status: string): string {
  return Object.hasOwn(statusLabels, status) ? statusLabels[status as Assessment["status"]] : status.replaceAll("_", " ");
}
export function taskAssessmentTone(status: string): StatusTone {
  return Object.hasOwn(statusTones, status) ? statusTones[status as Assessment["status"]] : "neutral";
}
export function taskCheckLabel(status: string): string {
  return Object.hasOwn(checkLabels, status) ? checkLabels[status as keyof typeof checkLabels] : status.replaceAll("_", " ");
}
export function taskCheckTone(status: string): StatusTone {
  return Object.hasOwn(checkTones, status) ? checkTones[status as keyof typeof checkTones] : "neutral";
}
export function taskAssessmentSourceLabel(source: string): string {
  return source === "controller" ? "Reported by the platform" : "Reported by the agent";
}

/** Controller-counted facts; independent of what the agent claims. */
export function taskAssessmentFacts(facts: Assessment["facts"]): string {
  return `${facts.actions_completed ?? 0} actions completed, ${facts.actions_failed ?? 0} failed or rejected, ${facts.actions_blocked_or_skipped ?? 0} blocked or skipped`;
}

/** Why the session ended, for the cases where the status alone is not self-explanatory. */
export function taskAssessmentStopNote(assessment: Pick<Assessment, "status" | "stop_reason">): string | null {
  if (assessment.stop_reason === "agent_step_limit") return assessment.status === "inconclusive"
    ? "The model call budget ran out before the agent could finish the task." : "The model call budget ran out; this assessment covers only what was done before then.";
  if (assessment.stop_reason === "agent_stopped") return "The agent stopped because it found no safe action to continue.";
  return null;
}

/** Only a well-formed assessment replaces failure copy; anything else keeps the existing behaviour. */
export function validTaskAssessment(value: unknown): Assessment | null {
  const item = value as Partial<Assessment> | null | undefined;
  return item && typeof item === "object" && typeof item.status === "string" && Array.isArray(item.checks) && item.facts && typeof item.facts === "object" ? item as Assessment : null;
}

/** Completion text for a result (`describe` is `visionFailureMessage`; passed in so models stay import-free). A session that ended with an assessment is not a failure, so no failure copy is shown. */
export function completionNote(reason: string | null | undefined, assessment: unknown, describe: (reason: string) => string | undefined): string | undefined {
  if (!reason || validTaskAssessment(assessment)) return undefined;
  return describe(reason) ?? reason.replaceAll("_", " ");
}

/** Badge for a session row/header: the assessment status for assessed agent sessions, otherwise null (use the session state). */
export function assessmentBadge(assessment: unknown): { label: string; tone: StatusTone } | null {
  const item = validTaskAssessment(assessment);
  return item ? { label: taskAssessmentLabel(item.status), tone: taskAssessmentTone(item.status) } : null;
}
