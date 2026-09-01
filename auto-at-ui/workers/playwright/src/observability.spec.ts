import { expect, test } from "@playwright/test";

import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { addRunnerObservabilityArtifacts } from "./execute.js";
import { logEvent, redact, RunnerEventSink, traceContext } from "./observability.js";

test("redacts sensitive fields and credential-shaped values", () => {
  expect(redact({ authorization: "Bearer private-token", url: "https://example.test/?token=private" })).toEqual({ authorization: "[REDACTED]", url: "https://example.test/?token=[REDACTED]" });
});

test("parses only valid W3C traceparent values", () => {
  expect(traceContext(`00-${"a".repeat(32)}-${"b".repeat(16)}-01`)).toEqual({ trace_id: "a".repeat(32), span_id: "b".repeat(16) });
  expect(traceContext("not-a-traceparent")).toEqual({});
});

test("emits a parseable common JSON envelope", () => {
  const emitted: string[] = [];
  const original = console.log;
  console.log = (line: string) => emitted.push(line);
  try {
    logEvent("info", "runner.request.accepted", "Accepted.", { run_id: "run-1", correlation_id: "correlation-1" });
  } finally {
    console.log = original;
  }
  expect(JSON.parse(emitted[0])).toMatchObject({ level: "info", event: "runner.request.accepted", run_id: "run-1", correlation_id: "correlation-1" });
});

test("caps redacted runner JSONL and creates a checksum-backed safe manifest", async () => {
  const sink = new RunnerEventSink({ run_id: "run-1", correlation_id: "correlation-1" }, 100);
  sink.record("runner.step.failed", "Bearer private-value?token=private-value");
  sink.record("runner.step.failed", "This record exceeds the remaining bounded runner-log budget.");
  const root = await mkdtemp(join(tmpdir(), "auto-at-runner-log-"));
  const artifacts: Array<{ kind: string; uri: string; content_type?: string }> = [];
  const evidence: Record<string, { checksum: string; size: number }> = {};
  try {
    await addRunnerObservabilityArtifacts(root, { run_id: "run-1", correlation_id: "correlation-1" } as never, artifacts, evidence, sink);
    const runnerLog = artifacts.find((artifact) => artifact.kind === "runner-log");
    const manifest = artifacts.find((artifact) => artifact.kind === "artifact-manifest");
    expect(runnerLog).toBeDefined();
    expect(manifest).toBeDefined();
    const log = await readFile(runnerLog!.uri.replace("file://", ""), "utf8");
    expect(log).not.toContain("private-value");
    expect(log.split("\n").filter(Boolean).every((line) => JSON.parse(line))).toBeTruthy();
    const parsedManifest = JSON.parse(await readFile(manifest!.uri.replace("file://", ""), "utf8"));
    expect(parsedManifest).toMatchObject({ schema_version: "v1", run_id: "run-1", correlation_id: "correlation-1" });
    expect(parsedManifest.artifacts[0]).toMatchObject({ name: "runner-log.jsonl", checksum: evidence[runnerLog!.uri].checksum });
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
