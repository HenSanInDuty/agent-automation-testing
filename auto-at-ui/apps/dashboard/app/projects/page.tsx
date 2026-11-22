"use client";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertCircle, FolderKanban, FlaskConical, Play, Plus } from "lucide-react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { PageHeader } from "../components/page-header";
import { Section } from "../components/section";
import { EmptyState } from "../components/states";
import { ControlPlaneError } from "../api-client";
import { createProject, createRun, projects, renameTestCase, testCases, type Project, type TestCase } from "../run-api";

const artifactPolicy = { trace_on_failure: true, video_on_failure: true, screenshot_on_failure: true, trace_on_success: true, video_on_success: true, screenshot_on_success: true, retain_days: 30 };

function errorMessage(error: unknown, fallback: string) {
  return error instanceof ControlPlaneError ? error.message : fallback;
}

export default function ProjectsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
  const router = useRouter();
  const [items, setItems] = useState<Project[]>([]);
  const [tests, setTests] = useState<TestCase[]>([]);
  const [projectId, setProjectId] = useState("");
  const [testId, setTestId] = useState("");
  const [url, setUrl] = useState("");
  const [projectName, setProjectName] = useState("");
  const [testName, setTestName] = useState("");
  const [notice, setNotice] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [starting, setStarting] = useState(false);
  const [renaming, setRenaming] = useState(false);

  useEffect(() => {
    projects(apiUrl)
      .then((next) => { setItems(next); if (next[0]) setProjectId(next[0].id); })
      .catch((error) => setNotice(errorMessage(error, "Unable to load projects.")))
      .finally(() => setLoaded(true));
  }, [apiUrl]);
  useEffect(() => {
    if (!projectId) return;
    testCases(apiUrl, projectId)
      .then((next) => { setTests(next); setTestId(next[0]?.id ?? ""); })
      .catch((error) => setNotice(error.message));
  }, [apiUrl, projectId]);
  const selected = tests.find((item) => item.id === testId);
  const project = items.find((item) => item.id === projectId);
  useEffect(() => { setTestName(selected?.name ?? ""); }, [selected]);

  async function addProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    setCreating(true);
    try {
      const created = await createProject(apiUrl, { name: projectName, default_target: "web_ui" });
      setItems((current) => [...current, created]);
      setProjectId(created.id);
      setProjectName("");
    } catch (error) {
      setNotice(errorMessage(error, "Unable to create project."));
    } finally {
      setCreating(false);
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    setStarting(true);
    try {
      const created = await createRun(apiUrl, {
        project_id: projectId,
        test_case_id: selected.id,
        target_type: selected.target_type,
        target_url: url || undefined,
        runner_config: {},
        artifact_policy: artifactPolicy,
      });
      router.push(`/runs/${created.id}`);
    } catch (error) {
      setNotice(errorMessage(error, "Unable to create run."));
      setStarting(false);
    }
  }

  async function renameSelected() {
    if (!selected || !testName.trim()) return;
    setRenaming(true);
    try {
      const renamed = await renameTestCase(apiUrl, projectId, selected.id, testName.trim());
      setTests((current) => current.map((item) => (item.id === renamed.id ? renamed : item)));
      setNotice("");
    } catch (error) {
      setNotice(errorMessage(error, "Unable to rename test case."));
    } finally {
      setRenaming(false);
    }
  }

  return <>
    <PageHeader eyebrow="Catalog" title="Projects & Tests" description="Create a project by name, then choose an immutable test revision and start one deterministic run." />
    {notice && <Alert variant="destructive" role="alert" className="mb-6">
      <AlertCircle />
      <AlertDescription>{notice}</AlertDescription>
    </Alert>}
    <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
      <Section title="1. Project" description="The control plane assigns the project UUID automatically." contentClassName="space-y-5">
        <form className="space-y-3" onSubmit={addProject}>
          <div className="space-y-2">
            <Label htmlFor="project-name">Project name</Label>
            <Input id="project-name" required value={projectName} onChange={(e) => setProjectName(e.target.value)} placeholder="Project-01" />
          </div>
          <Button type="submit" variant="secondary" className="w-full" disabled={creating}>
            {creating ? <Spinner /> : <Plus />}Create project
          </Button>
        </form>
        {loaded && !items.length
          ? <EmptyState title="No projects yet" icon={<FolderKanban />} className="py-8">No projects are available yet. Create one above.</EmptyState>
          : <ul className="space-y-1.5" aria-label="Projects">
            {items.map((item) => {
              const active = item.id === projectId;
              return <li key={item.id}>
                <button
                  type="button"
                  aria-pressed={active}
                  onClick={() => setProjectId(item.id)}
                  className={cn(
                    "flex w-full min-w-0 items-center justify-between gap-2 rounded-lg border px-3 py-2.5 text-left text-sm outline-none transition-colors focus-visible:ring-[3px] focus-visible:ring-ring/50",
                    active ? "border-primary/40 bg-accent text-accent-foreground" : "bg-transparent hover:bg-accent/50",
                  )}
                >
                  <span className="min-w-0 truncate font-medium">{item.name}</span>
                  <Badge variant="outline" className="shrink-0 font-mono text-[11px]">{item.default_target}</Badge>
                </button>
              </li>;
            })}
          </ul>}
      </Section>

      {items.length > 0 && <Section
        title="2. Run a test"
        description={project ? `Project: ${project.name}` : undefined}
      >
        <form className="space-y-6" onSubmit={submit}>
          {tests.length === 0
            ? <EmptyState title="No test cases" icon={<FlaskConical />} className="py-8">This project has no test cases yet.</EmptyState>
            : null}
          <div className="space-y-2 [&_[data-slot=native-select-wrapper]]:w-full">
            <Label htmlFor="test-case">Test case</Label>
            <NativeSelect id="test-case" required className="w-full" value={testId} onChange={(e) => setTestId(e.target.value)}>
              {tests.map((item) => <NativeSelectOption key={item.id} value={item.id}>{item.name}</NativeSelectOption>)}
            </NativeSelect>
          </div>

          <dl className="grid grid-cols-1 gap-3 rounded-lg border bg-muted/40 p-4 text-sm sm:grid-cols-2">
            <div className="min-w-0">
              <dt className="text-xs text-muted-foreground">Immutable revision</dt>
              <dd className="mt-1 truncate"><code className="font-mono text-xs">{selected?.revision ?? "Select a test case"}</code></dd>
            </div>
            <div className="min-w-0">
              <dt className="text-xs text-muted-foreground">Target type</dt>
              <dd className="mt-1 truncate">{selected?.target_type ?? "—"}</dd>
            </div>
          </dl>

          <div className="space-y-2">
            <Label htmlFor="test-name">Test case name</Label>
            <div className="flex flex-col gap-2 sm:flex-row">
              <Input id="test-name" value={testName} onChange={(e) => setTestName(e.target.value)} disabled={!selected} />
              <Button
                type="button"
                variant="outline"
                disabled={!selected || renaming || !testName.trim() || testName === selected.name}
                onClick={() => void renameSelected()}
              >
                {renaming && <Spinner />}Save test name
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">Only project and tenant administrators can save a new name. The technical ID and revision stay immutable.</p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="target-url">Target URL <span className="font-normal text-muted-foreground">(optional)</span></Label>
            <Input id="target-url" type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://example.test" />
          </div>

          <div className="flex flex-col gap-3 border-t pt-5 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm text-muted-foreground">Visual evidence: trace, video, and screenshot are retained for every run for 30 days.</p>
            <Button type="submit" disabled={!selected || starting} className="shrink-0">
              {starting ? <Spinner /> : <Play />}Create deterministic run
            </Button>
          </div>
        </form>
      </Section>}
    </div>
  </>;
}
