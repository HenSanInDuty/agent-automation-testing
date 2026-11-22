/** Offline policy microbenchmark, NOT a second production exploration runner. */
import { chromium, type Page } from '@playwright/test';
import { equivalentState, inspectState } from '../vision-checkpoints.js';

const repetitions = 20;
const cases = [
  'stable', 'passive_motion', 'unrelated_link', 'target_moves', 'popup',
  'target_renamed', 'target_replaced', 'target_covered', 'duplicate_target',
  'form_changed', 'navigation_changed', 'lost_ack',
] as const;
type Scenario = typeof cases[number];
type Policy = 'current_checkpoint_gate' | 'sequential_target_prototype';
const blocked = new Set<Scenario>([
  'target_renamed', 'target_replaced', 'target_covered', 'duplicate_target',
  'form_changed', 'navigation_changed',
]);
const html = `<style>button{width:130px;height:40px;margin:10px}
  #other{position:absolute;left:700px;top:300px}#ticker{position:absolute;top:400px}</style>
  <button id="one">Action 1</button><button id="two">Action 2</button>
  <button id="three">Action 3</button><a id="other" href="#other">Article</a>
  <input type="hidden" name="csrf" value="synthetic"><div id="ticker">Tick</div>
  <script>window.executions=[];window.wrong=0;
  document.querySelectorAll('button').forEach((button,index)=>button.onclick=()=>{
    window.executions.push(index+1);
    if(window.openPopup && index===0) window.open('about:blank','benchmark-popup');
  });</script>`;

async function mutate(page: Page, scenario: Scenario) {
  await page.evaluate(kind => {
    const button = document.querySelector('#one') as HTMLButtonElement;
    if (kind === 'passive_motion') document.querySelector('#ticker')!.textContent = 'Tick changed';
    if (kind === 'unrelated_link') document.querySelector('#other')!.textContent = 'Another article';
    if (kind === 'target_moves') button.style.transform = 'translateY(60px)';
    if (kind === 'target_renamed') button.textContent = 'Delete everything';
    if (kind === 'target_replaced') {
      const replacement = button.cloneNode(true) as HTMLButtonElement;
      replacement.onclick = () => { (window as any).wrong++; };
      button.replaceWith(replacement);
    }
    if (kind === 'target_covered') {
      const cover = document.createElement('div');
      cover.style.cssText = 'position:fixed;inset:0;z-index:999;background:white';
      document.body.append(cover);
    }
    if (kind === 'duplicate_target') {
      const duplicate = button.cloneNode(true) as HTMLButtonElement;
      duplicate.removeAttribute('id'); document.body.append(duplicate);
    }
    if (kind === 'form_changed') (document.querySelector('input') as HTMLInputElement).value = 'changed';
    if (kind === 'navigation_changed') location.hash = 'different-context';
    if (kind === 'popup') (window as any).openPopup = true;
  }, scenario);
}

async function run(page: Page, policy: Policy, scenario: Scenario) {
  const started = performance.now();
  let reason = 'completed', proposals = 0, observations = 0;
  let popupCount = 0;
  await page.setContent(html);
  for (let step = 1; step <= 3; step++) {
    const target = page.getByRole('button', { name: `Action ${step}`, exact: true });
    const before = await inspectState(page); observations++;
    const handle = await target.elementHandle();
    const identity = await target.evaluate(el => ({
      text: el.textContent, role: el.getAttribute('role'), type: el.getAttribute('type'),
      id: el.id, label: el.getAttribute('aria-label'),
    }));
    // Deterministic planner delay; never presented as real model latency.
    await page.waitForTimeout(10); proposals++;
    if (step === 1) await mutate(page, scenario);
    const current = await inspectState(page); observations++;
    // Shared live-node fence approximates the worker's trusted snapshot binding.
    // Do not attribute an unsafe replacement click to the production baseline.
    if (!handle || !await handle.evaluate(el => el.isConnected)) { reason = 'node_replaced'; break; }
    if (policy === 'current_checkpoint_gate') {
      if (!equivalentState(before, current)) { reason = 'stale_checkpoint'; break; }
    } else {
      // Keep URL/form context and exact live-node identity; tolerate unrelated controls.
      if (before.url_fingerprint !== current.url_fingerprint ||
          before.form_presence_fingerprint !== current.form_presence_fingerprint ||
          before.privateForms !== current.privateForms) { reason = 'context_changed'; break; }
      if (await target.count() !== 1) { reason = 'target_ambiguous_or_changed'; break; }
      const fresh = await target.elementHandle();
      if (!fresh || !await handle.evaluate((el, other) => el === other, fresh)) {
        reason = 'node_replaced'; break;
      }
      const currentIdentity = await target.evaluate(el => ({
        text: el.textContent, role: el.getAttribute('role'), type: el.getAttribute('type'),
        id: el.id, label: el.getAttribute('aria-label'),
      }));
      if (JSON.stringify(identity) !== JSON.stringify(currentIdentity)) { reason = 'identity_changed'; break; }
    }
    try {
      // Both policies use identical locator uniqueness/actionability and click behavior.
      await target.click({ trial: true, timeout: 250 });
      if (scenario === 'popup' && step === 1) {
        const popupPending = page.waitForEvent('popup', { timeout: 1000 });
        await target.click({ timeout: 250 });
        const popup = await popupPending; popupCount++;
        await popup.close();
      } else await target.click({ timeout: 250 });
    } catch { reason = 'actionability_blocked'; break; }
    if (scenario === 'lost_ack' && step === 1) { reason = 'outcome_unknown'; break; }
  }
  const evidence = await page.evaluate(() => ({
    executions: (window as any).executions as number[], wrong: (window as any).wrong as number,
  }));
  const duplicateClicks = evidence.executions.length - new Set(evidence.executions).size;
  const forbiddenClicks = blocked.has(scenario) ? evidence.executions.length + evidence.wrong : evidence.wrong;
  const complete = reason === 'completed' && evidence.executions.join(',') === '1,2,3';
  const correct = blocked.has(scenario) ? forbiddenClicks === 0 && reason !== 'completed'
    : scenario === 'lost_ack' ? reason === 'outcome_unknown' && evidence.executions.join(',') === '1'
    : complete && (scenario !== 'popup' || popupCount === 1);
  return { policy, scenario, correct, complete, reason, proposals, observations, popupCount,
    clicks: evidence.executions.length, wrongClicks: evidence.wrong, forbiddenClicks,
    duplicateClicks, durationMs: Math.round((performance.now() - started) * 1000) / 1000 };
}

const browser = await chromium.launch({ headless: true });
const rows = [];
try {
  for (let repetition = 0; repetition < repetitions; repetition++) {
    for (const scenario of cases) {
      const policies: Policy[] = ['current_checkpoint_gate', 'sequential_target_prototype'];
      if (repetition % 2) policies.reverse();
      for (const policy of policies) {
        const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
        try { rows.push({ repetition, ...await run(await context.newPage(), policy, scenario) }); }
        finally { await context.close(); }
      }
    }
  }
  process.stdout.write(JSON.stringify({ browserVersion: browser.version(), repetitions,
    planner: 'deterministic, 10 ms per proposal; no model or network calls', rows }));
} finally { await browser.close(); }
