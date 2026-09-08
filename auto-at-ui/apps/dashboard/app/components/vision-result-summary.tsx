import Link from "next/link";
import type { VisionResult } from "../generation-types";
import { visionResultExportUrl } from "../generation-api";
import { visionResultLabel } from "./vision-operation-model";

export function VisionResultSummary({ result, apiUrl }: { result: VisionResult; apiUrl: string }) {
  return <section className="workspace-section" aria-label="Vision result">
    <h2>{visionResultLabel(result.exploration_state)}</h2>
    <p>Selected session: <code>{result.session_id}</code></p>
    <p>{result.completion_reason?.replaceAll("_", " ")}</p>
    {result.evidence_status === "legacy_evidence_only" && <p>Legacy evidence only. Verified locators were not recorded for this session.</p>}
    <dl className="vision-counts">{Object.entries(result.counts).map(([key, value]) => <div key={key}><dt>{key.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl>
    <ul className="stack-list">{Object.entries(result.links).map(([key, link]) => <li key={key}><strong>{key}: </strong>{key === "generation" && link.state === "failed" ? "Draft generation failed" : visionResultLabel(link.state)}{link.reason_code && ` — ${link.reason_code.replaceAll("_", " ")}`}{link.href && <> · <Link href={link.href}>{key === "draft" ? "Review draft" : key === "report" ? "View Playwright result" : "Open run"}</Link></>}</li>)}</ul>
    <p>{result.limitations.join(" ")}</p>
    <a className="button button--secondary" href={visionResultExportUrl(apiUrl, result.session_id)}>Export exploration JSON</a>
  </section>;
}
