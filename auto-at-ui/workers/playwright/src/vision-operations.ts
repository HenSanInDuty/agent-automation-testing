import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import { chromium, type Browser, type BrowserContext, type Page } from "@playwright/test";
import { allowedOrigin, canonical, digest, requireVision, validateVision, VisionWorkerError,
  type VisualWorkerIdentity, type VisualWorkerOpen, type VisualWorkerPrepare, type VisualWorkerExecute,
  type VisualWorkerAck, type VisualOperation, type VisualOperationFrame, type VisualLocatorEvidence,
  type VisualCheckpoint, type VisualWorkerOperationResult, type VisualExternalOrigin, type VisualExecutedClick } from "./vision-contract.js";
import { groundLocator, type GroundedLocator } from "./vision-locators.js";
import { observeDom, resolveDomTarget, type DomSnapshot } from "./vision-dom.js";
import type { VisualWorkerObserveDom, VisualWorkerDomObservation } from "./vision-contract.js";
import { captureVisionScreen } from "./vision-screen.js";
import { checkpointMetadata, equivalentState, inspectState, settleState, type RuntimeState } from "./vision-checkpoints.js";

export type OperationResult = VisualWorkerOperationResult;
type OperationRuntime = {
  result: OperationResult; payloadHash: string; prepare: VisualWorkerPrepare | null;
  before: RuntimeState | null; grounded?: GroundedLocator; page: Page;
  paths: Map<string, string>; replayable: boolean;
  confirmedClick?: VisualExecutedClick;
};
type CheckpointRuntime = { metadata: VisualCheckpoint; state: RuntimeState };
type Session = {
  request: VisualWorkerOpen; browser: Browser; context: BrowserContext; page: Page;
  pages: Map<Page, string>; parents: Map<Page, Page>; deadline: number;
  timer: ReturnType<typeof setTimeout>; expired: boolean; busy: boolean;
  operations: Map<string, OperationRuntime>; pending: string | null;
  checkpoints: Map<string, CheckpointRuntime>; ancestry: string[];
  exploredStates: number;
  state: RuntimeState; policyFailure: string | null; activeOperation: string | null;
  preview?: { at: number; image: Promise<Buffer> };
  externalOrigins: Map<string, VisualExternalOrigin>; originsTruncated: boolean;
  domSnapshots: Map<string, DomSnapshot>;
};

export class VisualOperationWorker {
  private sessions = new Map<string, Session>();
  private opening = new Set<string>();
  private closed = new Set<string>();
  private readonly artifactRoot: string;
  private readonly launch: typeof chromium.launch;
  constructor(artifactRoot: string, launch: typeof chromium.launch = (options) => chromium.launch(options)) {
    this.artifactRoot = artifactRoot; this.launch = launch;
  }
  hasSession(id: string): boolean { return this.sessions.has(id) || this.opening.has(id) || this.closed.has(id); }

  private identity(value: unknown, id: string): Session {
    const identity = validateVision<VisualWorkerIdentity>("VisualWorkerIdentity", value);
    const session = this.sessions.get(id);
    requireVision(session, "session_unavailable");
    requireVision(identity.session_id === id && identity.tenant_id === session.request.tenant_id &&
      identity.project_id === session.request.project_id, "scope_mismatch");
    // A new lease cannot inherit old in-memory browser side effects. The control
    // plane must reconcile the previous lease or finish it as unknown.
    requireVision(identity.fencing_token === session.request.fencing_token, "stale_fencing_token");
    return session;
  }
  private scope(value: VisualWorkerIdentity): VisualWorkerIdentity {
    return { contract_version: "v4", tenant_id: value.tenant_id, project_id: value.project_id,
      session_id: value.session_id, fencing_token: value.fencing_token };
  }
  private async serialized<T>(session: Session, action: () => Promise<T>, allowExpired = false): Promise<T> {
    requireVision(!session.busy, "session_busy");
    if (!allowExpired) requireVision(!session.expired && Date.now() < session.deadline, "session_timeout");
    session.busy = true;
    try { return await action(); } finally { session.busy = false; }
  }
  private timeout(session: Session): number {
    requireVision(!session.expired && Date.now() < session.deadline, "session_timeout");
    return Math.max(1, Math.min(3000, session.deadline - Date.now()));
  }
  private pageId(session: Session, page: Page): string {
    let id = session.pages.get(page);
    if (!id) { id = randomUUID(); session.pages.set(page, id); }
    return id;
  }
  private async expire(session: Session): Promise<void> {
    session.expired = true;
    for (const runtime of session.operations.values()) {
      if (["prepared", "executing"].includes(runtime.result.operation.status)) {
        this.finalize(runtime, runtime.result.operation.status === "executing" ? "unknown" : "rejected", "session_timeout");
      }
      runtime.prepare = null; runtime.before = null;
      await runtime.grounded?.target?.dispose().catch(() => undefined); runtime.grounded = undefined;
    }
    session.checkpoints.clear(); session.domSnapshots.clear(); session.state.privateForms = "";
    await session.context.close().catch(() => undefined);
    await session.browser.close().catch(() => undefined);
  }

  async open(value: unknown): Promise<{ session_id: string; contract_version: "v4"; state_fingerprint: string; operation_budget: number; capabilities: string[] }> {
    const request = validateVision<VisualWorkerOpen>("VisualWorkerOpen", value);
    requireVision(!this.hasSession(request.session_id), "session_already_open");
    const deadline = Date.parse(request.deadline);
    requireVision(deadline > Date.now() && deadline <= Date.now() + request.max_session_seconds * 1000, "invalid_deadline");
    requireVision(allowedOrigin(request.target_url, ["*"]), "invalid_target_url");
    this.opening.add(request.session_id);
    let browser: Browser | undefined;
    try {
      browser = await this.launch({ headless: true, timeout: Math.min(30_000, deadline - Date.now()) });
      const context = await browser.newContext({ viewport: { width: 1280, height: 720 }, acceptDownloads: false, serviceWorkers: "block" });
      let session: Session | undefined;
      await context.route("**/*", async (route) => {
        const request = route.request();
        if (session) {
          let kind: VisualExternalOrigin["request_kind"] = "resource";
          if (request.isNavigationRequest()) {
            // The first popup request can arrive before Playwright creates its frame.
            try { kind = request.frame().page() !== session.page ? "popup" : "navigation"; }
            catch { kind = "popup"; }
          }
          this.observeOrigin(session, request.url(), kind);
        }
        await route.continue();
      });
      await context.routeWebSocket("**/*", (socket) => {
        const httpUrl = socket.url().replace(/^ws:/, "http:").replace(/^wss:/, "https:");
        if (session) this.observeOrigin(session, httpUrl, "websocket");
        socket.connectToServer();
      });
      context.on("page", (page) => {
        page.on("dialog", (dialog) => { if (session) session.policyFailure = "dialog_unsupported"; void dialog.dismiss().catch(() => undefined); });
        page.on("download", (download) => { if (session) session.policyFailure = "download_unsupported"; void download.cancel().catch(() => undefined); });
        if (session) {
          this.pageId(session, page);
          // A page created outside an executing primitive cannot silently become
          // the source page for a future proposal.
          if (!session.activeOperation) session.policyFailure = "unattributed_popup";
        }
      });
      const page = await context.newPage();
      const state = await inspectState(page);
      session = { request, browser, context, page, pages: new Map(), parents: new Map(), deadline,
        timer: setTimeout(() => undefined, 0), expired: false, busy: false, operations: new Map(),
        pending: null, checkpoints: new Map(), ancestry: [], exploredStates: 0, state, policyFailure: null, activeOperation: null,
        externalOrigins: new Map(), originsTruncated: false, domSnapshots: new Map() };
      const opened = session;
      clearTimeout(opened.timer);
      opened.timer = setTimeout(() => { void this.expire(opened); }, Math.max(1, deadline - Date.now()));
      opened.timer.unref();
      this.pageId(opened, page);
      this.sessions.set(request.session_id, opened);
      return { session_id: request.session_id, contract_version: "v4", state_fingerprint: state.fingerprint,
        operation_budget: this.budget(opened), capabilities: ["dom-observation-v1"] };
    } catch (error) { await browser?.close(); throw error; }
    finally { this.opening.delete(request.session_id); }
  }
  private budget(session: Session): number { return 1 + session.request.max_states * (2 * session.request.max_hops + 3); }
  private observeOrigin(session: Session, url: string, kind: VisualExternalOrigin["request_kind"]): void {
    let parsed: URL;
    try { parsed = new URL(url); } catch { return; }
    if (!["http:", "https:"].includes(parsed.protocol) || parsed.origin === new URL(session.request.target_url).origin) return;
    const key = `${kind}:${parsed.origin}`;
    if (session.externalOrigins.has(key)) return;
    if (session.externalOrigins.size >= 100 || parsed.origin.length > 500) { session.originsTruncated = true; return; }
    session.externalOrigins.set(key, { origin: parsed.origin, request_kind: kind, observed_at: new Date().toISOString() });
  }
  origins(value: unknown, id: string) {
    const session = this.identity(value, id);
    return validateVision("VisualWorkerOriginObservations", { ...this.scope(session.request),
      items: [...session.externalOrigins.values()], truncated: session.originsTruncated });
  }
  async observeDom(value: unknown): Promise<VisualWorkerDomObservation> {
    const request = validateVision<VisualWorkerObserveDom>("VisualWorkerObserveDom", value);
    const session = this.identity(this.scope(request), request.session_id);
    return this.serialized(session, async () => {
      requireVision(!session.pending, "operation_pending");
      requireVision(!session.policyFailure, session.policyFailure ?? "policy_block");
      requireVision(!session.domSnapshots.has(request.snapshot_id), "snapshot_already_exists");
      requireVision(session.domSnapshots.size < session.request.max_states, "dom_snapshot_limit");
      requireVision(equivalentState(session.state, await inspectState(session.page)), "state_mismatch");
      const snapshot = await observeDom(session.page, request);
      this.timeout(session);
      session.domSnapshots.set(request.snapshot_id, snapshot);
      return validateVision<VisualWorkerDomObservation>("VisualWorkerDomObservation", {
        ...this.scope(request), capability: "dom-observation-v1", data: snapshot.data,
      });
    });
  }
  async screen(value: unknown, id: string): Promise<Buffer> {
    const session = this.identity(value, id);
    const timeout = this.timeout(session);
    // Concurrent viewers share a bounded capture; preview never acquires the action lock.
    if (!session.preview || Date.now() - session.preview.at > 1000) {
      const image = captureVisionScreen(session.page, timeout).then((bytes) => {
        requireVision(bytes.length <= Math.min(session.request.max_screenshot_bytes, 2_000_000), "screenshot_byte_limit");
        return bytes;
      });
      const preview = { at: Number.POSITIVE_INFINITY, image };
      session.preview = preview;
      void image.then(() => { preview.at = Date.now(); }, () => {
        if (session.preview === preview) session.preview = undefined;
      });
    }
    return session.preview.image;
  }
  private directory(session: Session, operationId: string): string {
    const root = resolve(this.artifactRoot, "vision-v4");
    const directory = resolve(root, session.request.session_id, operationId);
    requireVision(directory.startsWith(root + sep), "invalid_artifact_path");
    return directory;
  }
  private async capture(session: Session, runtime: OperationRuntime, role: "before" | "after", page: Page, stable = false): Promise<RuntimeState | null> {
    const timeout = this.timeout(session);
    // Successful after-captures may need another sample after late hydration.
    // Share one navigation-sized budget across retries, always within the session.
    const deadline = Math.min(session.deadline, Date.now() + (stable ? 10_000 : timeout));
    let bytes: Buffer, observed: RuntimeState | null = null;
    for (;;) {
      const before = stable ? await inspectState(page) : null;
      requireVision(Date.now() < deadline, "capture_failed");
      bytes = await captureVisionScreen(page, deadline - Date.now());
      if (!before) break;
      observed = await inspectState(page);
      // Hydration may finish between settle and capture. Publish only an image
      // bracketed by matching states; retries are read-only and share one timeout.
      if (equivalentState(before, observed)) break;
    }
    requireVision(bytes.length <= session.request.max_screenshot_bytes, "screenshot_byte_limit");
    const directory = this.directory(session, runtime.result.operation.id);
    await mkdir(directory, { recursive: true });
    const path = resolve(directory, `${role}.png`);
    await writeFile(path, bytes, { flag: "wx" });
    requireVision(digest(await readFile(path)) === digest(bytes), "capture_verification_failed");
    requireVision(!session.expired && Date.now() < session.deadline, "session_timeout");
    const frame = validateVision<VisualOperationFrame>("VisualOperationFrame", {
      id: randomUUID(), tenant_id: session.request.tenant_id, project_id: session.request.project_id,
      session_id: session.request.session_id, operation_id: runtime.result.operation.id, role,
      checksum: digest(bytes), byte_count: bytes.length, content_type: "image/png", captured_at: new Date().toISOString(),
    });
    runtime.result.frames.push(frame); runtime.paths.set(frame.id, path);
    runtime.result.operation[`actual_${role}_frame_id`] = frame.id;
    runtime.result.operation[`${role}_page_id`] = this.pageId(session, page);
    return observed;
  }
  private finalize(runtime: OperationRuntime, status: "completed" | "failed" | "rejected" | "unknown", code: string): void {
    if (!["prepared", "executing"].includes(runtime.result.operation.status)) return;
    const op = runtime.result.operation;
    op.status = status; op.outcome_code = code; op.ended_at = new Date().toISOString();
    op.executed_click = ["completed", "failed"].includes(status) ? runtime.confirmedClick ?? null : null;
    if (!op.actual_before_frame_id) op.before_unavailable_reason ??= "capture_failed";
    if (!op.actual_after_frame_id) op.after_unavailable_reason ??= "capture_unavailable";
    runtime.result.duration_ms = Date.parse(op.ended_at) - Date.parse(op.started_at);
    runtime.result.operation = validateVision("VisualOperation", op);
  }
  private result(runtime: OperationRuntime): OperationResult { return validateVision("VisualWorkerOperationResult", runtime.result); }

  async prepare(value: unknown): Promise<OperationResult> {
    const request = validateVision<VisualWorkerPrepare>("VisualWorkerPrepare", value);
    const session = this.identity(this.scope(request), request.session_id);
    return this.serialized(session, async () => {
      const payloadHash = digest(canonical(request));
      const existing = session.operations.get(request.operation_id);
      if (existing) { requireVision(existing.payloadHash === payloadHash, "operation_payload_conflict"); return this.result(existing); }
      requireVision(!session.pending, "operation_pending");
      requireVision(session.operations.size < this.budget(session), "operation_budget_exhausted");
      const operation = validateVision<VisualOperation>("VisualOperation", {
        id: request.operation_id, tenant_id: request.tenant_id, project_id: request.project_id, session_id: request.session_id,
        sequence: session.operations.size + 1, purpose: request.purpose, action_kind: request.action.kind,
        state_id: request.state_id, proposal_id: request.proposal_id, checkpoint_id: request.restore_checkpoint_id,
        expected_parent_fingerprint: request.expected_state_fingerprint,
        parent_operation_id: request.action.kind === "navigate" ? null : session.ancestry.at(-1) ?? null,
        started_at: new Date().toISOString(), status: "prepared",
      });
      const runtime: OperationRuntime = { payloadHash, prepare: request, before: null, page: session.page, paths: new Map(), replayable: false,
        result: { operation, frames: [], locator: null, prepared_handle: randomUUID(), state_fingerprint: null,
          checkpoint: null, semantic_change: "unavailable", duration_ms: 0, acknowledged: false, replayable: false } };
      session.operations.set(request.operation_id, runtime);
      try {
        if (session.policyFailure) throw new VisionWorkerError(session.policyFailure);
        runtime.before = await inspectState(session.page);
        requireVision(runtime.before.fingerprint === request.expected_state_fingerprint &&
          equivalentState(runtime.before, session.state), "state_mismatch");
        if (request.dom_snapshot_id) {
          const snapshot = session.domSnapshots.get(request.dom_snapshot_id);
          requireVision(snapshot, "unknown_dom_snapshot");
          requireVision(snapshot.data.observation.state_fingerprint === request.expected_state_fingerprint, "stale_dom_snapshot");
          const target = await resolveDomTarget(snapshot, session.page, request.dom_element_id!);
          if (request.expected_locator) requireVision(canonical(request.expected_locator) === canonical(target.binding.descriptor), "dom_descriptor_mismatch");
          // Model coordinates are placeholders for DOM mode; only this fresh binding supplies them.
          request.action.x = target.x; request.action.y = target.y;
          request.expected_locator = target.binding.descriptor;
        }
        if (request.purpose === "explore") requireVision(session.ancestry.length <= session.request.max_hops, "hop_limit");
        if (request.purpose === "explore" || request.purpose === "setup") requireVision(session.exploredStates < session.request.max_states, "state_limit");
        if (request.checkpoint_id) {
          requireVision(!session.checkpoints.has(request.checkpoint_id), "checkpoint_already_exists");
          requireVision(session.checkpoints.size < session.request.max_states, "state_limit");
        }
        if (request.restore_checkpoint_id) requireVision(session.checkpoints.has(request.restore_checkpoint_id), "checkpoint_unavailable");
        if (request.purpose === "replay") {
          const source = session.operations.get(request.replay_operation_id!);
          requireVision(source?.result.operation.status === "completed" && source.replayable && source.prepare, "unsafe_replay");
          requireVision(canonical(source.prepare.action) === canonical(request.action) &&
            canonical(source.result.locator?.descriptor ?? null) === canonical(request.expected_locator), "replay_mismatch");
        }
        if (request.action.kind === "navigate") requireVision(request.purpose === "setup" || request.purpose === "replay", "invalid_navigation_purpose");
        if (["back", "close_popup"].includes(request.action.kind)) requireVision(request.purpose === "restore", "invalid_restore_purpose");
        // Before bytes are staged before metadata can be acknowledged by the caller.
        await this.capture(session, runtime, "before", session.page);
        if (["click", "type"].includes(request.action.kind)) {
          const ground = await groundLocator(session.page, request.action.x!, request.action.y!, request.action.kind === "type", request.expected_locator);
          runtime.grounded = ground;
          const { locator: _locator, target: _target, ...evidence } = ground;
          runtime.result.locator = validateVision<VisualLocatorEvidence>("VisualLocatorEvidence", {
            ...evidence, id: randomUUID(), tenant_id: request.tenant_id, project_id: request.project_id,
            session_id: request.session_id, operation_id: request.operation_id, state_id: request.state_id,
            proposal_id: request.proposal_id, originating_frame_id: operation.actual_before_frame_id,
            model_confidence: request.model_confidence,
          });
          operation.locator_id = runtime.result.locator.id;
          requireVision(ground.status === "verified", ground.reason_code ?? "locator_unresolved");
          if (request.action.kind === "click") runtime.replayable = await ground.target!.evaluate((el) => el.tagName === "A" &&
            !!el.getAttribute("href") && !el.hasAttribute("download") && !el.hasAttribute("onclick"));
        }
        requireVision(equivalentState(runtime.before, await inspectState(session.page)), "state_changed_during_prepare");
        runtime.result.state_fingerprint = runtime.before.fingerprint;
        session.pending = request.operation_id;
      } catch (error) {
        this.finalize(runtime, "rejected", error instanceof VisionWorkerError ? error.code : "prepare_failed");
        // A rejected proposal is recorded without inventing a physical action.
        runtime.result.operation.after_unavailable_reason = "action_not_executed";
        await runtime.grounded?.target?.dispose().catch(() => undefined); runtime.grounded = undefined;
      }
      return this.result(runtime);
    });
  }

  async execute(value: unknown): Promise<OperationResult> {
    const request = validateVision<VisualWorkerExecute>("VisualWorkerExecute", value);
    const session = this.identity(this.scope(request), request.session_id);
    return this.serialized(session, async () => {
      const runtime = session.operations.get(request.operation_id);
      requireVision(runtime, "operation_unavailable");
      const beforeFrame = runtime.result.frames.find((frame) => frame.role === "before");
      requireVision(request.prepared_handle === runtime.result.prepared_handle && beforeFrame &&
        request.before_frame_id === beforeFrame.id && request.before_checksum === beforeFrame.checksum, "before_ack_mismatch");
      if (runtime.result.operation.status !== "prepared") return this.result(runtime);
      requireVision(!session.expired && Date.now() < session.deadline, "session_timeout");
      requireVision(session.pending === request.operation_id && runtime.prepare && runtime.before, "operation_not_prepared");
      const command = runtime.prepare, action = command.action;
      let status: "completed" | "rejected" | "failed" | "unknown" = "rejected", code = "state_mismatch";
      let afterPage = runtime.page;
      const initialPages = new Set(session.context.pages());
      let pageCreated: (() => void) | undefined;
      const popupReady = new Promise<void>((resolve) => { pageCreated = resolve; });
      const onPage = () => pageCreated?.();
      session.context.on("page", onPage);
      try {
        requireVision(!session.policyFailure, session.policyFailure ?? "origin_denied");
        requireVision(equivalentState(runtime.before, await inspectState(runtime.page)), "state_mismatch");
        if (runtime.grounded) {
          const fresh = await groundLocator(runtime.page, action.x!, action.y!, action.kind === "type", runtime.grounded.descriptor);
          const sameTarget = fresh.target && runtime.grounded.target && await fresh.target.evaluate((el, old) => el === old, runtime.grounded.target).catch(() => false);
          await fresh.target?.dispose();
          requireVision(fresh.status === "verified" && sameTarget, "stale_locator");
        }
        runtime.result.operation.status = "executing";
        if (command.purpose === "explore" || command.purpose === "setup") session.exploredStates++;
        session.activeOperation = request.operation_id;
        status = "unknown"; code = "action_outcome_unknown";
        const timeout = this.timeout(session);
        if (action.kind === "navigate") await runtime.page.goto(session.request.target_url, { waitUntil: "domcontentloaded", timeout });
        else if (action.kind === "back") {
          await runtime.page.goBack({ waitUntil: "domcontentloaded", timeout });
        } else if (action.kind === "close_popup") {
          const parent = session.parents.get(runtime.page);
          requireVision(parent && !parent.isClosed(), "popup_parent_unavailable");
          await runtime.page.close(); afterPage = parent;
        } else if (action.kind === "click") {
          const box = await runtime.grounded!.locator!.boundingBox(); requireVision(box, "stale_locator");
          // Optional evidence must not affect dispatch. Playwright 1.50 adds the
          // border width to position (padding-box relative); preserve that input.
          const viewport = runtime.page.viewportSize();
          const geometry = await runtime.grounded!.target!.evaluate((el) => {
            const view = el.ownerDocument.defaultView!;
            for (let node: Element | null = el; node;) {
              const style = view.getComputedStyle(node);
              if (style.transform !== "none" || (style.zoom && style.zoom !== "1" && style.zoom !== "normal")) return null;
              node = node.parentElement ?? (node.getRootNode() instanceof ShadowRoot ? (node.getRootNode() as ShadowRoot).host : null);
            }
            const style = view.getComputedStyle(el);
            return { left: parseFloat(style.borderLeftWidth) || 0, top: parseFloat(style.borderTopWidth) || 0 };
          }).catch(() => null);
          const groundedBox = runtime.grounded!.bounding_box;
          const point = geometry ? {
            x: Math.trunc((action.x! * 1279 + geometry.left) * 100) / 100,
            y: Math.trunc((action.y! * 719 + geometry.top) * 100) / 100,
          } : null;
          const canRecord = viewport?.width === 1280 && viewport.height === 720 && point &&
            point.x >= 0 && point.x <= 1279 && point.y >= 0 && point.y <= 719 &&
            box.x >= 0 && box.y >= 0 && box.x + box.width <= 1280 && box.y + box.height <= 720 &&
            !runtime.grounded!.descriptor?.scope.some((scope) => scope.kind === "iframe") &&
            groundedBox && Math.abs(groundedBox.width * 1280 - box.width) < 1 &&
            Math.abs(groundedBox.height * 720 - box.height) < 1;
          await runtime.grounded!.locator!.click({ timeout, position: {
            x: action.x! * 1279 - box.x, y: action.y! * 719 - box.y } });
          if (canRecord) runtime.confirmedClick = {
            x: point.x / 1279, y: point.y / 719, viewport_width: 1280, viewport_height: 720,
            before_frame_id: beforeFrame.id, confirmed_at: new Date().toISOString(),
          };
        } else if (action.kind === "type") {
          // Preserve append semantics; do not persist text in evidence or fill/clear.
          await runtime.grounded!.locator!.press("ControlOrMeta+End", { timeout });
          await runtime.grounded!.locator!.pressSequentially(action.text!, { timeout });
        } else if (action.kind === "scroll") await runtime.page.mouse.wheel(0, action.delta_y!);
        else { requireVision(action.duration_ms! < session.deadline - Date.now(), "session_timeout"); await runtime.page.waitForTimeout(action.duration_ms!); }
        status = "completed"; code = "observed";
        if (action.kind === "click") {
          // Playwright can resolve click before the popup page event is delivered.
          // The listener was armed before dispatch and remains armed through settle.
          let timer: ReturnType<typeof setTimeout> | undefined;
          await Promise.race([popupReady, new Promise<void>((resolve) => {
            timer = setTimeout(resolve, Math.min(500, Math.max(1, session.deadline - Date.now())));
          })]);
          clearTimeout(timer);
        }
        const popups = session.context.pages().filter((page) => !initialPages.has(page));
        requireVision(popups.length <= 1, "multiple_popups_unsupported");
        if (popups[0]) {
          afterPage = popups[0]; session.parents.set(afterPage, runtime.page);
          await afterPage.waitForLoadState("domcontentloaded", { timeout: this.timeout(session) }).catch(() => undefined);
        }
        this.observeOrigin(session, afterPage.url(), afterPage === runtime.page ? "navigation" : "popup");
        if (session.policyFailure) throw new VisionWorkerError(session.policyFailure);
        // DOMContentLoaded can precede hydration and carousel initialization by
        // several seconds. Allow navigation to settle without relaxing state
        // equality or exceeding the session deadline; local actions stay short.
        const navigated = ["navigate", "back", "close_popup"].includes(action.kind) ||
          afterPage !== runtime.page || runtime.before.url_fingerprint !== digest(afterPage.url());
        const settleTimeout = navigated ? 10_000 : 1500;
        const settled = await settleState(afterPage, Math.min(session.deadline, Date.now() + settleTimeout));
        if (!settled.settled) { status = "failed"; code = "settle_timeout"; }
        session.state = settled.state; runtime.result.state_fingerprint = settled.state.fingerprint;
        runtime.result.semantic_change = runtime.before.semantic_fingerprint === settled.state.semantic_fingerprint ? "unchanged" : "changed";
        runtime.result.operation.url_change = runtime.before.url_fingerprint === settled.state.url_fingerprint ? "unchanged" : "changed";
        if (!command.restore_checkpoint_id && status === "completed") {
          if (action.kind === "navigate") session.ancestry = [request.operation_id];
          else if (command.purpose === "explore" || command.purpose === "replay") session.ancestry.push(request.operation_id);
        }
        runtime.replayable ||= ["navigate", "scroll", "wait"].includes(action.kind);
        runtime.result.replayable = runtime.replayable && status === "completed";
      } catch (error) {
        code = error instanceof VisionWorkerError ? error.code : "action_outcome_unknown";
        if (status === "completed") status = "failed";
      } finally {
        session.context.off("page", onPage);
        session.activeOperation = null; session.pending = null; session.page = afterPage;
        let captured: RuntimeState | null = null;
        try {
          // Failed/unknown actions retain diagnostic pixels even when the page
          // never settles; only a successful action can create a checkpoint.
          captured = await this.capture(session, runtime, "after", afterPage, status === "completed");
          const before = runtime.result.frames.find((f) => f.role === "before")!;
          const after = runtime.result.frames.find((f) => f.role === "after")!;
          runtime.result.operation.visual_change = before.checksum === after.checksum ? "unchanged" : "changed";
        } catch (error) { runtime.result.operation.after_unavailable_reason = error instanceof VisionWorkerError ? error.code : "capture_failed"; }
        try {
          session.state = captured ?? await inspectState(afterPage); runtime.result.state_fingerprint = session.state.fingerprint;
        } catch { /* browser lost; last known state remains explicitly unavailable */ }
        if (captured) {
          runtime.result.semantic_change = runtime.before.semantic_fingerprint === captured.semantic_fingerprint ? "unchanged" : "changed";
          runtime.result.operation.url_change = runtime.before.url_fingerprint === captured.url_fingerprint ? "unchanged" : "changed";
          if (status === "completed" && command.restore_checkpoint_id) {
            const checkpoint = session.checkpoints.get(command.restore_checkpoint_id)!;
            if (!equivalentState(checkpoint.state, captured)) { status = "failed"; code = "state_restore_failed"; }
            else session.ancestry = [...checkpoint.metadata.ancestor_operation_ids];
          }
          if (status === "completed" && command.checkpoint_id) {
            // Bind the checkpoint to the committed image, not the earlier settle
            // sample. No image means no checkpoint usable by a future proposal.
            const metadata = checkpointMetadata(command.checkpoint_id, command.checkpoint_state_id!, [...session.ancestry], captured);
            session.checkpoints.set(metadata.id, { metadata, state: captured }); runtime.result.checkpoint = metadata;
          }
        }
        if (status === "completed" && command.restore_checkpoint_id && !captured) {
          status = "failed"; code = "state_restore_failed";
        }
        runtime.result.replayable = runtime.replayable && status === "completed";
        if (status === "unknown" || code === "state_restore_failed") session.policyFailure = code;
        this.finalize(runtime, status, code);
        await runtime.grounded?.target?.dispose().catch(() => undefined); runtime.grounded = undefined;
      }
      return this.result(runtime);
    }, true);
  }

  read(identity: unknown, sessionId: string, operationId: string): OperationResult {
    const session = this.identity(identity, sessionId), runtime = session.operations.get(operationId);
    requireVision(runtime, "operation_unavailable"); return this.result(runtime);
  }
  async checkpoint(identity: unknown, sessionId: string, checkpointId: string): Promise<{ checkpoint: VisualCheckpoint; matches_current: boolean }> {
    const session = this.identity(identity, sessionId), checkpoint = session.checkpoints.get(checkpointId);
    requireVision(checkpoint && !session.expired, "checkpoint_unavailable");
    return this.serialized(session, async () => ({ checkpoint: structuredClone(checkpoint.metadata),
      matches_current: equivalentState(checkpoint.state, await inspectState(session.page)) }));
  }
  async frame(identity: unknown, sessionId: string, operationId: string, frameId: string): Promise<Buffer> {
    const session = this.identity(identity, sessionId), runtime = session.operations.get(operationId);
    const path = runtime?.paths.get(frameId), metadata = runtime?.result.frames.find((f) => f.id === frameId);
    requireVision(path && metadata, "frame_unavailable");
    const bytes = await readFile(path); requireVision(bytes.length === metadata.byte_count && digest(bytes) === metadata.checksum, "frame_checksum_mismatch");
    return bytes;
  }
  async acknowledge(value: unknown): Promise<OperationResult> {
    const request = validateVision<VisualWorkerAck>("VisualWorkerAck", value);
    const session = this.identity(this.scope(request), request.session_id);
    return this.serialized(session, async () => {
      const runtime = session.operations.get(request.operation_id); requireVision(runtime, "operation_unavailable");
      requireVision(!["prepared", "executing"].includes(runtime.result.operation.status), "operation_not_final");
      requireVision(canonical([...request.persisted_frame_ids].sort()) === canonical(runtime.result.frames.map((f) => f.id).sort()), "frame_ack_mismatch");
      await rm(this.directory(session, request.operation_id), { recursive: true, force: true });
      runtime.paths.clear(); runtime.result.acknowledged = true;
      // Preserve replay action only in RAM; drop typed input immediately after ACK.
      if (runtime.prepare?.action.kind === "type") runtime.prepare = null;
      runtime.before = null;
      return this.result(runtime);
    }, true);
  }
  async close(identity: unknown, sessionId: string): Promise<void> {
    const session = this.identity(identity, sessionId);
    await this.serialized(session, async () => {
      clearTimeout(session.timer); await this.expire(session); this.sessions.delete(sessionId); this.closed.add(sessionId);
      // Unacknowledged staging remains available to the owning control-plane
      // artifact adapter; close never deletes evidence before durable ACK.
    }, true);
  }
}
