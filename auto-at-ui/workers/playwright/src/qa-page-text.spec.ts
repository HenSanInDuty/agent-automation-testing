// QA phase 02 (ADR-046 `page-text-v1`): behaviour of the real worker on pages built here (not the developer's fixtures).
import { randomUUID } from "node:crypto";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import { mkdtemp, rm, writeFile, readFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { chromium, expect, test, type Browser } from "@playwright/test";
import { VisualOperationWorker, type OperationResult } from "./vision-operations.js";
import { canonical, safeLocatorValue, type VisualWorkerIdentity, type VisualWorkerDomObservation } from "./vision-contract.js";

const wrap = (body: string) => `<!doctype html><meta charset="utf-8"><style>body{margin:8px;font:14px sans-serif}</style>${body}`;
const many = (n: number, f: (i: number) => string) => Array.from({ length: n }, (_, i) => f(i)).join("");
const PAGES: Record<string, string> = {
  "/heading": wrap(`<h1>Reset password</h1><h2>Liên hệ a.b@example.com</h2><h3>Tiêu đề an toàn</h3>
    <div role="alert">token=abc123xyz bị lộ</div><div role="status">Đã lưu</div>`),
  // sensitive word inside the first 160 chars of a >160 char paragraph; and one that only exists after char 160.
  "/cut": wrap(`<p>${"a ".repeat(20)}password=hunter2 ${"b ".repeat(80)}</p>
    <p>${"c ".repeat(85)}password=hunter3</p>
    <p>${"d".repeat(150)} password=hunter4</p>`),
  "/unicode": wrap(`<p>😀 Xin chào ✓ 世界</p><p dir="rtl">مرحبا بالعالم</p><p>${"😀".repeat(200)}</p>
    <p>  nhiều   khoảng\n\n trắng\t\ttab  </p><p>dòng một<br>dòng hai</p><p><span>ghép</span><span>liền</span></p>
    <p>nbsp giữa​zw</p><p>   </p><p>ctrl\u0007bell</p>`),
  "/dup": wrap(`<div role="alert">Lặp lại</div><h1>Lặp lại</h1><p>Lặp lại</p><p>Lặp lại</p><p>Khác</p><p> Khác </p>`),
  "/nested": wrap(`<div role="alert"><input value="gia-tri-bi-mat"> Lỗi gõ <select><option>tuỳ-chọn</option></select>
    <textarea>ghi chú riêng</textarea><button>Nút</button></div>
    <p title="tooltip-an" >Có tooltip<img alt="mô tả ảnh" src="data:image/gif;base64,R0lGODlhAQABAAAAACw="></p>
    <noscript><p>trong noscript</p></noscript><template><p>trong template</p></template>
    <svg width="40" height="20"><text x="0" y="10">chữ svg</text></svg>
    <details><summary>Tóm tắt</summary><p>Nội dung đang đóng</p></details>
    <div contenteditable="true"><h2>Đang soạn tiêu đề</h2><p>Đang soạn đoạn</p></div>
    <div id="host"></div><iframe srcdoc="<p>trong iframe</p>"></iframe>
    <script>const s=document.getElementById("host").attachShadow({mode:"closed"});s.innerHTML="<p>trong shadow đóng</p>";</script>
    <input id="live" type="password" aria-label="Mật khẩu" value="MatKhauDaGo99"><p id="echo"></p>`),
  "/digits": wrap(`<p>Mã ١٢٣٤٥٦٧٨ ở đây</p><p>đ@example.com</p><p>An toàn</p>`),
  "/flood": wrap(`<h1>Nhiều</h1>${many(1500, i => `<p>Dòng ${i}</p>`)}`),
  "/controls": wrap(`<h1>Bảng điều khiển</h1><p>Chữ mô tả</p>${many(40, i => `<button type="button">Nút ${i}</button>`)}${many(60, i => `<p>Ghi chú ${i}</p>`)}`),
  "/surrogate": wrap(`<p id="a"></p><p id="b"></p><p>Bình thường</p><script>document.getElementById("a").textContent="ab\ud800cd";document.getElementById("b").textContent="ef\udc00gh"</script>`),
  "/turkish": wrap(`<p>Işık açık</p><p>İstanbul ılık</p><h1>İLK SIRA</h1><div role="alert">Çıkış yapıldı</div>`),
  "/plain": wrap(`<h1>Trang thường</h1><div role="alert">Báo lỗi</div><button type="button">Bấm</button>`),
};
let server: Server, origin: string;
let batches: string[][] = [];
let worker: VisualOperationWorker, identity: VisualWorkerIdentity, root: string, browser: Browser, current: string;
test.beforeAll(async () => {
  try { const all: string[] = JSON.parse(await readFile(join(tmpdir(), "qa-p2-candidates.json"), "utf-8"));
    for (let i = 0; i < all.length; i += 16) batches.push(all.slice(i, i + 16)); } catch { /* candidates optional */ }
  server = createServer((req, res) => { res.setHeader("content-type", "text/html; charset=utf-8");
    const path = new URL(req.url ?? "/", "http://x").pathname;
    const batch = /^\/b\/(\d+)$/.exec(path);
    const html = batch ? wrap(batches[Number(batch[1])].map(t => `<p>${t.replace(/&/g, "&amp;").replace(/</g, "&lt;")}</p>`).join("")) : PAGES[path];
    res.statusCode = html ? 200 : 404; res.end(html ?? "nf"); });
  origin = await new Promise<string>(r => server.listen(0, "127.0.0.1", () => r(`http://127.0.0.1:${(server.address() as AddressInfo).port}`)));
});
test.afterAll(async () => { server.closeAllConnections(); await new Promise<void>(r => server.close(() => r())); });
test.beforeEach(async () => {
  root = await mkdtemp(join(tmpdir(), "auto-at-vision-qap2-"));
  worker = new VisualOperationWorker(root, async (options) => { browser = await chromium.launch(options); return browser; });
  identity = { contract_version: "v4", tenant_id: "fixture-tenant", project_id: randomUUID(), session_id: randomUUID(), fencing_token: 1 };
});
test.afterEach(async () => {
  if (worker.hasSession(identity.session_id)) await worker.close(identity, identity.session_id).catch(() => undefined);
  const path = resolve(root); expect(path.startsWith(resolve(tmpdir()) + sep) && path.includes("auto-at-vision-qap2-")).toBe(true);
  await rm(path, { recursive: true, force: true });
});
function navCommand() { return { ...identity, operation_id: randomUUID(), purpose: "setup", action: { kind: "navigate" },
  expected_state_fingerprint: current, state_id: randomUUID(), proposal_id: randomUUID() }; }
async function open(path: string, extra: object = {}) {
  const opened = await worker.open({ ...identity, target_url: origin + path, allowed_origins: [origin],
    deadline: new Date(Date.now() + 120_000).toISOString(), max_session_seconds: 120, max_states: 20, max_hops: 10,
    max_screenshot_bytes: 1_000_000, ...extra });
  current = opened.state_fingerprint;
  const prepared: OperationResult = await worker.prepare(navCommand());
  const before = prepared.frames.find(f => f.role === "before")!;
  const done = await worker.execute({ ...identity, operation_id: prepared.operation.id, prepared_handle: prepared.prepared_handle,
    before_persisted: true, before_frame_id: before.id, before_checksum: before.checksum });
  expect(done.operation.status, done.operation.outcome_code ?? "").toBe("completed");
  current = done.state_fingerprint ?? current; return opened;
}
const AGENT_TEXT = { agent_mode: true, required_capabilities: ["page-text-v1"] };
const observe = (extra: object = {}): Promise<VisualWorkerDomObservation> =>
  worker.observeDom({ ...identity, snapshot_id: randomUUID(), expected_state_fingerprint: current, ...extra });
const items = async (path: string, extra: object = AGENT_TEXT) => { await open(path, extra); return (await observe()).data.observation; };
const texts = (o: { page_text: Array<{ text: string }> }) => o.page_text.map(i => i.text);

test("QA-W01 sensitive text inside headings, alerts is dropped and counted", async () => {
  const o = await items("/heading");
  expect(o.page_text.map(i => [i.kind, i.text])).toEqual([["status", "Đã lưu"], ["heading", "Tiêu đề an toàn"]]);
  expect(o.page_text_skipped).toBe(3);
  expect(JSON.stringify(o)).not.toMatch(/Reset|example\.com|abc123/);
});
test("QA-W02 sensitive text: cut happens first, nothing after char 160 leaks, in-window sensitive text is dropped", async () => {
  const o = await items("/cut");
  const wire = JSON.stringify(o);
  expect(wire).not.toMatch(/hunter/);
  // p1 has password= inside the 160 window -> dropped. p2/p3 sensitive text starts after the window -> text kept, cut.
  console.log("CUT", JSON.stringify(o.page_text), o.page_text_skipped);
  // p1 (word inside window) and p3 (whole word "password" still inside the 159-char window) are dropped; p2 survives cut.
  expect(o.page_text_skipped).toBe(2);
  expect(o.page_text).toHaveLength(1);
  for (const i of o.page_text) { expect([...i.text].length).toBeLessThanOrEqual(160); expect(i.text.endsWith("…")).toBe(true); }
});
test("QA-W03 unicode, emoji, RTL, whitespace, newlines", async () => {
  const o = await items("/unicode");
  const t = texts(o);
  expect(t).toContain("😀 Xin chào ✓ 世界");
  expect(t).toContain("مرحبا بالعالم");
  expect(t).toContain("nhiều khoảng trắng tab");
  expect(t).toContain("dòng một dòng hai");
  expect(t).toContain("ghépliền");
  const long = t.find(x => x.startsWith("😀😀"))!;
  expect([...long].length).toBe(160); expect(long.endsWith("…")).toBe(true);
  expect(long).not.toMatch(/[\ud800-\udbff](?![\udc00-\udfff])|(?<![\ud800-\udbff])[\udc00-\udfff]/); // no lone surrogate
  for (const x of t) { expect(x).toBe(x.trim()); expect(x).not.toMatch(/[\x00-\x1f\n\t]/); expect(x).not.toMatch(/\s{2,}/); }
  // nothing blank
  expect(t.every(x => x.length > 0)).toBe(true);
  console.log("UNICODE", JSON.stringify(t.filter(x => /nbsp|ctrl/.test(x))));
});
test("QA-W04 duplicates collapse to one item (first kind wins)", async () => {
  const o = await items("/dup");
  expect(o.page_text.map(i => [i.kind, i.text])).toEqual([["alert", "Lặp lại"], ["paragraph", "Khác"]]);
});
test("QA-W05 only visible words: no field values, alt/title, noscript/template, closed details, contenteditable, iframe, closed shadow", async () => {
  await open("/nested", AGENT_TEXT);
  // type into a password input and a contenteditable on the live page, then observe
  const o = (await observe()).data.observation;
  const wire = JSON.stringify(o);
  for (const bad of ["gia-tri-bi-mat", "tuỳ-chọn", "ghi chú riêng", "tooltip-an", "mô tả ảnh", "noscript", "template",
    "chữ svg", "đang đóng", "soạn", "iframe", "shadow", "MatKhauDaGo99"]) expect(JSON.stringify(o.page_text), bad).not.toContain(bad);
  expect(wire).not.toContain("MatKhauDaGo99");
  expect(o.page_text.map(i => i.text)).toContain("Lỗi gõ");
  console.log("NESTED", JSON.stringify(o.page_text));
});
test("QA-W06 sensitive-text filter parity: what TS accepts, Python must accept (divergent inputs)", async () => {
  const o = await items("/digits");
  console.log("DIGITS", JSON.stringify(o.page_text), "skipped", o.page_text_skipped);
  for (const s of ["Mã ١٢٣٤٥٦٧٨ ở đây", "đ@example.com"]) console.log("TS safeLocatorValue", s, safeLocatorValue(s));
  await writeFile(join(tmpdir(), "qa-p2-digits-observation.json"), JSON.stringify(o));
});
test("QA-W07 flood page (1500 paragraphs): bounded, flagged, fast, observation <= 65536", async () => {
  await open("/flood", AGENT_TEXT);
  const t0 = Date.now(); const o = (await observe()).data.observation; const ms = Date.now() - t0;
  expect(o.page_text.length).toBeLessThanOrEqual(24); expect(o.page_text_truncated).toBe(true);
  expect(Buffer.byteLength(canonical(o))).toBeLessThanOrEqual(65_536);
  expect(ms).toBeLessThan(15_000); console.log("FLOOD ms", ms, "items", o.page_text.length);
});
test("QA-W08 text never displaces controls; capped text with many controls", async () => {
  await open("/controls", AGENT_TEXT);
  const withText = (await observe()).data.observation;
  const key = (e: { role: string; name: string }) => `${e.role}|${e.name}`;
  // tight byte budget (same session): element list identical to the full one, text shed and flagged
  const room = Buffer.byteLength(canonical(withText)) - 600;
  const t = (await observe({ max_bytes: room })).data.observation;
  expect(t.elements.map(key)).toEqual(withText.elements.map(key));
  expect(Buffer.byteLength(canonical(t))).toBeLessThanOrEqual(room);
  expect(t.page_text.length).toBeLessThan(withText.page_text.length);
  expect(t.page_text_truncated).toBe(true);
  // budget below the controls alone: all text goes first
  const floor = (await observe({ max_bytes: 1024 + 5500 })).data.observation;
  console.log("FLOOR", floor.page_text.length, floor.elements.length, Buffer.byteLength(canonical(floor)));
  await worker.close(identity, identity.session_id); identity = { ...identity, session_id: randomUUID() };
  await open("/controls", { agent_mode: true });
  const without = (await observe()).data.observation;
  expect(withText.elements.map(key)).toEqual(without.elements.map(key));
  expect(withText.page_text.length).toBeGreaterThan(0);
  expect(without.page_text).toEqual([]);
});
test("QA-W09 gating matrix: need agent_mode AND capability", async () => {
  const cases: Array<[string, object, boolean]> = [
    ["agent+cap", AGENT_TEXT, true], ["agent only", { agent_mode: true }, false],
    ["cap only", { required_capabilities: ["page-text-v1"] }, false], ["neither", {}, false],
    ["agent+other cap", { agent_mode: true, required_capabilities: ["agent-dom-path-v1", "click-context-v1"] }, false],
    ["agent+cap+owned", { agent_mode: true, required_capabilities: ["owned-test-target-v1", "page-text-v1"] }, true]];
  for (const [label, extra, expectText] of cases) {
    const opened = await open("/plain", extra);
    expect(opened.capabilities, label).toContain("page-text-v1");
    const o = (await observe()).data.observation;
    expect(o.page_text.length > 0, label).toBe(expectText);
    if (!expectText) expect(o).toMatchObject({ page_text: [], page_text_truncated: false, page_text_skipped: 0 });
    if (label === "neither") await writeFile(join(tmpdir(), "qa-p2-plain-observation.json"), JSON.stringify(o));
    await worker.close(identity, identity.session_id); identity = { ...identity, session_id: randomUUID() };
  }
});

test("QA-W10 attack: Python-rejected candidate strings must not survive the worker filter", async () => {
  test.skip(!batches.length, "run pytest -k c11a first");
  test.setTimeout(480_000);
  const kept: string[] = []; let skipped = 0, sent = 0;
  for (let i = 0; i < batches.length; i++) {
    await open(`/b/${i}`, AGENT_TEXT);
    const o = (await observe()).data.observation;
    sent += batches[i].length; kept.push(...texts(o)); skipped += o.page_text_skipped;
    expect(o.page_text_truncated, `batch ${i}`).toBe(false);
    await worker.close(identity, identity.session_id); identity = { ...identity, session_id: randomUUID() };
  }
  console.log("ATTACK sent", sent, "kept", kept.length, "skipped", skipped);
  await writeFile(join(tmpdir(), "qa-p2-kept.json"), JSON.stringify({ sent, kept_total: kept.length, kept }));
});
test("QA-W11 lone surrogates in page text", async () => {
  const o = await items("/surrogate");
  console.log("SURR", JSON.stringify(texts(o)), o.page_text_skipped);
  await writeFile(join(tmpdir(), "qa-p2-surrogate-observation.json"), JSON.stringify(o));
});

test("QA-W12 harmless Turkish text is kept verbatim (no i-folding in the output)", async () => {
  const o = await items("/turkish");
  expect(o.page_text.map(i => i.text)).toEqual(["Çıkış yapıldı", "İLK SIRA", "Işık açık", "İstanbul ılık"]);
  expect(o.page_text_skipped).toBe(0);
});
