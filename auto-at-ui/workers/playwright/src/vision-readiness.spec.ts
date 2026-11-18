import { expect, test } from "@playwright/test";
import { equivalentState, inspectState, setInteractionScope, settleState } from "./vision-checkpoints.js";

test("button scope tolerates unrelated moving links while retaining full semantic evidence", async ({ page }) => {
  setInteractionScope(page, "buttons");
  await page.setContent('<button>Save</button><a href="/article" style="position:absolute;left:500px;top:200px">Article</a>');
  const before = await inspectState(page);
  await page.locator('a').evaluate(el => { el.style.transform = 'translateX(100px)'; el.textContent = 'Next article'; });
  const after = await inspectState(page);
  expect(equivalentState(before, after)).toBe(true);
  expect(before.semantic_fingerprint).not.toBe(after.semantic_fingerprint);
});

for (const change of ['move', 'cover', 'rename', 'disable', 'form'] as const) {
  test(`button scope still detects ${change}`, async ({ page }) => {
    setInteractionScope(page, 'buttons');
    await page.setContent('<button>Save</button><input type="hidden" value="seed"><a href="/a">Other</a>');
    const before = await inspectState(page);
    await page.evaluate(kind => {
      const button = document.querySelector('button')!;
      if (kind === 'move') button.style.transform = 'translateX(20px)';
      if (kind === 'rename') button.textContent = 'Delete';
      if (kind === 'disable') button.disabled = true;
      if (kind === 'form') document.querySelector('input')!.value = 'changed';
      if (kind === 'cover') document.querySelector('a')!.style.cssText = 'position:fixed;inset:0;z-index:1000;background:red';
    }, change);
    expect(equivalentState(before, await inspectState(page))).toBe(false);
  });
}

test("anonymous rounded button resize keeps live-node readiness but covering its click point does not", async ({ page }) => {
  setInteractionScope(page, 'buttons');
  await page.setContent('<button style="position:absolute;left:100px;top:100px;width:12px;height:12px;padding:0;border:0;border-radius:999px"></button>');
  const before = await inspectState(page);
  await page.locator('button').evaluate(el => (el as HTMLElement).style.width = '41px');
  const resized = await inspectState(page);
  expect(equivalentState(before, resized)).toBe(true);
  expect(before.semantic_fingerprint).not.toBe(resized.semantic_fingerprint);
  await page.evaluate(() => {
    const cover = document.createElement('div');
    cover.style.cssText = 'position:absolute;left:118px;top:104px;width:5px;height:5px;background:red;z-index:999';
    document.body.append(cover);
  });
  expect(equivalentState(resized, await inspectState(page))).toBe(false);
});

test("passive visible motion and framework attributes do not invalidate interaction state", async ({ page }) => {
  await page.setContent(`<button id="target">Continue</button>
    <div id="clock" style="position:absolute;left:600px;top:100px">Tick</div>
    <div id="banner" style="position:absolute;left:600px;top:200px;width:120px;height:40px;background:red">Slide</div>
    <script>let n=0; setInterval(() => {
      document.querySelector('#clock').textContent = 'Tick ' + ++n;
      document.querySelector('#banner').style.transform = 'translateX(' + n % 20 + 'px)';
      document.querySelector('#target').setAttribute('data-render-counter', String(n));
    }, 20);</script>`);
  const before = await inspectState(page);
  const settled = await settleState(page, Date.now() + 2000, 160);
  expect(settled.settled).toBe(true);
  expect(equivalentState(before, settled.state)).toBe(true);
  expect(before.semantic_fingerprint).not.toBe(settled.state.semantic_fingerprint);
});

for (const change of ["move", "cover", "disable", "rename", "href", "form", "transparent", "iframe_cover"] as const) {
  test(`interaction state still detects ${change}`, async ({ page }) => {
    await page.setContent(`<div id="wrapper"><button id="target">Continue</button></div>
      <a id="link" href="https://fixture.test/a">Next</a><input type="hidden" value="private-form-value">
      <iframe id="frame" srcdoc="<button>Embedded</button>" style="position:absolute;left:500px;top:200px;width:200px;height:100px"></iframe>`);
    await page.frameLocator('#frame').getByRole('button').waitFor();
    const before = await inspectState(page);
    await page.evaluate((kind) => {
      const target = document.querySelector('#target') as HTMLButtonElement;
      if (kind === "move") target.style.transform = "translateX(100px)";
      if (kind === "disable") target.disabled = true;
      if (kind === "rename") target.setAttribute('aria-label', 'Different action');
      if (kind === "href") document.querySelector('#link')!.setAttribute('href', 'https://fixture.test/b');
      if (kind === "form") (document.querySelector('input') as HTMLInputElement).value = 'changed-private-value';
      if (kind === "transparent") (document.querySelector('#wrapper') as HTMLElement).style.opacity = '0';
      if (kind === "cover" || kind === "iframe_cover") {
        const overlay = document.createElement('div');
        overlay.style.cssText = kind === "cover" ? 'position:fixed;inset:0;z-index:1000' :
          'position:fixed;left:500px;top:200px;width:210px;height:110px;z-index:1000';
        document.body.append(overlay);
      }
    }, change);
    expect(equivalentState(before, await inspectState(page))).toBe(false);
  });
}

test("explicit loading state is respected even when controls stand still", async ({ page }) => {
  await page.setContent('<main aria-busy="true"><button>Continue</button></main>');
  const logs: string[] = [], original = console.error;
  console.error = (line: string) => logs.push(line);
  try {
    expect((await settleState(page, Date.now() + 400, 80)).settled).toBe(false);
    expect(JSON.parse(logs[0])).toMatchObject({ reason: 'document_busy', document_ready: true, document_busy: true });
  } finally { console.error = original; }
  await page.locator('main').evaluate(el => el.removeAttribute('aria-busy'));
  expect((await settleState(page, Date.now() + 1000, 80)).settled).toBe(true);
});
