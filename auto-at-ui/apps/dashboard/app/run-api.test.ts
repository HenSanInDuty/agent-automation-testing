import assert from "node:assert/strict";
import test from "node:test";
import { createProject, runReport } from "./run-api.ts";

test("project creation sends only the user-facing name and target", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => {
    received = new Request(input, init);
    return new Response(JSON.stringify({ id: "generated-uuid", name: "Project-01", default_target: "web_ui" }), { status: 201 });
  };
  try {
    await createProject("http://control-plane", { name: "Project-01", default_target: "web_ui" });
    assert.equal(received?.method, "POST");
    assert.match(received?.url ?? "", /\/api\/v1\/projects$/);
    assert.equal(await received?.text(), JSON.stringify({ name: "Project-01", default_target: "web_ui" }));
  } finally { globalThis.fetch = originalFetch; }
});

test("run reporting is read through the dedicated immutable report route", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => {
    received = new Request(input, init);
    return new Response(JSON.stringify({ status: "unavailable" }));
  };
  try {
    await runReport("http://control-plane", "run-id");
    assert.equal(received?.method, "GET");
    assert.match(received?.url ?? "", /\/api\/v1\/runs\/run-id\/report$/);
  } finally { globalThis.fetch = originalFetch; }
});
