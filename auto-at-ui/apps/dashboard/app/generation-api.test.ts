import assert from "node:assert/strict";
import test from "node:test";
import { getVisualTrace, getOperationFrameBlob } from "./generation-api.ts";
import { ControlPlaneError, decideProposal, deleteVisualReplayFrame, getPolicy, getVisionPolicy, getVisualReplayFrameBlob, getVisualTrajectory, listDrafts, listProposals, listVisualActions, listVisualReplayFrames, setPolicy, setVisionPolicy, submitGeneration, submitVisualExploration } from "./generation-api.ts";

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
    return new Response(JSON.stringify({ allowed_origins: ["https://example.test"], vision_max_hops: 5, vision_max_states: 50 }));
  };
  try {
    await getPolicy("http://control-plane", "project-id");
    assert.equal(received?.method, "GET");
    assert.match(received?.url ?? "", /projects\/project-id\/policy$/);
  } finally { globalThis.fetch = originalFetch; }
});

test("project policy keeps configured Vision tree bounds", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => { received = new Request(input, init); return new Response("{}"); };
  try {
    await setPolicy("http://control-plane", "project-id", { allowed_origins: ["https://example.test"], vision_max_hops: 5, vision_max_states: 50 });
    assert.equal(await received?.text(), JSON.stringify({ allowed_origins: ["https://example.test"], vision_max_hops: 5, vision_max_states: 50 }));
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
    await getVisualTrajectory("http://control-plane", "session");
    assert.match(requests[0].url, /\/vision\/policy$/);
    assert.equal(requests[1].method, "PUT");
    assert.equal(await requests[1].text(), JSON.stringify(policy));
    assert.match(requests[2].url, /\/vision\/explorations$/);
    assert.equal(requests[2].headers.get("Idempotency-Key")?.length, 36);
    assert.equal(await requests[2].text(), JSON.stringify({ project_id: "project", target_url: "https://example.com", task_intent: "Open the menu", use_vision: true }));
    assert.match(requests[3].url, /\/vision\/explorations\/session\/actions$/);
    assert.match(requests[4].url, /\/vision\/explorations\/session\/trajectory$/);
  } finally { globalThis.fetch = originalFetch; }
});

test("replay evidence stays on session-scoped cookie and CSRF-protected routes", async () => {
  const originalFetch = globalThis.fetch;
  const requests: Request[] = [];
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init); requests.push(request);
    if (request.headers.get("Accept") === "image/png") return new Response(new Uint8Array([137, 80, 78, 71]));
    if (request.method === "DELETE") return new Response(null, { status: 204 });
    return new Response(JSON.stringify({ items: [] }));
  };
  try {
    await listVisualReplayFrames("http://control-plane", "session");
    await getVisualReplayFrameBlob("http://control-plane", "session", "frame");
    await deleteVisualReplayFrame("http://control-plane", "session", "frame");
    assert.match(requests[0].url, /vision\/explorations\/session\/replay-frames$/);
    assert.match(requests[1].url, /vision\/explorations\/session\/replay-frames\/frame$/);
    assert.equal(requests[1].headers.get("Accept"), "image/png");
    assert.equal(requests[2].method, "DELETE");
    assert.equal(await requests[2].text(), JSON.stringify({ confirm: true }));
  } finally { globalThis.fetch = originalFetch; }
});

test("trace pagination restarts on a changed revision without mixing snapshots", async () => {
  const originalFetch = globalThis.fetch;
  const calls: string[] = [];
  globalThis.fetch = async (input) => {
    calls.push(String(input));
    if (calls.length === 2) return new Response(JSON.stringify({ detail: "Trace changed" }), { status: 409 });
    const last = calls.length === 4;
    return new Response(JSON.stringify({ session_id: "session", revision: calls.length === 1 ? "old" : "new", items: [{ id: calls.length }], locators: [], next_sequence: last ? 2 : 1, has_more: !last }));
  };
  try {
    const result = await getVisualTrace("http://fixture", "session");
    assert.deepEqual(result.items.map((item) => item.id), [3, 4]);
    assert.match(calls[1], /revision=old/); assert.doesNotMatch(calls[2], /revision=/);
    assert.match(calls[3], /revision=new/);
  } finally { globalThis.fetch = originalFetch; }
});

test("operation image requests can be aborted and use private session credentials", async () => {
  const originalFetch = globalThis.fetch; const abort = new AbortController();
  globalThis.fetch = async (_input, init) => {
    assert.equal(init?.signal, abort.signal); assert.equal(init?.credentials, "include");
    assert.equal(init?.cache, "no-store"); return new Response(new Uint8Array([137, 80, 78, 71]));
  };
  try { assert.equal((await getOperationFrameBlob("http://fixture", "session", "frame", abort.signal)).size, 4); }
  finally { globalThis.fetch = originalFetch; }
});
