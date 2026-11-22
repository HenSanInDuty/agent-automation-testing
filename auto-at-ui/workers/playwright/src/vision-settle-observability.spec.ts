import { expect, test, type Page } from "@playwright/test";
import { settleState } from "./vision-checkpoints.js";
import { visionLogScope } from "./vision-observability.js";

test("settle timeout explains changing state without leaking content, values or fingerprints", async ({ page }) => {
  await page.setContent(`<button>private-page-text</button><input type="hidden" value="private-form-value">
    <script>let n = 0; setInterval(() => {
      document.querySelector('button').setAttribute('data-changing', 'private-attribute-' + ++n);
      document.querySelector('input').value = 'private-form-value-' + n;
    }, 10);</script>`);
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    const result = await visionLogScope.run({ context: {}, fields: { session_id: "synthetic-session",
      operation_id: "synthetic-operation", stage: "operation_execute" } },
    () => settleState(page, Date.now() + 700, 160));
    expect(result.settled).toBe(false);
    const log = JSON.parse(lines[0]);
    expect(log).toMatchObject({ level: "error", event: "vision.state.settle_timeout", failure_stage: "page_settle",
      session_id: "synthetic-session", operation_id: "synthetic-operation", reason: "state_kept_changing",
      quiet_required_ms: 160, document_ready: null });
    expect(log.visible_state_changes).toBeGreaterThan(0);
    expect(log.form_value_changes).toBeGreaterThan(0);
    expect(log.samples).toBeGreaterThan(1);
    expect(log.message).toContain("state_kept_changing");
    expect(lines.join("\n")).not.toMatch(/private-|fingerprint|<button>/);
  } finally { console.error = original; }
});

test("stable pages retain their successful result without timeout diagnostics", async ({ page }) => {
  await page.setContent("<button>Stable</button>");
  const lines: string[] = [], original = console.error;
  console.error = (line: string) => lines.push(line);
  try {
    expect((await settleState(page, Date.now() + 2000, 160)).settled).toBe(true);
    expect(lines).toEqual([]);
  } finally { console.error = original; }
});

test("a slow observation arriving after the deadline cannot certify readiness", async ({ page }) => {
  await page.setContent('<button>Stable</button>');
  const evaluate = page.evaluate.bind(page);
  let reads = 0;
  page.evaluate = (async (...args: Parameters<Page['evaluate']>) => {
    if (++reads === 2) await new Promise(resolve => setTimeout(resolve, 350));
    return evaluate(...args);
  }) as Page['evaluate'];
  try {
    expect((await settleState(page, Date.now() + 250, 80)).settled).toBe(false);
  } finally { page.evaluate = evaluate; }
});
