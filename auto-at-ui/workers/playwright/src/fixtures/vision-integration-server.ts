import { createServer } from "node:http";
import { mkdir, mkdtemp, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { chromium } from "@playwright/test";
import { executeRequest, preflightPlaywrightTestSource } from "../execute.js";
import type { AddressInfo } from "node:net";
import { visualHttpHandler } from "../vision-http.js";
import { startVisionTarget } from "./vision-target.js";
import { VisualOperationWorker } from "../vision-operations.js";

const target = await startVisionTarget();
const root = await mkdtemp(join(tmpdir(), "vision-integration-"));
// The unchanged Linux runner resolves its cache under HOME. This owned fixture
// junction lets its child use the installed pinned browser on Windows too.
if (process.platform === "win32") {
  const cache = dirname(dirname(dirname(chromium.executablePath())));
  await mkdir(join(root, ".cache"));
  await symlink(cache, join(root, ".cache", "ms-playwright"), "junction");
  process.env.HOME = root;
}
const handler = visualHttpHandler(root, () => "integration-fixture-only");
// Test-only barrier: hydrate a known popup after its before-frame has been captured.
// The production handler has no endpoint or mutation hook for this.
let closePrepareMutations = 0;
let restorePrepareMutation: 'form' | 'changed' | undefined;
let refreshPrepareMutation = false;
let refreshPage: import('@playwright/test').Page | undefined;
let preflightPage: import('@playwright/test').Page | undefined;
const prototype = VisualOperationWorker.prototype as unknown as {
  capture: (...args: any[]) => Promise<unknown>;
};
const capture = prototype.capture;
prototype.capture = async function (...args) {
  const result = await capture.apply(this, args);
  const [, runtime, role, page] = args;
  if (refreshPrepareMutation && role === 'before' && runtime.prepare?.refresh_observation) {
    refreshPrepareMutation = false; refreshPage = page;
    await page.evaluate(() => document.querySelector('a,button')!.setAttribute('aria-busy', 'true'));
  }
  if (new URL(page.url()).pathname === '/coverage-video-preflight') preflightPage = page;
  if (restorePrepareMutation && role === 'before' && runtime.prepare?.action.kind === 'wait' &&
      runtime.prepare?.purpose === 'restore' && new URL(page.url()).pathname === '/restore-race') {
    const mutation = restorePrepareMutation; restorePrepareMutation = undefined;
    await page.evaluate(async (mutation: string) => {
      await fetch('/restore-race-' + (mutation === 'form' ? 'form' : 'release'));
    }, mutation);
    await page.waitForFunction((mutation: string) => mutation === 'form'
      ? document.querySelector('input')?.value === 'fixture-changed'
      : document.querySelector('#sibling')?.textContent === 'Changed', mutation);
  }
  if (closePrepareMutations > 0 && role === "before" &&
      runtime.prepare?.action.kind === "close_popup" &&
      new URL(page.url()).pathname === "/close-race-child") {
    closePrepareMutations--;
    await page.evaluate(() => {
      const input = document.createElement("input");
      input.type = "hidden"; input.value = "fixture-popup-private";
      document.body.append(input);
    });
  }
  return result;
};
const server = createServer(async (request, response) => {
  if (request.method === 'GET' && request.url === '/fixture-arm-refresh-prepare') {
    refreshPrepareMutation = true; response.writeHead(200).end('armed'); return;
  }
  if (request.method === 'GET' && request.url === '/fixture-reset-refresh-prepare') {
    await refreshPage?.evaluate(() => document.querySelector('a,button')!.removeAttribute('aria-busy'));
    response.writeHead(200).end('reset'); return;
  }
  if (request.method === 'GET' && ['/fixture-arm-restore-prepare/form', '/fixture-arm-restore-prepare/changed'].includes(request.url ?? '')) {
    restorePrepareMutation = request.url!.endsWith('/form') ? 'form' : 'changed';
    response.writeHead(200).end('armed'); return;
  }
  if (request.method === 'GET' && request.url?.startsWith('/fixture-preflight-mutate/')) {
    const kind = request.url.split('/').at(-1);
    if (!preflightPage || !['swap', 'replacement', 'form', 'limit'].includes(kind!)) {
      response.writeHead(400).end(); return;
    }
    await preflightPage.evaluate(kind => {
      const a = document.querySelectorAll('a');
      if (kind === 'form') document.querySelector('input')!.value = 'fixture-private-changed';
      else if (kind === 'replacement' || kind === 'limit') a[0].replaceWith(a[0].cloneNode(true));
      else { const href = a[0].href; a[0].href = a[1].href; a[1].href = href; }
    }, kind);
    response.writeHead(200).end('changed'); return;
  }
  if (request.method === "GET" && request.url === "/fixture-arm-close-prepare") {
    closePrepareMutations = 1;
    response.writeHead(200).end("armed"); return;
  }
  if (request.method === "GET" && request.url === "/fixture-visits") {
    response.writeHead(200, { "content-type": "application/json" })
      .end(JSON.stringify(Object.fromEntries(target.visits)));
    return;
  }
  if (request.url?.startsWith("/visual-explorations")) {
    await handler(request, response);
    return;
  }
  if (request.method !== "POST" || !["/preflight", "/execute"].includes(request.url ?? "")) {
    response.writeHead(404).end();
    return;
  }
  try {
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const chunk of request) {
      const bytes = Buffer.from(chunk);
      size += bytes.length;
      if (size > 500_000) throw new Error("fixture request size");
      chunks.push(bytes);
    }
    const payload: unknown = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const result = request.url === "/preflight"
      ? await preflightPlaywrightTestSource(payload)
      : await executeRequest(payload, root);
    response.writeHead(200, { "content-type": "application/json" }).end(JSON.stringify(result));
  } catch {
    response.writeHead(422).end();
  }
});
await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
process.stdout.write(JSON.stringify({ target: target.origin,
  worker: `http://127.0.0.1:${(server.address() as AddressInfo).port}`, root }) + "\n");
