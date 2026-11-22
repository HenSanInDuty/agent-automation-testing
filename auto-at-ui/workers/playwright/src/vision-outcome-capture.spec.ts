import { createHash, randomUUID } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, sep } from 'node:path';
import { chromium, expect, test, type Browser } from '@playwright/test';
import { VisualOperationWorker } from './vision-operations.js';
import { startVisionTarget } from './fixtures/vision-target.js';

for (const change of ['passive', 'loaded', 'form', 'control', 'replacement', 'popup', 'navigation', 'capture_failure', 'capture_timeout'] as const) {
  test(`local click outcome capture preserves ${change} behavior`, async () => {
    const target = await startVisionTarget();
    const root = await mkdtemp(join(tmpdir(), 'auto-at-outcome-capture-'));
    let browser: Browser;
    const worker = new VisualOperationWorker(root, async options => {
      browser = await chromium.launch(options); return browser;
    });
    const identity = { contract_version: 'v4', tenant_id: 'fixture-tenant',
      project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
    const logs: string[] = [], originalLog = console.log;
    console.log = line => logs.push(String(line));
    try {
      const opened = await worker.open({ ...identity, target_url: target.origin,
        allowed_origins: [target.origin], interaction_scope: 'visual_buttons',
        required_capabilities: ['visual-button-scope-v1'],
        deadline: new Date(Date.now() + 60000).toISOString(), max_session_seconds: 60,
        max_states: 20, max_hops: 10, max_screenshot_bytes: change === 'loaded' ? 5000000 : 1000000 });
      const page = browser!.contexts()[0].pages()[0];
      let loads = 0;
      await page.route(target.origin + '/', route => route.fulfill({ contentType: 'text/html',
        body: `<button style="width:150px;height:50px" onclick="
          window.clicks=(window.clicks||0)+1;
          document.querySelector('#slide').dataset.index='4';
          document.querySelector('#slide').textContent='Slide 4';
          setTimeout(() => {
            document.querySelector('#slide').dataset.index='5';
            document.querySelector('#slide').textContent='Slide 5';
            ${change === 'form' ? "document.querySelector('input').value='changed-private';" : ''}
            ${change === 'control' ? "document.querySelector('button').disabled=true;" : ''}
            ${change === 'replacement' ? "const b=document.querySelector('button');b.replaceWith(b.cloneNode(true));" : ''}
            ${change === 'popup' ? "window.open('/a');" : ''}
            ${change === 'navigation' ? "location.reload();" : ''}
          },${change === 'loaded' ? 650 : 350})">Select four</button>
          <div id="slide" data-index="${++loads > 1 ? 9 : 1}">Slide</div>
          <input type="hidden" value="initial-private">
          ${change === 'loaded' ? `<canvas width="1280" height="600"></canvas><script>
            const c=document.querySelector('canvas'),ctx=c.getContext('2d');
            const data=ctx.createImageData(1280,600);let seed=1234567;
            for(let i=0;i<data.data.length;i+=4){seed=(Math.imul(seed,1664525)+1013904223)>>>0;
              const noise=(i/4)%1280<480;
              data.data[i]=noise?seed&255:210;data.data[i+1]=noise?(seed>>>8)&255:210;data.data[i+2]=noise?(seed>>>16)&255:210;data.data[i+3]=255;}
            ctx.putImageData(data,0,0);
            for(let i=0;i<575;i++){const n=document.createElement('div');n.textContent='Synthetic detail '+i;
              n.style.cssText='position:absolute;left:'+i%1280+'px;top:'+i%600+'px;pointer-events:none';
              document.body.append(n);}
          </script>` : ''}` }));
      let current = opened.state_fingerprint;
      const prepare = (action: object, extra: object = {}) => worker.prepare({ ...identity,
        operation_id: randomUUID(), purpose: 'explore', action,
        expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID(),
        ...extra });
      const execute = async (prepared: Awaited<ReturnType<typeof prepare>>) => {
        expect(prepared.operation.status).toBe('prepared');
        const before = prepared.frames.find(f => f.role === 'before')!;
        const result = await worker.execute({ ...identity, operation_id: prepared.operation.id,
          prepared_handle: prepared.prepared_handle, before_persisted: true,
          before_frame_id: before.id, before_checksum: before.checksum });
        current = result.state_fingerprint!;
        return result;
      };
      await execute(await prepare({ kind: 'navigate' }, { purpose: 'setup',
        checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() }));
      const observation = await worker.observeDom({ ...identity, snapshot_id: randomUUID(),
        expected_state_fingerprint: current });
      const element = observation.data.observation.elements.find(e => e.name === 'Select four')!;
      const prepared = await prepare({ kind: 'click', x: 0.5, y: 0.5 }, {
        dom_snapshot_id: observation.data.observation.snapshot_id, dom_element_id: element.element_id,
        checkpoint_id: randomUUID(), checkpoint_state_id: randomUUID() });
      const context = page.context(), original = context.newCDPSession.bind(context);
      const captures = new Map<string, { before: string | null; after: string | null }>();
      let failed = false;
      context.newCDPSession = async target => {
        const client = await original(target), send = client.send.bind(client);
        client.send = async (method, params) => {
          if (method !== 'Page.captureScreenshot') return send(method, params);
          if (change === 'capture_failure' && !failed) { failed = true; throw new Error('synthetic'); }
          if (change === 'capture_timeout' && !failed) {
            failed = true; await new Promise(resolve => setTimeout(resolve, 600));
          }
          const before = await page.locator('#slide').getAttribute('data-index').catch(() => null);
          const frame = await send(method, params);
          if (!('data' in frame) || typeof frame.data !== 'string') throw new Error('missing pixels');
          const after = await page.locator('#slide').getAttribute('data-index').catch(() => null);
          captures.set(createHash('sha256').update(Buffer.from(frame.data, 'base64')).digest('hex'),
            { before, after });
          return frame;
        };
        return client;
      };
      const result = await execute(prepared);
      if (change === 'loaded') originalLog(JSON.stringify({ fixture: 'loaded',
        stages: logs.map(line => JSON.parse(line)).filter(row => row.event === 'vision.evidence.sample') }));
      expect(result.operation.status, result.operation.outcome_code ?? '').toBe('completed');
      const frame = result.frames.find(f => f.role === 'after')!;
      expect(frame).toBeDefined();
      if (change === 'popup') {
        expect(result.operation.after_page_id).not.toBe(result.operation.before_page_id);
        expect(result.checkpoint!.page_url).toBe(target.origin + '/a');
      } else {
        const expected = change === 'passive' || change === 'loaded' ? '4' : change === 'navigation' ? '9' : '5';
        expect(captures.get(frame.checksum)).toEqual({ before: expected, after: expected });
      }
      if (change !== 'navigation') expect(await page.evaluate(() => (window as any).clicks)).toBe(1);
      if (change === 'passive') expect(await page.locator('#slide').getAttribute('data-index')).toBe('5');
      expect((await worker.checkpoint(identity, identity.session_id, result.checkpoint!.id)).matches_current).toBe(true);
      expect(JSON.stringify(result)).not.toContain('changed-private');
      const samples = logs.map(line => JSON.parse(line)).filter(row => row.event === 'vision.evidence.sample');
      expect(samples).toHaveLength(1);
      expect(samples[0]).toMatchObject({ session_id: identity.session_id,
        operation_id: result.operation.id, sample_budget_ms: 500 });
      expect(samples[0].duration_ms).toBeGreaterThanOrEqual(0);
      if (change === 'loaded') {
        expect(frame.byte_count).toBeGreaterThan(600000);
        expect(samples[0].sample_status).toBe('sampled');
        expect(samples[0].duration_ms).toBeLessThanOrEqual(500);
        expect(logs.map(line => JSON.parse(line)).some(row => row.event === 'vision.evidence.sample_reuse' && row.reused)).toBe(true);
      }
      if (change === 'capture_failure' || change === 'capture_timeout') {
        expect(samples[0]).toMatchObject({ sample_status: 'error', sample_stage: 'capture' });
      }
      expect(logs.join('\n')).not.toMatch(/initial-private|changed-private|synthetic|http:\/\//);
    } finally {
      console.log = originalLog;
      await worker.close(identity, identity.session_id);
      await target.close();
      expect(resolve(root).startsWith(resolve(tmpdir()) + sep)).toBe(true);
      await rm(root, { recursive: true, force: true });
    }
  });
}
