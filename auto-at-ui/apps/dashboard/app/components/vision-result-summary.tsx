import Link from "next/link";
import type { VisionResult } from "../generation-types";
import { visionResultExportUrl } from "../generation-api";
import { visionResultLabel } from "./vision-operation-model";
import { visionFailureMessage } from "./vision-provider-model";

const outcomeLabels: Record<string, string> = {
  unsupported_target: "No supported control at the proposed position",
  multiple_matches: "More than one control matches this locator",
  no_grounded_locator: "A unique locator could not be verified",
  state_mismatch: "Page changed before the action",
  target_not_actionable: "Control is hidden, disabled or not editable",
  observed: "Action recorded; business outcome unverified",
};

export function VisionResultSummary({ result, apiUrl, compact = false }: { result: VisionResult; apiUrl: string; compact?: boolean }) {
  const report = result.exploration_report;
  const finished = ["completed", "unavailable", "cancelled"].includes(result.exploration_state);
  if (compact) return <section className="workspace-section vision-result-compact" aria-label="Exploration summary">
    <div className="section-heading"><h2>{visionResultLabel(result.exploration_state)}</h2>{report && <span>{report.summary.controls_acted_on} control actions recorded</span>}</div>
    {result.completion_reason && <p>{visionFailureMessage(result.completion_reason) ?? result.completion_reason.replaceAll("_", " ")}</p>}
    <p>{finished ? "Partial coverage. Recorded actions are not passed tests." : "Following recorded browser actions."}</p>
    {result.evidence_status === "legacy_evidence_only" && <p>Legacy evidence only. Verified locators were not recorded for this session.</p>}
    {result.links.generation.state === "failed" && <p>Draft generation failed. Exploration evidence is still available.</p>}
    <div className="button-row">{(["draft", "run", "report"] as const).map((key) => result.links[key].href && <Link key={key} href={result.links[key].href!}>{key === "draft" ? "Review draft" : key === "run" ? "View run" : "View execution report"}</Link>)}</div>
  </section>;
  return <section id={`vision-report-${result.session_id}`} className="workspace-section vision-exploration-report" aria-label="Vision result">
    <div className="section-heading"><h2>Exploration report</h2><a className="button button--secondary" href={visionResultExportUrl(apiUrl, result.session_id)}>Download report JSON</a></div>
    <p><strong>{finished ? "Partial coverage - full page coverage is not established." : "Exploration in progress - report updates as actions finish."}</strong></p>
    <p>Session: <code>{result.session_id}</code> · {visionResultLabel(result.exploration_state)}</p>
    <p>{visionFailureMessage(result.completion_reason) ?? result.completion_reason?.replaceAll("_", " ")}</p>
    {report && <>
      <dl className="vision-counts">
        <div><dt>Click / type actions recorded</dt><dd>{report.summary.controls_acted_on}</dd></div>
        <div><dt>Actions not executed</dt><dd>{report.summary.actions_rejected}</dd></div>
        <div><dt>Actions failed / unknown</dt><dd>{report.summary.actions_failed} / {report.summary.actions_unknown}</dd></div>
        <div><dt>Scrolls completed</dt><dd>{report.summary.scrolls_completed}</dd></div>
        <div><dt>Candidates not attempted</dt><dd>{report.summary.candidates_not_attempted}</dd></div>
      </dl>
      <p>Session limits: {report.limits.max_steps} model requests, {report.limits.max_session_seconds} seconds, {report.limits.max_hops} hops, {report.limits.max_states} states. A stopped session does not mean the bottom of the page was reached.</p>
      {report.findings.length ? <div className="table-wrap"><table>
        <caption>Recorded exploration actions</caption>
        <thead><tr><th>Operation</th><th>Control / action</th><th>Result</th><th>Observation</th></tr></thead>
        <tbody>{report.findings.map(item => <tr key={item.operation_id}>
          <td>{item.sequence}</td><td>{item.target ?? (item.action_kind === "scroll" || item.action_kind === "wait" ? "Page" : "Unresolved target")}<br />{item.action_kind}</td>
          <td>{item.status === "completed" ? "Observed" : item.status === "rejected" ? "Not executed" : item.status.replaceAll("_", " ")}</td>
          <td>{outcomeLabels[item.reason_code ?? ""] ?? item.reason_code?.replaceAll("_", " ") ?? "Pending"}{item.status === "completed" && <><br />URL: {item.url_change}; image: {item.visual_change}</>}</td>
        </tr>)}</tbody>
      </table></div> : <p>No exploration action has been recorded yet.</p>}
    </>}
    <p>Exploration is bounded and does not prove every control works. Observed actions are not passed tests.</p>
    {result.evidence_status === "legacy_evidence_only" && <p>Legacy evidence only. Verified locators were not recorded for this session.</p>}
    <details><summary>Evidence counts</summary><dl className="vision-counts">{Object.entries(result.counts).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl></details>
    <h3>Generated test and execution report</h3>
    <p>The exploration report above is available even when exploration stops early. A Playwright execution report becomes available after a generated draft is approved and run. Draft generation uses a separate text provider.</p>
    <ul className="stack-list">{Object.entries(result.links).map(([key, link]) => <li key={key}><strong>{key === "report" ? "Execution report" : key}: </strong>{key === "generation" && link.state === "failed" ? "Draft generation failed" : visionResultLabel(link.state)}{link.reason_code && ` — ${link.reason_code.replaceAll("_", " ")}`}{link.href && <> · <Link href={link.href}>{key === "draft" ? "Review draft" : key === "report" ? "View Playwright result" : "Open run"}</Link></>}</li>)}</ul>
    <p>{result.limitations.join(" ")}</p>
  </section>;
}
