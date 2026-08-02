"use client";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { PageHeader } from "../components/page-header";
import { ControlPlaneError } from "../api-client";
import { createRun, projects, testCases, type Project, type TestCase } from "../run-api";

export default function ProjectsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000"; const router = useRouter();
  const [items, setItems] = useState<Project[]>([]); const [tests, setTests] = useState<TestCase[]>([]); const [projectId, setProjectId] = useState(""); const [testId, setTestId] = useState(""); const [url, setUrl] = useState(""); const [notice, setNotice] = useState("");
  useEffect(() => { projects(apiUrl).then((next) => { setItems(next); if (next[0]) setProjectId(next[0].id); }).catch((error) => setNotice(error instanceof ControlPlaneError ? error.message : "Unable to load projects.")); }, [apiUrl]);
  useEffect(() => { if (!projectId) return; testCases(apiUrl, projectId).then((next) => { setTests(next); setTestId(next[0]?.id ?? ""); }).catch((error) => setNotice(error.message)); }, [apiUrl, projectId]);
  const selected = tests.find((item) => item.id === testId);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!selected) return; try { const created = await createRun(apiUrl, { project_id: projectId, test_case_id: selected.id, target_type: selected.target_type, target_url: url || undefined, runner_config: {}, artifact_policy: { trace_on_failure: true, video_on_failure: true, screenshot_on_failure: true, retain_days: 30 } }); router.push(`/runs/${created.id}`); } catch (error) { setNotice(error instanceof ControlPlaneError ? error.message : "Unable to create run."); } }
  return <><PageHeader eyebrow="Catalog" title="Projects & Tests" description="Choose a project and immutable test revision, then start one deterministic run." />{notice && <p className="notice notice--error" role="alert">{notice}</p>}{!items.length ? <p className="panel">No projects are available to your account.</p> : <form className="workspace-section form-grid" onSubmit={submit}><label className="field">Project<select value={projectId} onChange={(e) => setProjectId(e.target.value)}>{items.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label className="field">Test case<select required value={testId} onChange={(e) => setTestId(e.target.value)}>{tests.map((item) => <option key={item.id} value={item.id}>{item.id}</option>)}</select></label><label className="field">Target URL <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.test" /></label><div className="field">Immutable revision <code>{selected?.revision ?? "Select a test case"}</code></div><p className="form-grid--one">Evidence: trace, video, and screenshot on failure; retained for 30 days.</p><div className="form-actions"><button className="button" disabled={!selected}>Create deterministic run</button></div></form>}</>;
}
