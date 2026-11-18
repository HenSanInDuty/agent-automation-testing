import { randomUUID } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { chromium, expect, test, type Browser } from '@playwright/test';
import { VisualOperationWorker } from './vision-operations.js';
import { startVisionTarget } from './fixtures/vision-target.js';
import { inspectState, equivalentState } from './vision-checkpoints.js';

for (const mutation of ['unchanged', 'passive_class', 'replacement', 'destination_swap', 'occluded', 'form', 'reload',
  'restored_navigation', 'restored_spa', 'restored_swap', 'restored_form'] as const) {
  test(`target preflight keeps approved identity: ${mutation}`, async () => {
    const fixture = await startVisionTarget();
    const root = await mkdtemp(join(tmpdir(), 'auto-at-preflight-'));
    let browser: Browser;
    const worker = new VisualOperationWorker(root, async options => {
      browser = await chromium.launch(options); return browser;
    });
    const identity = { contract_version: 'v4', tenant_id: 'fixture-tenant',
      project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
    try {
      const opened = await worker.open({ ...identity, target_url: fixture.origin,
        allowed_origins: [fixture.origin], interaction_scope: 'visual_buttons',
        required_capabilities: ['visual-button-scope-v1', 'target-preflight-v1'],
        deadline: new Date(Date.now() + 60000).toISOString(), max_session_seconds: 60,
        max_states: 10, max_hops: 10, max_screenshot_bytes: 1000000 });
      const page = browser!.contexts()[0].pages()[0];
      await page.route(fixture.origin + '/', route => route.fulfill({ contentType: 'text/html', body: `
        <style>a{display:inline-block;width:140px;height:60px;background:#234;border-radius:8px;color:white}</style>
        <a href="/a">Video</a><a href="/b">Video</a><input type="hidden" value="private-original">` }));
      const cp = randomUUID();
      const prepared = await worker.prepare({ ...identity, operation_id: randomUUID(), purpose: 'setup',
        state_id: randomUUID(), proposal_id: null, action: { kind: 'navigate' },
        expected_state_fingerprint: opened.state_fingerprint, checkpoint_id: cp, checkpoint_state_id: randomUUID() });
      const before = prepared.frames.find(f => f.role === 'before')!;
      const navigated = await worker.execute({ ...identity, operation_id: prepared.operation.id,
        prepared_handle: prepared.prepared_handle, before_persisted: true,
        before_frame_id: before.id, before_checksum: before.checksum });
      expect(navigated.operation.status).toBe('completed');
      const observed = await worker.observeDom({ ...identity, snapshot_id: randomUUID(),
        expected_state_fingerprint: navigated.state_fingerprint });
      expect(observed.data.bindings).toHaveLength(2); // same label never collapses distinct positions/destinations
      const check = { ...identity, snapshot_id: observed.data.observation.snapshot_id,
        element_id: observed.data.bindings[0].element_id, checkpoint_id: cp };
      expect((await worker.checkTarget(check)).matches_current).toBe(true);
      await page.evaluate(change => {
        const a = document.querySelector('a')!;
        if (change === 'passive_class') a.className = 'animation-phase-two';
        if (['replacement', 'restored_spa'].includes(change)) a.replaceWith(a.cloneNode(true));
        if (['destination_swap', 'restored_swap'].includes(change)) {
          const b = document.querySelectorAll('a')[1]; const href = a.href; a.href = b.href; b.href = href;
        }
        if (change === 'occluded') {
          const cover = document.createElement('div'); cover.style.cssText = 'position:fixed;inset:0;background:black;z-index:99';
          document.body.append(cover);
        }
        if (['form', 'restored_form'].includes(change)) document.querySelector('input')!.value = 'private-changed';
      }, mutation);
      if (['reload', 'restored_navigation'].includes(mutation)) await page.reload();
      const result = await worker.checkTarget({ ...check, allow_restored_document: mutation.startsWith('restored_') });
      expect(result.matches_current).toBe(['unchanged', 'passive_class', 'restored_navigation', 'restored_spa'].includes(mutation));
      // Explicit restoration also requires the complete saved checkpoint.
      expect(result.context_matches).toBe(!['form', 'restored_form', 'restored_swap', 'reload'].includes(mutation));
      expect(page.url()).toBe(fixture.origin + '/'); // no click or navigation from checking
      const complete = await inspectState(page), guard = await inspectState(page, false);
      expect(equivalentState(complete, guard)).toBe(true);
      expect(guard.privateForms).toBe(complete.privateForms);
    } finally {
      await worker.close(identity, identity.session_id); await fixture.close();
      expect(resolve(root).startsWith(resolve(tmpdir()) + sep)).toBe(true);
      await rm(root, { recursive: true, force: true });
    }
  });
}
