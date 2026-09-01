import assert from "node:assert/strict";
import test from "node:test";
import { ControlPlaneError, decideProposal, getPolicy, getVisionPolicy, listDrafts, listProposals, listVisualActions, setVisionPolicy, submitGeneration, submitVisualExploration } from "./generation-api.ts";

test("generation submission sends session credentials and an idempotency key", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => {
    received = new Request(input, init);
    return new Response(JSON.stringify({ id: "id" }), { status: 202 });
  };
  try {
    await submitGeneration("http://control-plane", { project_id: "project", target_url: "https://example.com", request: "Check heading" });
    assert.equal(received?.headers.get("X-Tenant-Id"), null);
    assert.equal(received?.headers.get("Idempotency-Key")?.length, 36);
    assert.equal(await received?.text(), JSON.stringify({ project_id: "project", target_url: "https://example.com", request: "Check heading" }));
  } finally { globalThis.fetch = originalFetch; }
});

test("control-plane errors retain only the safe API detail", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Project not found." }), { status: 404 });
  try {
    await assert.rejects(() => submitGeneration("http://control-plane", { project_id: "project", target_url: "https://example.com", request: "Check heading" }), (error: unknown) => error instanceof ControlPlaneError && error.message === "Project not found.");
  } finally { globalThis.fetch = originalFetch; }
});

test("review collection and decision requests use the control-plane routes", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Request[] = [];
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init); requests.push(request);
    return new Response(JSON.stringify(request.url.includes("decision") ? { proposal_id: "proposal", proposal_version: 1, approved: true, decided_by: "person", reason: null } : { items: [], total: 0, limit: 25, offset: 0 }));
  };
  try {
    await listDrafts("http://control-plane", "pending_review");
    await listProposals("http://control-plane", false, "run-id");
    await decideProposal("http://control-plane", "proposal", true, "evidence reviewed");
    assert.match(requests[0].url, /test-generations\/drafts\?state=pending_review/);
    assert.match(requests[1].url, /proposals\?decided=false&run_id=run-id/);
    assert.equal(requests[2].method, "POST");
    assert.equal(await requests[2].text(), JSON.stringify({ approved: true, reason: "evidence reviewed" }));
  } finally { globalThis.fetch = originalFetch; }
});

test("project policy can be loaded after it has been saved", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => {
    received = new Request(input, init);
    return new Response(JSON.stringify({ allowed_origins: ["https://example.test"] }));
  };
  try {
    await getPolicy("http://control-plane", "project-id");
    assert.equal(received?.method, "GET");
    assert.match(received?.url ?? "", /projects\/project-id\/policy$/);
  } finally { globalThis.fetch = originalFetch; }
});

test("vision calls use the dedicated server-side policy and exploration routes", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Request[] = [];
  const policy = { enabled: true, provider: "huggingface", model: "Qwen/Qwen2.5-VL-7B-Instruct", raw_screenshot_transfer_accepted: true, max_steps: 3, max_screenshot_bytes: 1000, max_session_seconds: 30, max_cost_usd: 0.01, max_requests_per_minute: 1 };
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init); requests.push(request);
    return new Response(JSON.stringify(request.url.includes("actions") ? [] : policy));
  };
  try {
    await getVisionPolicy("http://control-plane");
    await setVisionPolicy("http://control-plane", policy);
    await submitVisualExploration("http://control-plane", { project_id: "project", target_url: "https://example.com", task_intent: "Open the menu", use_vision: true });
    await listVisualActions("http://control-plane", "session");
    assert.match(requests[0].url, /\/vision\/policy$/);
    assert.equal(requests[1].method, "PUT");
    assert.equal(await requests[1].text(), JSON.stringify(policy));
    assert.match(requests[2].url, /\/vision\/explorations$/);
    assert.equal(requests[2].headers.get("Idempotency-Key")?.length, 36);
    assert.equal(await requests[2].text(), JSON.stringify({ project_id: "project", target_url: "https://example.com", task_intent: "Open the menu", use_vision: true }));
    assert.match(requests[3].url, /\/vision\/explorations\/session\/actions$/);
  } finally { globalThis.fetch = originalFetch; }
});
