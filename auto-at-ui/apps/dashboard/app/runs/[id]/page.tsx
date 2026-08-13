"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { artifactArchiveDownloadUrl, artifactArchiveEntriesUrl, artifactDownloadUrl } from "../../api-client";
import { ActivityTimeline } from "../../components/activity-timeline";
import { PageHeader } from "../../components/page-header";
import { StatusBadge } from "../../components/status-badge";
import { artifacts, cancelRun, run, runReport, type Artifact, type Run, type RunReport } from "../../run-api";

export default function RunDetailPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000";
  const id = String(useParams<{ id: string }>().id);
  const [item, setItem] = useState<Run | null>(null);
  const [evidence, setEvidence] = useState<Artifact[]>([]);
  const [report, setReport] = useState<RunReport | null>(null);
  const [reportMissing, setReportMissing] = useState(false);
  const [notice, setNotice] = useState("");
  const [preview, setPreview] = useState<Artifact | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [archiveEntries, setArchiveEntries] = useState<Array<{ path: string; size: number; is_directory: boolean }> | null>(null);

  useEffect(() => {
    Promise.all([run(apiUrl, id), artifacts(apiUrl, id), runReport(apiUrl, id).catch((error: { status?: number }) => { if (error.status === 404) { setReportMissing(true); return null; } throw error; })])
      .then(([next, files, nextReport]) => { setItem(next); setEvidence(files); setReport(nextReport); })
      .catch((error: Error) => setNotice(error.message));
  }, [apiUrl, id]);

  if (!item) return <><PageHeader eyebrow="Execution" title="Run detail" description="Loading deterministic run evidence." /><p className="panel">Loading...</p></>;
  const cancellable = item.status === "queued" || item.status === "running";
  const artifactForReference = (reference: string) => evidence.find((file) => file.uri === reference);
  const evidenceLinks = (references: string[]) => references.map((reference) => {
    const artifact = artifactForReference(reference);
    return artifact ? <a key={reference} href={artifactDownloadUrl(apiUrl, item.id, artifact.id)}>{artifact.kind}</a> : <span key={reference}>Verified evidence reference</span>;
  });
  const previewType = (file: Artifact) => {
    const path = file.uri.toLowerCase();
    if (file.content_type?.startsWith("image/") || path.endsWith(".png") || path.endsWith(".jpg") || path.endsWith(".jpeg")) return "image";
    if (file.content_type?.startsWith("video/") || path.endsWith(".webm") || path.endsWith(".mp4")) return "video";
    if (file.content_type?.startsWith("text/") || path.endsWith(".txt") || path.endsWith(".json")) return "text";
    return "binary";
  };
  const openPreview = async (file: Artifact) => {
    setPreview(file); setPreviewContent(null); setPreviewUrl(null); setArchiveEntries(null); setNotice("");
    try {
      if (file.uri.toLowerCase().endsWith(".zip") || file.content_type === "application/zip") {
        const response = await fetch(artifactArchiveEntriesUrl(apiUrl, item.id, file.id), { credentials: "include" });
        if (!response.ok) throw new Error("Unable to inspect this archive.");
        setArchiveEntries(await response.json() as Array<{ path: string; size: number; is_directory: boolean }>);
        return;
      }
      const response = await fetch(artifactDownloadUrl(apiUrl, item.id, file.id), { credentials: "include" });
      if (!response.ok) throw new Error("Unable to load this artifact preview.");
      if (previewType(file) === "text") setPreviewContent(await response.text());
      else setPreviewUrl(URL.createObjectURL(await response.blob()));
    } catch (error) { setPreview(null); setNotice(error instanceof Error ? error.message : "Unable to load this artifact preview."); }
  };
  return <>
    <PageHeader eyebrow="Execution" title={`Run ${item.id.slice(0, 8)}`} description="Immutable request, deterministic result, and verified evidence." actions={cancellable ? <button className="button button--danger" onClick={() => cancelRun(apiUrl, item.id).then(setItem).catch((error: Error) => setNotice(error.message))}>Cancel run</button> : undefined} />
    <section className="workspace-section"><div className="section-heading"><h2>Result</h2><StatusBadge status={item.status} /></div><ul className="detail-list"><li>Correlation ID: <code>{item.correlation_id}</code></li><li>Test: {item.test_case_id}</li><li>Revision: <code>{item.revision}</code></li>{item.terminal_summary && <li>Terminal summary: {item.terminal_summary}</li>}</ul></section>
    <ActivityTimeline apiUrl={apiUrl} runId={item.id} live={cancellable} />
    <section className="workspace-section"><div className="section-heading"><h2>Advisory report</h2>{report && <StatusBadge status={report.status} />}</div>{report?.status === "completed" && report.payload ? <><p>This advisory explanation cannot change the deterministic result.</p><h3>{report.payload.headline}</h3><p>{report.payload.what_ran}</p>{report.payload.observations.length > 0 && <><h3>Verified observations</h3><ul className="stack-list">{report.payload.observations.map((observation, index) => <li key={`${observation.text}-${index}`}>{observation.text}{observation.evidence_references.length > 0 && <> — {evidenceLinks(observation.evidence_references)}</>}</li>)}</ul></>}{report.payload.failure && <><h3>Failure detail</h3><ul className="detail-list"><li>Stage: {report.payload.failure.stage}</li><li>Location: {report.payload.failure.location}</li><li>Reason: {report.payload.failure.message}</li>{report.payload.failure.evidence_references.length > 0 && <li>Evidence: {evidenceLinks(report.payload.failure.evidence_references)}</li>}</ul></>}{report.payload.unverified_or_skipped.length > 0 && <><h3>Unverified or skipped scope</h3><ul className="stack-list">{report.payload.unverified_or_skipped.map((item) => <li key={item}>{item}</li>)}</ul></>}{report.payload.limitations.length > 0 && <><h3>Limitations</h3><ul className="stack-list">{report.payload.limitations.map((item) => <li key={item}>{item}</li>)}</ul></>}<p>Provenance: {report.provenance.provider ?? "provider unavailable"}{report.provenance.model ? ` / ${report.provenance.model}` : ""}; prompt {report.prompt_version}.</p></> : report?.status === "unavailable" ? <p>The advisory report is unavailable: {report.unavailable_reason ?? "No safe reason was recorded."} The deterministic runner result remains the primary verdict.</p> : cancellable ? <p>Report will be prepared after a deterministic result.</p> : reportMissing ? <p>No report is available for this historical run.</p> : <p>Report will be prepared after a deterministic result.</p>}</section>
    <section className="workspace-section"><div className="section-heading"><div><h2>Artifacts</h2><p>Preview supported evidence or download the complete retained-artifacts folder as a ZIP.</p></div>{evidence.length > 0 && <a className="button button--secondary" href={artifactArchiveDownloadUrl(apiUrl, item.id)}>Download all (.zip)</a>}</div>{evidence.length ? <ul className="artifact-list">{evidence.map((file) => <li key={file.id}><div><strong>{file.kind}</strong><br /><small>{file.size.toLocaleString()} bytes · {file.content_type ?? "binary artifact"}</small></div><div className="button-row"><button className="button button--secondary" type="button" onClick={() => void openPreview(file)}>Preview</button><a className="button button--secondary" href={artifactDownloadUrl(apiUrl, item.id, file.id)}>Download</a></div></li>)}</ul> : <p>No artifacts were retained for this run.</p>}{preview && <div className="artifact-preview" aria-live="polite"><div className="section-heading"><h3>Preview: {preview.kind}</h3><button className="button button--secondary" type="button" onClick={() => { if (previewUrl) URL.revokeObjectURL(previewUrl); setPreview(null); setPreviewContent(null); setPreviewUrl(null); setArchiveEntries(null); }}>Close</button></div>{archiveEntries && <><p>This ZIP contains {archiveEntries.length.toLocaleString()} entries. Files are listed without extracting the archive.</p><ul className="archive-entry-list">{archiveEntries.map((entry) => <li key={entry.path}><code>{entry.is_directory ? `${entry.path}/` : entry.path}</code>{!entry.is_directory && <small>{entry.size.toLocaleString()} bytes</small>}</li>)}</ul></>}{previewType(preview) === "image" && previewUrl && <img src={previewUrl} alt={`Artifact preview: ${preview.kind}`} />}{previewType(preview) === "video" && previewUrl && <video controls src={previewUrl}>Your browser cannot preview this video.</video>}{previewType(preview) === "text" && <pre className="code-block">{previewContent ?? "Loading preview..."}</pre>}{previewType(preview) === "binary" && !archiveEntries && <p>This {preview.content_type ?? "binary"} artifact cannot be previewed in the browser. Download it to inspect it with the appropriate tool.</p>}</div>}</section>
    {notice && <p className="notice notice--error">{notice}</p>}
  </>;
}
