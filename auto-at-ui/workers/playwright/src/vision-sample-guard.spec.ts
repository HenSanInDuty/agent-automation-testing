import { chromium, expect, test } from '@playwright/test';
import { equivalentState, inspectState, setInteractionScope } from './vision-checkpoints.js';
import { captureVisionScreen } from './vision-screen.js';

test('fast sample encoding preserves every rendered pixel', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.setContent('<body style="background:linear-gradient(20deg,#f83,#178)"><button>Selected slide</button></body>');
    const standard = await captureVisionScreen(page, 5000);
    const fast = await captureVisionScreen(page, 5000, true);
    const equal = await page.evaluate(async ([a, b]) => {
      const images = await Promise.all([a, b].map(async data => createImageBitmap(
        await (await fetch('data:image/png;base64,' + data)).blob())));
      const pixels = images.map(image => {
        const canvas = new OffscreenCanvas(image.width, image.height), ctx = canvas.getContext('2d')!;
        ctx.drawImage(image, 0, 0); return ctx.getImageData(0, 0, image.width, image.height).data;
      });
      return pixels[0].length === pixels[1].length && pixels[0].every((value, i) => value === pixels[1][i]);
    }, [standard.toString('base64'), fast.toString('base64')]);
    expect(equal).toBe(true);
  } finally { await browser.close(); }
});

for (const mutation of ['hidden_form', 'shadow_form', 'frame_form', 'editable', 'control', 'overlay', 'passive'] as const) {
  test(`sample guard preserves complete state comparison: ${mutation}`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
      await page.setContent(`<main><button>Choose</button><input type="hidden" value="private">
        <div id="host"></div><iframe srcdoc="<input type=hidden value=frame-private>"></iframe>
        <div contenteditable="true" style="position:absolute;top:2000px">editable-private</div>
        <p>Passive</p></main>`);
      await page.evaluate(() => {
        document.querySelector('#host')!.attachShadow({ mode: 'open' }).innerHTML = '<input type="hidden" value="shadow-private">';
      });
      await page.waitForFunction(() => !!document.querySelector('iframe')?.contentDocument?.querySelector('input'));
      setInteractionScope(page, 'visual_buttons');
      const before = await inspectState(page), beforeGuard = await inspectState(page, false);
      expect(equivalentState(before, beforeGuard)).toBe(true);
      await page.evaluate(change => {
        if (change === 'hidden_form') document.querySelector('input')!.value = 'changed';
        if (change === 'shadow_form') document.querySelector('#host')!.shadowRoot!.querySelector('input')!.value = 'changed';
        if (change === 'frame_form') document.querySelector('iframe')!.contentDocument!.querySelector('input')!.value = 'changed';
        if (change === 'editable') document.querySelector('[contenteditable]')!.textContent = 'changed';
        if (change === 'control') document.querySelector('button')!.disabled = true;
        if (change === 'overlay') {
          const modal = document.createElement('div'); modal.setAttribute('role', 'dialog');
          modal.style.cssText = 'position:fixed;inset:0;background:white'; document.body.append(modal);
        }
        if (change === 'passive') document.querySelector('p')!.textContent = 'Different slide';
      }, mutation);
      const after = await inspectState(page), afterGuard = await inspectState(page, false);
      expect(equivalentState(after, afterGuard)).toBe(true);
      expect(afterGuard.privateForms).toBe(after.privateForms);
      expect(equivalentState(before, after)).toBe(mutation === 'passive');
      expect(equivalentState(beforeGuard, afterGuard)).toBe(mutation === 'passive');
    } finally { await browser.close(); }
  });
}
