import assert from "node:assert/strict";
import test from "node:test";
import { ControlPlaneError, submitGeneration } from "./generation-api.ts";

test("generation submission sends identity and an idempotency key to the control plane", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => {
    received = new Request(input, init);
    return new Response(JSON.stringify({ id: "id" }), { status: 202 });
  };
  try {
    await submitGeneration("http://control-plane", { tenantId: "tenant", actorId: "actor", roles: "contributor" }, { project_id: "project", target_url: "https://example.com", request: "Check heading" });
    assert.equal(received?.headers.get("X-Tenant-Id"), "tenant");
    assert.equal(received?.headers.get("Idempotency-Key")?.length, 36);
    assert.equal(await received?.text(), JSON.stringify({ project_id: "project", target_url: "https://example.com", request: "Check heading" }));
  } finally { globalThis.fetch = originalFetch; }
});

test("control-plane errors retain only the safe API detail", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: "Project not found." }), { status: 404 });
  try {
    await assert.rejects(() => submitGeneration("http://control-plane", { tenantId: "tenant", actorId: "actor", roles: "viewer" }, { project_id: "project", target_url: "https://example.com", request: "Check heading" }), (error: unknown) => error instanceof ControlPlaneError && error.message === "Project not found.");
  } finally { globalThis.fetch = originalFetch; }
});
