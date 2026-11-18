/** Read-only live audit. No clicks, model calls or changes to the live DOM. */
import { chromium } from '@playwright/test';
import { createHash, randomUUID } from 'node:crypto';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { parseArgs } from 'node:util';
import { visualButtonSemantics } from '../vision-button-semantics.js';
import { inspectState, setInteractionScope } from '../vision-checkpoints.js';
import { observeDom } from '../vision-dom.js';
import { validateVision, type VisualWorkerObserveDom } from '../vision-contract.js';
import { matchAnnotations, type Annotation, type AuditedElement } from './visual-buttons-audit-model.js';

const { values } = parseArgs({ options: {
  dataset: { type: 'string', default: '../../benchmark/vision/visual-buttons/mongchiton-desktop.json' },
  output: { type: 'string' }, width: { type: 'string' }, height: { type: 'string' },
} });
const data = readFileSync(values.dataset!, 'utf8');
const dataset = JSON.parse(data) as { source_url: string; viewport: {width: number; height: number}; examples: Annotation[] };
const viewport = { width: Number(values.width ?? dataset.viewport.width), height: Number(values.height ?? dataset.viewport.height) };
if (!Number.isInteger(viewport.width) || !Number.isInteger(viewport.height) || viewport.width < 320 || viewport.height < 240)
  throw new Error('Invalid viewport');
const output = resolve(values.output ?? '../../benchmark/vision/visual-buttons/audit-' + Date.now() + '-' + randomUUID() + '.json');
const screenshot = output.replace(/\.json$/, '') + '.png';
if (existsSync(output) || existsSync(screenshot)) throw new Error('Audit output already exists');
mkdirSync(dirname(output), { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport });
const found = new Map<string, AuditedElement>(), annotatedDom = new Map<string, AuditedElement>();
const bound = new Set<string>(), failures: string[] = [];
let skipped = 0, bottomReached = false;
try {
  await page.goto(dataset.source_url, { waitUntil: 'domcontentloaded', timeout: 60000 });
  await page.waitForTimeout(3500);
  setInteractionScope(page, 'visual_buttons');
  const identity = { tenant_id: 'dataset-audit', project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
  for (let index = 0; index < 20; index++) {
    const semantic = await page.evaluate(visualButtonSemantics);
    const entries = await page.evaluate(async () => {
      // Independent DOM candidates for manual review; not classifier-derived labels.
      const result: AuditedElement[] = [];
      for (const el of document.querySelectorAll('a,button,[role="button"],div.character-switcher')) {
        const rect = el.getBoundingClientRect(), style = getComputedStyle(el);
        if (rect.width <= 0 || rect.height <= 0 || style.visibility !== 'visible' ||
            rect.bottom <= 0 || rect.top >= innerHeight) continue;
        const parts: string[] = []; let node: Element | null = el;
        while (node && node.tagName !== 'HTML') {
          const parent: Element | null = node.parentElement;
          if (!parent) break;
          const siblings = Array.from(parent.children).filter(other => other.tagName === node!.tagName);
          parts.unshift(node.tagName.toLowerCase() + ':nth-of-type(' + (siblings.indexOf(node) + 1) + ')');
          node = parent;
        }
        let href: string | null = null, href_sha256: string | null = null;
        if (el instanceof HTMLAnchorElement && /^https?:/.test(el.href)) {
          href_sha256 = Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(el.href))))
            .map(byte => byte.toString(16).padStart(2, '0')).join('');
          const url = new URL(el.href); url.username = ''; url.password = ''; url.search = ''; url.hash = '';
          href = url.toString();
        }
        const hit = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        const actionable = rect.left >= 0 && rect.right <= innerWidth && rect.top >= 0 && rect.bottom <= innerHeight &&
          !!hit && (el === hit || el.contains(hit));
        result.push({ path: 'html > ' + parts.join(' > '), classes: String(el.className), actionable, href_sha256,
          label: (el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 240),
          tag: el.tagName.toLowerCase(), href, target: el.getAttribute('target'),
          box: { x: Math.round(rect.x), y: Math.round(rect.y + scrollY), width: Math.round(rect.width), height: Math.round(rect.height) } });
      }
      return result;
    });
    for (const entry of entries) if (entry.actionable || !annotatedDom.has(entry.path)) annotatedDom.set(entry.path, entry);
    const paths = new Set(semantic.map(item => item.path));
    for (const entry of entries) if (entry.actionable && paths.has(entry.path)) found.set(entry.path, entry);
    try {
      const state = await inspectState(page);
      const snapshot = await observeDom(page, validateVision<VisualWorkerObserveDom>('VisualWorkerObserveDom', {
        ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: state.fingerprint,
      }));
      skipped += snapshot.data.observation.skipped_count;
      for (const item of snapshot.data.bindings) bound.add(item.descriptor.value);
    } catch { failures.push('observation_unavailable:' + index); }
    bottomReached = await page.evaluate(() => Math.ceil(scrollY + innerHeight) >= document.documentElement.scrollHeight - 1);
    if (bottomReached) break;
    await page.evaluate(() => scrollBy(0, Math.floor(innerHeight * .75)));
    await page.waitForTimeout(700);
  }
  await page.screenshot({ path: screenshot, fullPage: true });
  const detected = matchAnnotations(dataset.examples, [...found.values()]);
  const reviewed = matchAnnotations(dataset.examples, [...annotatedDom.values()]);
  const positives = dataset.examples.filter(e => e.expected);
  const result = {
    schema_version: 'visual-button-live-audit-v2', checked_at: new Date().toISOString(),
    source_url: dataset.source_url, viewport, dataset_sha256: createHash('sha256').update(data).digest('hex'),
    browser_version: browser.version(), model_calls: 0, clicks: 0,
    expected: positives.length, identified: found.size, bound: bound.size, skipped, failures, bottom_reached: bottomReached,
    missing: positives.filter(e => !detected.matches.some(m => m.expected_id === e.id)).map(e => e.id),
    unexpected: detected.unmatched.map(e => e.path), false_positives: detected.matches.filter(e => !e.expected),
    matches: detected.matches.map(e => ({ ...e, bound: bound.has(e.path) })),
    review_matches: reviewed.matches, review_missing: reviewed.missing, public_elements: [...annotatedDom.values()],
    screenshot_file: screenshot.split(/[\\/]/).at(-1),
    screenshot_sha256: createHash('sha256').update(readFileSync(screenshot)).digest('hex'),
    scope: 'Read-only homepage desktop scroll-through; detection evidence only, not click correctness.',
  };
  writeFileSync(output, JSON.stringify(result, null, 2) + '\n', { flag: 'wx' });
  console.log(JSON.stringify({ output, expected: result.expected, identified: result.identified,
    missing: result.missing, unexpected: result.unexpected.length, failures, review_missing: reviewed.missing }));
  if (result.missing.length || result.unexpected.length || result.false_positives.length || skipped || failures.length || !bottomReached)
    process.exitCode = 1;
} finally { await browser.close(); }
