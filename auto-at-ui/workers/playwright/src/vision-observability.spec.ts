import { expect, test, type Page } from "@playwright/test";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { randomUUID } from "node:crypto";
import { visualHttpHandler } from "./vision-http.js";
import { VisualOperationWorker } from "./vision-operations.js";
import { captureVisionScreen } from "./vision-screen.js";
import { logVisionEvent, visionLogScope } from "./vision-observability.js";
import { inspectState, logStateMismatch, setInteractionScope } from "./vision-checkpoints.js";
import { observeDom } from "./vision-dom.js";

test("HTTP rejections carry Loki envelope, scope and trace without request data", async () => {
  const lines: string[] = [];
  const original = console.warn;
  console.warn = (line: string) => lines.push(line);
  const handler = visualHttpHandler("unused", () => "private-worker-secret");
  const server = createServer((req, res) => { void handler(req, res); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${(server.address() as AddressInfo).port}/visual-explorations`;
  const session = randomUUID(), correlation = randomUUID();
  const headers = { "x-auto-at-vision-worker-secret": "private-worker-secret",
    "x-auto-at-vision-tenant-id": "fixture", "x-auto-at-vision-project-id": randomUUID(),
    "x-auto-at-vision-fencing-token": "1", "x-correlation-id": correlation,
    traceparent: `00-${"a".repeat(32)}-${"b".repeat(16)}-01` };
  try {
    const response = await fetch(`${url}/${session}/screen`, { headers });
    expect(response.status).toBe(422);
    expect(await response.json()).toEqual({ detail: "session_unavailable" });
    expect(JSON.parse(lines[0])).toMatchObject({ service: "auto-at-playwright-worker", environment: "local",
      level: "warn", event: "vision.request_rejected", session_id: session, correlation_id: correlation,
      trace_id: "a".repeat(32), span_id: "b".repeat(16), stage: "live_screen", status_code: 422,
      code: "session_unavailable", error_type: "contract_rejection", duration_ms: expect.any(Number) });
    const checkpoint = randomUUID();
    expect((await fetch(`${url}/${session}/checkpoints/${checkpoint}`, { headers })).status).toBe(422);
    expect(JSON.parse(lines.at(-1)!)).toMatchObject({stage:'checkpoint_read', checkpoint_id:checkpoint, session_id:session});
    expect(JSON.parse(lines.at(-1)!)).not.toHaveProperty('operation_id');
    const invalid = await fetch(url, { method: "POST", headers, body: 'private-page-content not json' });
    expect(invalid.status).toBe(422);
    expect(JSON.parse(lines.at(-1)!)).toMatchObject({ stage: "request_validation", error_type: "invalid_json" });
    expect((await fetch(`${url}/private-url?token=private-token/screen`, {
      headers: { ...headers, "x-correlation-id": "private-correlation", traceparent: "private-trace" },
    })).status).toBe(422);
    expect((await fetch(`${url}/${session}/screen`)).status).toBe(401);
    expect(JSON.parse(lines.at(-1)!)).toMatchObject({ stage: "authentication", code: "authentication_failed",
      error_type: "authentication_error", status_code: 401 });
    expect(lines.join("\n")).not.toMatch(/private-/);
  } finally {
    console.warn = original;
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

for (const kind of ["closed", "timeout", "protocol"] as const) {
  test(`capture ${kind} logs safe diagnostics and preserves failure`, async () => {
    const lines: string[] = [];
    const original = console.warn;
    console.warn = (line: string) => lines.push(line);
    const originalError = new Error(kind === "closed"
      ? "Target page, context or browser has been closed private-page-content"
      : "Protocol error (Page.captureScreenshot): private-page-content");
    const client = { send: async () => {
      if (kind === "timeout") return new Promise(() => undefined);
      throw originalError;
    }, detach: async () => undefined };
    const page = { isClosed: () => kind === "closed", context: () => ({
      newCDPSession: async () => client, browser: () => ({ isConnected: () => kind !== "closed" }),
    }) } as unknown as Page;
    const session = randomUUID();
    try {
      const capture = visionLogScope.run({ context: { correlation_id: randomUUID() },
        fields: { session_id: session, stage: "live_screen" } }, () => captureVisionScreen(page, 10));
      if (kind === "timeout") await expect(capture).rejects.toThrow("capture_failed");
      else await expect(capture).rejects.toBe(originalError);
      expect(JSON.parse(lines[0])).toMatchObject({ event: "vision.capture.failed", service: "auto-at-playwright-worker",
        level: "warn", session_id: session, stage: "live_screen", capture_stage: "screenshot", timeout_ms: 10,
        page_closed: kind === "closed", browser_connected: kind !== "closed",
        error_type: kind === "closed" ? "target_closed" : kind === "protocol" ? "browser_protocol_error" : "timeout" });
      expect(lines.join("\n")).not.toContain("private-page-content");
    } finally { console.warn = original; }
  });
}

test("concurrent requests retain separate capture scopes and logging failure is harmless", async () => {
  const lines: string[] = [];
  const original = console.warn;
  console.warn = (line: string) => lines.push(line);
  try {
    await Promise.all(["first", "second"].map((session) => visionLogScope.run({ context: {}, fields: { session_id: session } }, async () => {
      await new Promise((resolve) => setTimeout(resolve, session === "first" ? 5 : 1));
      expect(visionLogScope.getStore()?.fields.session_id).toBe(session);
    })));
    console.warn = () => { throw new Error("logging offline"); };
    expect(() => logVisionEvent("warn", "vision.request_rejected", "Rejected.")).not.toThrow();
  } finally { console.warn = original; }
});

test("coverage diagnostics explain unnamed, ambiguous and private controls without labels", async ({ page }) => {
  await page.setContent('<button style="width:50px;height:30px"></button><button>Duplicate</button><button>Duplicate</button>' +
    '<button disabled>Disabled</button><button aria-label="secret private-value">Private</button><button>Good</button>');
  setInteractionScope(page, "buttons");
  const lines: string[] = [], original = console.warn;
  console.warn = (line: string) => lines.push(line);
  const session = randomUUID(), correlation = randomUUID();
  try {
    const observed = await visionLogScope.run({ context: { correlation_id: correlation }, fields: {} }, () => observeDom(page, {
      contract_version: "v4", capability: "dom-observation-v1", tenant_id: "fixture", project_id: randomUUID(), session_id: session, fencing_token: 1,
      snapshot_id: randomUUID(), expected_state_fingerprint: "", max_elements: 100, max_bytes: 65536,
      revalidate_snapshot_id: null, revalidate_element_ids: [], revalidate_context_only: false,
    }).catch(() => null));
    expect(observed).toBeNull(); // Rejected stale observations must not emit misleading coverage.
    expect(lines).toHaveLength(0);
    const fingerprint = (await inspectState(page)).fingerprint;
    const result = await visionLogScope.run({ context: { correlation_id: correlation }, fields: {} }, () => observeDom(page, {
      contract_version: "v4", capability: "dom-observation-v1", tenant_id: "fixture", project_id: randomUUID(), session_id: session, fencing_token: 1,
      snapshot_id: randomUUID(), expected_state_fingerprint: fingerprint, max_elements: 100, max_bytes: 65536,
      revalidate_snapshot_id: null, revalidate_element_ids: [], revalidate_context_only: false,
    }));
    expect(result.data.observation.elements.map(e => e.name)).toEqual(["", "Good"]);
    expect(JSON.parse(lines[0])).toMatchObject({ event: "vision.dom.coverage_limited", session_id: session,
      correlation_id: correlation, interaction_scope: "buttons", observed_count: 2, skipped_count: 4,
      skip_reasons: { multiple_matches: 2, disabled: 1, sensitive_identity: 1 } });
    expect(lines.join("\n")).not.toMatch(/private-value|Duplicate|Disabled|Good/);
  } finally { console.warn = original; }
});

test("state mismatch logs changed components without form values or fingerprints", async ({ page }) => {
  await page.setContent('<button style="position:absolute;left:10px">Action</button><input type="hidden" value="private-before">');
  const before = await inspectState(page);
  await page.evaluate(() => {
    document.querySelector('button')!.style.left = '100px';
    document.querySelector('input')!.value = 'private-after';
  });
  const after = await inspectState(page);
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    logStateMismatch(before, after, "prepare_end");
    expect(JSON.parse(lines[0])).toMatchObject({ event: "vision.state.mismatch", failure_stage: "prepare_end",
      url_changed: false, interaction_changed: true, form_values_changed: true, form_presence_changed: false, scroll_changed: false });
    expect(lines[0]).not.toContain("private-");
    expect(lines[0]).not.toContain(before.fingerprint);
  } finally { console.error = original; }
});

test("HTTP 200 operation failure is an explicit error event; ACK only reads the recorded result", async () => {
  const lines: string[] = [];
  const originalError = console.error, originalLog = console.log;
  const originalPrepare = VisualOperationWorker.prototype.prepare, originalAck = VisualOperationWorker.prototype.acknowledge;
  console.error = console.log = (line: string) => lines.push(line);
  const session = randomUUID(), operation = randomUUID();
  VisualOperationWorker.prototype.prepare = async () => ({ operation: {
    status: "failed", outcome_code: "settle_timeout", action_kind: "navigate", purpose: "setup", sequence: 1,
  } } as Awaited<ReturnType<VisualOperationWorker["prepare"]>>);
  VisualOperationWorker.prototype.acknowledge = VisualOperationWorker.prototype.prepare as typeof originalAck;
  const handler = visualHttpHandler("unused", () => "fixture");
  const server = createServer((req, res) => { void handler(req, res); });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  try {
    const response = await fetch(`http://127.0.0.1:${(server.address() as AddressInfo).port}/visual-explorations/${session}/operations/prepare`, {
      method: "POST", headers: { "x-auto-at-vision-worker-secret": "fixture" },
      body: JSON.stringify({ session_id: session, operation_id: operation, action: { text: "private-input" } }),
    });
    expect(response.status).toBe(200);
    expect(JSON.parse(lines[0])).toMatchObject({ level: "error", status_code: 200, stage: "operation_prepare",
      event: "vision.operation.failed", failure_stage: "page_settle", action_kind: "navigate", purpose: "setup",
      session_id: session, operation_id: operation, operation_status: "failed", outcome_code: "settle_timeout" });
    expect(JSON.parse(lines[0]).message).toContain("settle_timeout");
    expect(JSON.parse(lines[0]).message).not.toContain("request completed");
    const ack = await fetch(`http://127.0.0.1:${(server.address() as AddressInfo).port}/visual-explorations/${session}/operations/${operation}/ack`, {
      method: "POST", headers: { "x-auto-at-vision-worker-secret": "fixture" },
      body: JSON.stringify({ session_id: session, operation_id: operation }),
    });
    expect(ack.status).toBe(200);
    expect(JSON.parse(lines.at(-1)!)).toMatchObject({ level: "info", event: "vision.operation.result_read",
      operation_status: "failed", outcome_code: "settle_timeout" });
    expect(lines.join("\n")).not.toContain("private-input");
  } finally {
    VisualOperationWorker.prototype.prepare = originalPrepare;
    VisualOperationWorker.prototype.acknowledge = originalAck;
    console.error = originalError; console.log = originalLog;
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
