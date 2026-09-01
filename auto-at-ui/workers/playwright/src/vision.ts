import { createHash, randomUUID } from "node:crypto";
import { mkdir, rm, stat } from "node:fs/promises";
import { join, resolve } from "node:path";
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";

type Action =
  | { kind: "click"; x: number; y: number }
  | { kind: "type"; x: number; y: number; text: string }
  | { kind: "scroll"; delta_y: number }
  | { kind: "wait"; duration_ms: number }
  | { kind: "stop" };

export type VisualRequest = {
  contract_version: "v1"; id: string; target_url: string; allowed_origins: string[];
  max_steps: number; max_screenshot_bytes: number; max_session_seconds: number;
};
export type VisualTreeRequest = Omit<VisualRequest, "contract_version" | "max_steps"> & {
  contract_version: "v2"; node_id: string; max_hops: number; max_states: number; replay_path: unknown[];
};
export type Observation = {
  session_id: string; sequence: number; checksum: string; content_type: "image/png";
  byte_count: number; terminal: boolean;
};
export type TreeObservation = Observation & { node_id: string; hop: number };

type ActiveSession = {
  request: VisualRequest; browser: Browser; context: BrowserContext; page: Page;
  startedAt: number; sequence: number;
};

const sessions = new Map<string, ActiveSession>();

function allowed(url: string, origins: string[]): boolean {
  try { return origins.includes(new URL(url).origin); } catch { return false; }
}

export function visualRequestOf(value: unknown): VisualRequest {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("visual request must be an object");
  const request = value as Record<string, unknown>;
  if (request.contract_version !== "v1" || typeof request.id !== "string" || typeof request.target_url !== "string" ||
    !Array.isArray(request.allowed_origins) || !request.allowed_origins.every((item) => typeof item === "string") ||
    !Number.isInteger(request.max_steps) || !Number.isInteger(request.max_screenshot_bytes) || !Number.isInteger(request.max_session_seconds)) {
    throw new Error("visual request does not satisfy contract v1");
  }
  const result = request as unknown as VisualRequest;
  if (result.max_steps < 1 || result.max_steps > 10 || result.max_screenshot_bytes < 1024 || result.max_session_seconds < 1 ||
    !allowed(result.target_url, result.allowed_origins)) throw new Error("visual request violates worker policy");
  return result;
}

export function actionOf(value: unknown): Action {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("visual action must be an object");
  const action = value as Record<string, unknown>;
  const coordinate = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1;
  if (action.kind === "click" && coordinate(action.x) && coordinate(action.y)) return { kind: "click", x: action.x as number, y: action.y as number };
  if (action.kind === "type" && coordinate(action.x) && coordinate(action.y) && typeof action.text === "string" && action.text.length > 0 && action.text.length <= 1000) return { kind: "type", x: action.x as number, y: action.y as number, text: action.text };
  if (action.kind === "scroll" && typeof action.delta_y === "number" && Number.isInteger(action.delta_y) && Math.abs(action.delta_y) <= 2000) return { kind: "scroll", delta_y: action.delta_y };
  if (action.kind === "wait" && typeof action.duration_ms === "number" && Number.isInteger(action.duration_ms) && action.duration_ms >= 100 && action.duration_ms <= 10000) return { kind: "wait", duration_ms: action.duration_ms };
  if (action.kind === "stop") return { kind: "stop" };
  throw new Error("visual action is not allowlisted");
}

export function visualTreeRequestOf(value: unknown): VisualTreeRequest {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("visual tree request must be an object");
  const request = value as Record<string, unknown>;
  if (request.contract_version !== "v2" || typeof request.id !== "string" || typeof request.node_id !== "string" ||
    !/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(request.node_id) ||
    typeof request.target_url !== "string" || !Array.isArray(request.allowed_origins) || !request.allowed_origins.every((item) => typeof item === "string") ||
    !Number.isInteger(request.max_hops) || !Number.isInteger(request.max_states) || !Number.isInteger(request.max_screenshot_bytes) ||
    !Number.isInteger(request.max_session_seconds) || !Array.isArray(request.replay_path)) throw new Error("visual tree request does not satisfy contract v2");
  if ((request.max_hops as number) < 1 || (request.max_hops as number) > 10 || (request.max_states as number) < 1 || (request.max_states as number) > 200 ||
    (request.max_screenshot_bytes as number) < 1024 || (request.max_session_seconds as number) < 1 ||
    request.replay_path.length > (request.max_hops as number) || !allowed(request.target_url, request.allowed_origins)) throw new Error("visual tree request violates worker policy");
  request.replay_path.forEach(actionOf);
  return request as unknown as VisualTreeRequest;
}

async function screenshot(session: ActiveSession, root: string, terminal: boolean): Promise<Observation> {
  const sequence = ++session.sequence;
  const directory = resolve(root, "vision", session.request.id);
  await mkdir(directory, { recursive: true });
  const path = join(directory, `${sequence}.png`);
  await session.page.screenshot({ path, type: "png" });
  const bytes = await stat(path);
  if (bytes.size > session.request.max_screenshot_bytes) throw new Error("visual screenshot exceeds byte cap");
  const content = await import("node:fs/promises").then(({ readFile }) => readFile(path));
  return { session_id: session.request.id, sequence, checksum: createHash("sha256").update(content).digest("hex"), content_type: "image/png", byte_count: bytes.size, terminal };
}

async function applyAction(page: Page, action: Action): Promise<void> {
  if (action.kind === "stop") throw new Error("stop cannot be replayed as a browser action");
  if (action.kind === "click" || action.kind === "type") {
    const size = page.viewportSize();
    if (!size) throw new Error("visual viewport is unavailable");
    const x = Math.round(action.x * (size.width - 1));
    const y = Math.round(action.y * (size.height - 1));
    await page.mouse.click(x, y);
    if (action.kind === "type") await page.keyboard.type(action.text);
    return;
  }
  if (action.kind === "scroll") { await page.mouse.wheel(0, action.delta_y); return; }
  await page.waitForTimeout(action.duration_ms);
}

/**
 * Materializes one BFS node from its immutable ancestor-action checkpoint.
 * A fresh browser context per node makes siblings independent: exploring one
 * candidate cannot leak cookies, history, or page state into another branch.
 */
export async function observeVisualTreeState(value: unknown, artifactRoot: string): Promise<TreeObservation> {
  const request = visualTreeRequestOf(value);
  const path = request.replay_path.map(actionOf);
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, acceptDownloads: false, serviceWorkers: "block" });
  const page = await context.newPage();
  try {
    await page.route("**/*", (route) => allowed(route.request().url(), request.allowed_origins) ? route.continue() : route.abort());
    await page.goto(request.target_url, { waitUntil: "domcontentloaded", timeout: request.max_session_seconds * 1000 });
    for (const action of path) {
      await applyAction(page, action);
      if (!allowed(page.url(), request.allowed_origins)) throw new Error("replayed action left the allowed origins");
    }
    const directory = resolve(artifactRoot, "vision", request.id);
    await mkdir(directory, { recursive: true });
    const screenshotPath = join(directory, `tree-${request.node_id}.png`);
    await page.screenshot({ path: screenshotPath, type: "png" });
    const bytes = await stat(screenshotPath);
    if (bytes.size > request.max_screenshot_bytes) throw new Error("visual screenshot exceeds byte cap");
    const content = await import("node:fs/promises").then(({ readFile }) => readFile(screenshotPath));
    return { session_id: request.id, sequence: path.length + 1, node_id: request.node_id, hop: path.length,
      checksum: createHash("sha256").update(content).digest("hex"), content_type: "image/png", byte_count: bytes.size, terminal: path.length >= request.max_hops };
  } finally {
    await context.clearCookies();
    await context.close();
    await browser.close();
  }
}

export async function openVisualSession(value: unknown, artifactRoot: string): Promise<Observation> {
  const request = visualRequestOf(value);
  if (sessions.has(request.id)) throw new Error("visual session is already active");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, acceptDownloads: false, serviceWorkers: "block" });
  const page = await context.newPage();
  await page.route("**/*", (route) => allowed(route.request().url(), request.allowed_origins) ? route.continue() : route.abort());
  const session = { request, browser, context, page, startedAt: Date.now(), sequence: 0 };
  sessions.set(request.id, session);
  try { await page.goto(request.target_url, { waitUntil: "domcontentloaded", timeout: request.max_session_seconds * 1000 }); return await screenshot(session, artifactRoot, false); }
  catch (error) { await closeVisualSession(request.id, artifactRoot); throw error; }
}

export async function applyVisualAction(sessionId: string, value: unknown, artifactRoot: string): Promise<Observation> {
  const session = sessions.get(sessionId); if (!session) throw new Error("visual session is unavailable");
  const action = actionOf(value);
  const expired = Date.now() - session.startedAt > session.request.max_session_seconds * 1000;
  const terminal = expired || action.kind === "stop" || session.sequence >= session.request.max_steps;
  if (!terminal) {
    await applyAction(session.page, action);
  }
  const observation = await screenshot(session, artifactRoot, terminal);
  if (terminal) await closeVisualSession(sessionId, artifactRoot, false);
  return observation;
}

export async function closeVisualSession(sessionId: string, artifactRoot: string, removeArtifacts = true): Promise<void> {
  const session = sessions.get(sessionId); sessions.delete(sessionId);
  await session?.context.clearCookies(); await session?.context.close(); await session?.browser.close();
  // The control plane consumes verified bytes before close; do not retain raw screenshots.
  if (removeArtifacts) await rm(join(resolve(artifactRoot), "vision", sessionId), { recursive: true, force: true });
}

export const newVisualSessionId = (): string => randomUUID();
