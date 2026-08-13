import assert from "node:assert/strict";
import test from "node:test";
import { ControlPlaneError, decideProposal, getPolicy, listDrafts, listProposals, submitGeneration } from "./generation-api.ts";

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
    await listProposals("http://control-plane", false);
    await decideProposal("http://control-plane", "proposal", true, "evidence reviewed");
    assert.match(requests[0].url, /test-generations\/drafts\?state=pending_review/);
    assert.match(requests[1].url, /proposals\?decided=false/);
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
