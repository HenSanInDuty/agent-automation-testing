import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { shouldPollGeneration } from "./generation-polling.ts";
import { agentTaskProvenance, canApproveAgentDraft, decisionFailureMessage, decisionNotFoundMessage } from "./components/agent-task-draft-model.ts";

test("only non-terminal generation states are polled", () => {
  assert.equal(shouldPollGeneration("queued"), true);
  assert.equal(shouldPollGeneration("generating"), true);
  assert.equal(shouldPollGeneration("completed"), false);
  assert.equal(shouldPollGeneration("failed"), false);
});

const agentDraftProvenance = (contains: boolean) => ({ agent_trace_source: { session_id: "s", trace_hash: "h" }, contains_test_values: contains, owned_test_target: contains, requested_by: "alice" });

test("the review screen asks for the disposable-account confirmation only for a draft that carries test values", () => {
  const carrying = agentTaskProvenance(agentDraftProvenance(true));
  const plain = agentTaskProvenance(agentDraftProvenance(false));
  const other: ReturnType<typeof agentTaskProvenance> = agentTaskProvenance({ provider: "codex_cli", vision_source: { session_id: "s" } });
  assert.equal(carrying?.contains_test_values, true);
  assert.equal(canApproveAgentDraft(carrying?.contains_test_values === true, false), false, "approve stays disabled until the box is ticked");
  assert.equal(canApproveAgentDraft(carrying?.contains_test_values === true, true), true);
  assert.equal(canApproveAgentDraft(plain?.contains_test_values === true, false), true);
  assert.equal(canApproveAgentDraft(other?.contains_test_values === true, false), true);
  assert.equal(other, null, "a draft from the planner keeps the screen it always had");
});

test("the review screen words the refusals the decision route gives", () => {
  assert.match(decisionFailureMessage("reviewer_must_differ_from_requester") ?? "", /someone else must review/);
  assert.match(decisionFailureMessage("disposable_credentials_ack_required") ?? "", /disposable test accounts/);
  assert.match(decisionNotFoundMessage, /not found, or you do not have permission/);
  assert.equal(decisionFailureMessage("Generated draft is already decided."), undefined);
});

test("the draft form keeps typed values out of storage, the address and the console, and out of the browser's memory", () => {
  const panel = readFileSync(new URL("./components/agent-task-draft-panel.tsx", import.meta.url), "utf8");
  const model = readFileSync(new URL("./components/agent-task-draft-model.ts", import.meta.url), "utf8");
  for (const [name, text] of [["panel", panel], ["model", model]] as const) {
    assert.doesNotMatch(text, /localStorage|sessionStorage|indexedDB|document\.cookie|console\.|window\.history|history\.(push|replace)State|location\.|useSearchParams|URLSearchParams|router\.(push|replace)/, `${name} must not write the values anywhere`);
  }
  const input = /<Input [\s\S]*?\/>/.exec(panel)?.[0] ?? "";
  assert.match(input, /type="text"/);
  assert.match(input, /autoComplete="off"/);
  assert.match(input, /spellCheck=\{false\}/);
  assert.doesNotMatch(input, /\sname=/, "a named field is what browsers offer to remember");
  assert.match(panel, /<form [^\n]*autoComplete="off"/);
  assert.match(panel, /setValues\(clearInputs\(values\)\)/, "the typed values are cleared as the request is sent");
});

test("the draft panel adds no way to run a test: the only action it takes is creating a draft", () => {
  const panel = readFileSync(new URL("./components/agent-task-draft-panel.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(panel, /decideDraft|decideProposal|createRun|\/runs|dispatch|Run test|Run now/i);
  const buttons = [...panel.matchAll(/<Button[^>]*>([^<{]*(?:\{[^}]*\}[^<]*)?)<\/Button>/g)].map((match) => match[1]);
  assert.ok(buttons.length >= 2);
  for (const label of buttons) assert.doesNotMatch(label, /run|execute|approve/i, label);
});
