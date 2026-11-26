import { cn } from "@/lib/utils";
import type { VisionTaskAssessment } from "../generation-types";
import { Hint, Notice } from "./agent-ui";
import { StatusBadge } from "./status-badge";
import { assessmentBadge, taskAssessmentAdvisoryNotice, taskAssessmentFacts, taskAssessmentLabel, taskAssessmentSourceLabel, taskAssessmentStopNote, taskAssessmentTone, taskCheckLabel, taskCheckTone } from "./vision-task-assessment-model";

const noticeTone = { success: "success", danger: "danger", warning: "warning", neutral: "neutral", muted: "neutral" } as const;

/** Session state badge that shows the task assessment status when the session has one. */
export function SessionStateBadge({ state, assessment }: { state: string; assessment?: VisionTaskAssessment | null }) {
  const badge = assessmentBadge(assessment);
  return badge ? <StatusBadge status={state} tone={badge.tone} className="normal-case">{badge.label}</StatusBadge> : <StatusBadge status={state} />;
}

export function VisionTaskAssessmentPanel({ assessment }: { assessment: VisionTaskAssessment }) {
  const tone = taskAssessmentTone(assessment.status);
  const stopNote = taskAssessmentStopNote(assessment);
  return <Notice tone={noticeTone[tone]} role="region" aria-label="Task assessment" className="grid gap-3 py-3.5">
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
      <h2 className="text-base font-semibold tracking-tight">Task assessment</h2>
      <StatusBadge status={assessment.status} tone={tone} className="normal-case">{taskAssessmentLabel(assessment.status)}</StatusBadge>
    </div>
    <p className="text-sm whitespace-pre-line">{assessment.summary}</p>
    {stopNote && <Hint className="text-foreground/80">{stopNote}</Hint>}
    {assessment.checks.length > 0 && <ul aria-label="Task checks" className="grid gap-2 text-sm">{assessment.checks.map((check, index) => <li key={index} className="grid min-w-0 gap-1 rounded-md border bg-background/60 px-3 py-2 min-[640px]:grid-cols-[minmax(0,1fr)_auto] min-[640px]:gap-x-4">
      <span className="font-medium">{check.expectation}</span>
      <StatusBadge status={check.status} tone={taskCheckTone(check.status)} className={cn("normal-case justify-self-start min-[640px]:justify-self-end")}>{taskCheckLabel(check.status)}</StatusBadge>
      {check.evidence && <span className="text-muted-foreground min-[640px]:col-span-2">{check.evidence}</span>}
    </li>)}</ul>}
    <p className="text-sm tabular-nums">{taskAssessmentFacts(assessment.facts)}</p>
    <p className="text-xs text-muted-foreground">{taskAssessmentSourceLabel(assessment.source)}. {taskAssessmentAdvisoryNotice}</p>
  </Notice>;
}
