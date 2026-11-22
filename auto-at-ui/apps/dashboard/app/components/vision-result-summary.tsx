import { Download } from "lucide-react";
import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { VisionResult } from "../generation-types";
import { visionResultExportUrl } from "../generation-api";
import { visionResultLabel } from "./vision-operation-model";
import { visionFailureMessage } from "./vision-provider-model";
import { Disclosure, Hint, ItemList } from "./agent-ui";
import { Section } from "./section";
import { VisionConclusion } from "./vision-conclusion";

const outcomeLabels: Record<string, string> = {
  unsupported_target: "No supported control at the proposed position",
  multiple_matches: "More than one control matches this locator",
  no_grounded_locator: "A unique locator could not be verified",
  state_mismatch: "Page changed before the action",
  target_not_actionable: "Control is hidden, disabled or not editable",
  observed: "Action recorded; business outcome unverified",
  download_started: "Download initiated; transfer cancelled after detection. File content unverified.",
};

const th = "px-3 py-2 text-left text-xs font-medium tracking-wide text-muted-foreground uppercase";
const td = "px-3 py-2.5 align-top [overflow-wrap:anywhere]";

export function VisionResultSummary({ result, apiUrl, compact = false }: { result: VisionResult; apiUrl: string; compact?: boolean }) {
  const report = result.exploration_report;
  const partial = ["exploration_call_limit", "exploration_coverage_incomplete"].includes(result.completion_reason ?? "");
  const stateLabel = partial ? "Partial exploration" : visionResultLabel(result.exploration_state);
  if (compact) return <Section aria-label="Exploration summary" className="gap-4 py-5" contentClassName="grid gap-4">
    <VisionConclusion conclusion={report?.conclusion} />
    <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1"><h2 className="text-base font-semibold tracking-tight">{stateLabel}</h2>{report && <span className="text-sm text-muted-foreground">{report.summary.controls_acted_on} control actions recorded</span>}</div>
    {result.completion_reason && <Hint>{visionFailureMessage(result.completion_reason) ?? result.completion_reason.replaceAll("_", " ")}</Hint>}
    {result.evidence_status === "legacy_evidence_only" && <Hint>Legacy evidence only. Verified locators were not recorded for this session.</Hint>}
    {result.links.generation.state === "failed" && <Hint>Draft generation failed. Exploration evidence is still available.</Hint>}
    <div className="flex flex-wrap gap-x-5 gap-y-1 text-sm font-medium">{(["draft", "run", "report"] as const).map((key) => result.links[key].href && <Link key={key} className="text-primary underline-offset-4 hover:underline" href={result.links[key].href!}>{key === "draft" ? "Review draft" : key === "run" ? "View run" : "View execution report"}</Link>)}</div>
  </Section>;
  return <section id={`vision-report-${result.session_id}`} aria-label="Vision result" className="grid min-w-0 scroll-mt-6 gap-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-base font-semibold tracking-tight">Exploration report</h2><a className={buttonVariants({ variant: "outline", size: "sm" })} href={visionResultExportUrl(apiUrl, result.session_id)}><Download aria-hidden="true" />Download report JSON</a></div>
    <VisionConclusion conclusion={report?.conclusion} />
    <p className="text-sm">Session: <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs break-all">{result.session_id}</code> · {stateLabel}</p>
    <p className="text-sm text-muted-foreground">{visionFailureMessage(result.completion_reason) ?? result.completion_reason?.replaceAll("_", " ")}</p>
    {report && <>
      <dl className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">
        {[
          ["Click / type actions recorded", report.summary.controls_acted_on],
          ["Actions not executed", report.summary.actions_rejected],
          ["Actions failed / unknown", `${report.summary.actions_failed} / ${report.summary.actions_unknown}`],
          ["Scrolls completed", report.summary.scrolls_completed],
          ["Candidates not attempted", report.summary.candidates_not_attempted],
        ].map(([label, value]) => <div key={label} className="rounded-lg border bg-muted/30 px-3 py-2.5"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 text-xl font-semibold tabular-nums">{value}</dd></div>)}
      </dl>
      <p className="text-sm text-muted-foreground">Session limits: {report.limits.max_steps} model requests, {report.limits.step_timeout_seconds != null ? `${report.limits.step_timeout_seconds} seconds per step (no session time limit)` : `${report.limits.max_session_seconds} seconds per session`}, {report.limits.max_hops} hops, {report.limits.max_states} states. A stopped session does not mean the bottom of the page was reached.</p>
      {report.findings.length ? <div className="max-h-[32rem] overflow-auto rounded-lg border"><table className="w-full min-w-[34rem] text-sm">
        <caption className="border-b bg-card px-4 py-3 text-left text-sm font-semibold">Recorded exploration actions</caption>
        <thead className="sticky top-0 bg-card shadow-[0_1px_0_var(--border)]"><tr><th className={th}>Operation</th><th className={th}>Control / action</th><th className={th}>Result</th><th className={th}>Observation</th></tr></thead>
        <tbody className="divide-y">{report.findings.map(item => <tr key={item.operation_id} className="hover:bg-muted/40">
          <td className={cn(td, "tabular-nums")}>{item.sequence}</td><td className={td}>{item.target ?? (item.action_kind === "scroll" || item.action_kind === "wait" ? "Page" : "Unresolved target")}<br /><span className="text-xs text-muted-foreground">{item.action_kind}</span></td>
          <td className={td}>{item.status === "completed" ? "Observed" : item.status === "rejected" ? "Not executed" : item.status.replaceAll("_", " ")}</td>
          <td className={td}>{outcomeLabels[item.reason_code ?? ""] ?? item.reason_code?.replaceAll("_", " ") ?? "Pending"}{item.status === "completed" && <><br /><span className="text-xs text-muted-foreground">URL: {item.url_change}; image: {item.visual_change}</span></>}</td>
        </tr>)}</tbody>
      </table></div> : <Hint>No exploration action has been recorded yet.</Hint>}
    </>}
    <Hint>Exploration is bounded and does not prove every control works. Observed actions are not passed tests.</Hint>
    {result.evidence_status === "legacy_evidence_only" && <Hint>Legacy evidence only. Verified locators were not recorded for this session.</Hint>}
    <Disclosure variant="plain" title="Evidence counts"><dl className="grid grid-cols-[repeat(auto-fit,minmax(9rem,1fr))] gap-3">{Object.entries(result.counts).map(([key, value]) => <div key={key} className="rounded-lg border bg-muted/30 px-3 py-2"><dt className="text-xs text-muted-foreground capitalize">{key.replaceAll("_", " ")}</dt><dd className="mt-1 text-lg font-semibold tabular-nums">{value}</dd></div>)}</dl></Disclosure>
    <h3 className="text-sm font-semibold">Generated test and execution report</h3>
    <Hint>The exploration report above is available even when exploration stops early. A Playwright execution report becomes available after a generated draft is approved and run. Draft generation uses a separate text provider.</Hint>
    <ItemList>{Object.entries(result.links).map(([key, link]) => <li key={key}><strong className="font-medium capitalize">{key === "report" ? "Execution report" : key}: </strong>{key === "generation" && link.state === "failed" ? "Draft generation failed" : visionResultLabel(link.state)}{link.reason_code && ` — ${link.reason_code.replaceAll("_", " ")}`}{link.href && <> · <Link className="font-medium text-primary underline-offset-4 hover:underline" href={link.href}>{key === "draft" ? "Review draft" : key === "report" ? "View Playwright result" : "Open run"}</Link></>}</li>)}</ItemList>
    <Hint>{result.limitations.join(" ")}</Hint>
  </section>;
}
