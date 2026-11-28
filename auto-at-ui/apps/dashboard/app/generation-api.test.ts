import assert from "node:assert/strict";
import test from "node:test";
import { getVisualTrace, getOperationFrameBlob } from "./generation-api.ts";
import { getVisionProviders } from "./generation-api.ts";

test("provider catalogue and confirmation preserve API shape and structured errors", async () => {
  const original = globalThis.fetch;
  const requests: Request[] = [];
  globalThis.fetch = async (input, init) => {
    const request = new Request(input, init); requests.push(request);
    return request.method === "POST" ? new Response(JSON.stringify({ detail: { code: "vision_policy_changed", ignored: "private diagnostic" } }), { status: 409 }) : new Response('{"items":[]}');
  };
  try {
    assert.deepEqual(await getVisionProviders("http://fixture"), { items: [] });
    const payload = { project_id: "p", target_url: "https://fixture.test", task_intent: "Explore", use_vision: true as const, expected_provider: "gemini", expected_model: "gemini-3.8-flash" };
    await assert.rejects(submitVisualExploration("http://fixture", payload), (error: unknown) => error instanceof ControlPlaneError && error.status === 409 && error.code === "vision_policy_changed" && !error.message.includes("private"));
    assert.match(requests[0].url, /vision\/providers$/);
    assert.deepEqual(await requests[1].json(), payload);
    assert.equal(requests[1].credentials, "include");
    assert.equal(requests[1].headers.has("X-CSRF-Token"), true);
  } finally { globalThis.fetch = original; }
});
import { ControlPlaneError, createAgentTaskDraft, decideDraft, getAgentTaskConsistency, getAgentTaskDraftInputs, decideProposal, deleteVisualReplayFrame, getPolicy, getVisionPolicy, getVisualReplayFrameBlob, getVisualTrajectory, listDrafts, listProposals, listVisualActions, listVisualReplayFrames, setPolicy, setVisionPolicy, submitGeneration, submitVisualExploration } from "./generation-api.ts";

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

const sampleValue = "Zx9!hunter2-sample";
const sessionId = "00000000-0000-4000-8000-000000000001";
const created = { request_id: "r", draft_id: "d", correlation_id: "c", state: "pending_review", title: "Agent task test", source_hash: "h", contains_test_values: true, owned_test_target: true, created: true };

test("the consistency report is read with no cache from the session's own route", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined;
  globalThis.fetch = async (input, init) => { received = new Request(input, init); return new Response(JSON.stringify({ eligible: true, reasons: [] })); };
  try {
    const abort = new AbortController();
    assert.deepEqual(await getAgentTaskConsistency("http://control-plane", sessionId, abort.signal), { eligible: true, reasons: [] });
    assert.equal(received?.method, "GET");
    assert.equal(received?.url, `http://control-plane/api/v1/vision/explorations/${sessionId}/consistency`);
    assert.equal(received?.cache, "no-store");
    assert.equal(received?.credentials, "include");
    assert.equal(received?.headers.has("X-CSRF-Token"), false);
  } finally { globalThis.fetch = originalFetch; }
});

test("the expected lengths are read with no cache from the draft inputs route, as a plain GET with nothing sent", async () => {
  const originalFetch = globalThis.fetch;
  let received: Request | undefined; let body = "";
  const answer = { owned_test_target: true, has_type_steps: true, type_steps: [{ step_index: 1, locator_name: "Mật khẩu", text_chars: 24 }, { step_index: 1, locator_name: "Tên", text_chars: 8 }] };
  globalThis.fetch = async (input, init) => { received = new Request(input, init); body = await received.clone().text(); return new Response(JSON.stringify(answer)); };
  try {
    const abort = new AbortController();
    assert.deepEqual(await getAgentTaskDraftInputs("http://control-plane", sessionId, abort.signal), answer);
    assert.equal(received?.method, "GET");
    assert.equal(received?.url, `http://control-plane/api/v1/vision/explorations/${sessionId}/test-draft/inputs`);
    assert.equal(received?.cache, "no-store");
    assert.equal(received?.credentials, "include");
    assert.equal(received?.headers.has("Idempotency-Key"), false);
    assert.equal(body, "");
  } finally { globalThis.fetch = originalFetch; }
});

test("a refused or failed draft inputs request keeps its code and does not become an answer", async () => {
  const originalFetch = globalThis.fetch;
  const cases: [number, unknown, string | undefined][] = [
    [404, { detail: "Visual exploration not found." }, undefined],
    [409, { detail: { code: "session_not_completed" } }, "session_not_completed"],
    [409, { detail: { code: "evidence_expired", step_index: 2, operation_id: "op-2" } }, "evidence_expired"],
  ];
  try {
    for (const [status, answer, code] of cases) {
      globalThis.fetch = async () => new Response(JSON.stringify(answer), { status });
      await assert.rejects(getAgentTaskDraftInputs("http://control-plane", sessionId), (error: unknown) => {
        assert.ok(error instanceof ControlPlaneError);
        assert.equal(error.status, status);
        assert.equal(error.code, code);
        assert.equal(error.message.includes("op-2"), false);
        return true;
      });
    }
  } finally { globalThis.fetch = originalFetch; }
});

test("a draft request carries the typed values only in its body and never in the address, a header, storage or the console", async () => {
  const originalFetch = globalThis.fetch;
  const touched: string[] = [];
  const consoleMethods = ["log", "info", "warn", "error", "debug"] as const;
  const originals = consoleMethods.map((name) => console[name]);
  const storage = new Proxy({}, { get: (_, key) => () => { touched.push(`storage.${String(key)}`); }, set: () => { touched.push("storage set"); return true; } });
  const previous = { local: Object.getOwnPropertyDescriptor(globalThis, "localStorage"), session: Object.getOwnPropertyDescriptor(globalThis, "sessionStorage") };
  Object.defineProperty(globalThis, "localStorage", { value: storage, configurable: true });
  Object.defineProperty(globalThis, "sessionStorage", { value: storage, configurable: true });
  for (const name of consoleMethods) console[name] = () => { touched.push(`console.${name}`); };
  let received: Request | undefined; let body = "";
  globalThis.fetch = async (input, init) => { received = new Request(input, init); body = await received.clone().text(); return new Response(JSON.stringify(created), { status: 201 }); };
  try {
    const result = await createAgentTaskDraft("http://control-plane", sessionId, [sampleValue, "second"]);
    assert.deepEqual(result, created);
    assert.equal(received?.method, "POST");
    assert.equal(received?.url, `http://control-plane/api/v1/vision/explorations/${sessionId}/test-draft`);
    assert.deepEqual(JSON.parse(body), { values: [sampleValue, "second"] });
    assert.equal(received?.headers.get("Idempotency-Key")?.length, 36);
    assert.equal(received?.headers.has("X-CSRF-Token"), true);
    assert.equal(received?.credentials, "include");
    assert.equal(received?.cache, "no-store");
    assert.equal(received?.url.includes(sampleValue) || received?.url.includes(encodeURIComponent(sampleValue)), false);
    assert.equal([...received!.headers.values()].some((header) => header.includes(sampleValue)), false);
    assert.equal(JSON.stringify(result).includes(sampleValue), false, "the answer holds no value");
  } finally {
    consoleMethods.forEach((name, index) => { console[name] = originals[index] as never; });
    for (const [name, descriptor] of [["localStorage", previous.local], ["sessionStorage", previous.session]] as const) { if (descriptor) Object.defineProperty(globalThis, name, descriptor); else delete (globalThis as Record<string, unknown>)[name]; }
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(touched, []);
});

test("a session without type steps is sent as an empty list", async () => {
  const originalFetch = globalThis.fetch;
  let body = "";
  globalThis.fetch = async (input, init) => { body = await new Request(input, init).text(); return new Response(JSON.stringify({ ...created, created: false, contains_test_values: false }), { status: 200 }); };
  try {
    assert.equal((await createAgentTaskDraft("http://control-plane", sessionId, [])).created, false);
    assert.deepEqual(JSON.parse(body), { values: [] });
  } finally { globalThis.fetch = originalFetch; }
});

test("every refusal of the draft route keeps its code and nothing else of the answer", async () => {
  const originalFetch = globalThis.fetch;
  const cases: [number, unknown, string | undefined][] = [
    [409, { detail: { code: "assessment_inconsistent", consistency: { eligible: false, status_counts: { achieved: 1 } } } }, "assessment_inconsistent"],
    [422, { detail: { code: "input_value_mismatch", step_index: 2, operation_id: "op-2" } }, "input_value_mismatch"],
    [409, { detail: { code: "input_value_not_allowed" } }, "input_value_not_allowed"],
    [409, { detail: "credentials_in_source" }, undefined],
    [422, { detail: { code: "request_invalid" } }, "request_invalid"],
    [404, { detail: "Visual exploration not found." }, undefined],
  ];
  try {
    for (const [status, answer, code] of cases) {
      globalThis.fetch = async () => new Response(JSON.stringify(answer), { status });
      await assert.rejects(createAgentTaskDraft("http://control-plane", sessionId, [sampleValue]), (error: unknown) => {
        assert.ok(error instanceof ControlPlaneError);
        assert.equal(error.status, status);
        assert.equal(error.code, code);
        assert.equal(JSON.stringify([error.message, error.code]).includes(sampleValue), false);
        assert.equal(error.message.includes("consistency") || error.message.includes("op-2"), false);
        return true;
      });
    }
    globalThis.fetch = async () => { throw new TypeError("offline"); };
    await assert.rejects(createAgentTaskDraft("http://control-plane", sessionId, [sampleValue]), (error: unknown) => error instanceof TypeError && !String(error.message).includes(sampleValue));
  } finally { globalThis.fetch = originalFetch; }
});

test("a decision sends the disposable-account confirmation only when it was given", async () => {
  const originalFetch = globalThis.fetch;
  const bodies: unknown[] = [];
  globalThis.fetch = async (input, init) => { bodies.push(await new Request(input, init).json()); return new Response(JSON.stringify({ id: "d" })); };
  try {
    await decideDraft("http://control-plane", "draft", true, "looks right");
    await decideDraft("http://control-plane", "draft", true, "", true);
    await decideDraft("http://control-plane", "draft", false, "no", false);
    assert.deepEqual(bodies, [
      { approved: true, reason: "looks right" },
      { approved: true, reason: null, acknowledge_disposable_credentials: true },
      { approved: false, reason: "no" },
    ]);
  } finally { globalThis.fetch = originalFetch; }
});

test("review refusals arrive as a plain code or a generic 404 and are not rewritten by the client", async () => {
  const originalFetch = globalThis.fetch;
  try {
    for (const [status, detail] of [[409, "reviewer_must_differ_from_requester"], [409, "disposable_credentials_ack_required"], [404, "Generated draft not found."]] as const) {
      globalThis.fetch = async () => new Response(JSON.stringify({ detail }), { status });
      await assert.rejects(decideDraft("http://control-plane", "draft", true, "", false), (error: unknown) => error instanceof ControlPlaneError && error.status === status && error.message === detail);
    }
  } finally { globalThis.fetch = originalFetch; }
});
