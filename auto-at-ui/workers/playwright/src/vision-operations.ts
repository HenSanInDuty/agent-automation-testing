import { visualButtonSemantics } from "./vision-button-semantics.js";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { resolve, sep } from "node:path";
import { chromium, type Browser, type BrowserContext, type Frame, type Page, type Request } from "@playwright/test";
import { allowedOrigin, canonical, digest, requireVision, validateVision, VisionWorkerError,
  type VisualWorkerIdentity, type VisualWorkerOpen, type VisualWorkerPrepare, type VisualWorkerExecute,
  type VisualWorkerAck, type VisualOperation, type VisualOperationFrame, type VisualLocatorEvidence,
  type VisualCheckpoint, type VisualWorkerOperationResult, type VisualExternalOrigin, type VisualExecutedClick } from "./vision-contract.js";
import { groundLocator, type GroundedLocator } from "./vision-locators.js";
import { observeDom, resolveDomTarget, verifySnapshotTarget, type DomSnapshot } from "./vision-dom.js";
import { revalidateDom, contextSignature, targetSignature, targetActionSignature } from "./vision-revalidation.js";
import type { VisualWorkerCheckTarget, VisualWorkerTargetCheck } from "./vision-contract.js";
import type { VisualWorkerObserveDom, VisualWorkerDomObservation } from "./vision-contract.js";
import { captureVisionScreen } from "./vision-screen.js";
import { observeClick } from "./vision-click-evidence.js";
import { logVisionEvent, logVisionFailure, visionErrorType, visionLogScope } from "./vision-observability.js";
import { checkpointMetadata, equivalentState, inspectState, logStateMismatch, setInteractionScope, settleState, type RuntimeState } from "./vision-checkpoints.js";
import { captureHistory, validateHistory, returnToHistory, type HistoryCheckpoint } from "./vision-history.js";

export type OperationResult = VisualWorkerOperationResult;
type OutcomeSample = { page: Page; state: RuntimeState; bytes: Buffer; capturedAt: string };
type OperationRuntime = {
  result: OperationResult; payloadHash: string; prepare: VisualWorkerPrepare | null; submittedAction: string;
  before: RuntimeState | null; grounded?: GroundedLocator; page: Page;
  paths: Map<string, string>; replayable: boolean;
  confirmedClick?: VisualExecutedClick;
  historyFromEntryId?: number;
};
type CheckpointRuntime = { metadata: VisualCheckpoint; state: RuntimeState; url: string; navigable: boolean; history: HistoryCheckpoint | null };
type Session = {
  request: VisualWorkerOpen; browser: Browser; context: BrowserContext; page: Page;
  pages: Map<Page, string>; parents: Map<Page, Page>; deadline: number;
  timer: ReturnType<typeof setTimeout>; expired: boolean; busy: boolean;
  operations: Map<string, OperationRuntime>; pending: string | null;
  checkpoints: Map<string, CheckpointRuntime>; ancestry: string[];
  exploredStates: number;
  state: RuntimeState; policyFailure: string | null; activeOperation: string | null;
  downloadOwner?: (page: Page, url: string) => boolean;
  preview?: { at: number; image: Promise<Buffer> };
  externalOrigins: Map<string, VisualExternalOrigin>; originsTruncated: boolean;
  domSnapshots: Map<string, DomSnapshot>;
  navigationMethods: WeakMap<Page, string>;
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
    if (!allowExpired) requireVision(!session.expired && Date.now() < session.deadline, this.timeoutCode(session));
    session.busy = true;
    try { return await action(); } finally { session.busy = false; this.idleLease(session); }
  }
  private timeoutCode(session: Session): string { return session.request.step_timeout_seconds == null ? "session_timeout" : "step_timeout"; }
  private idleLease(session: Session): void {
    if (session.request.step_timeout_seconds == null || session.expired || session.pending) return;
    // An abandoned browser is reclaimed, but active steps have no session-wide
    // clock. Preview polling never renews this controller-owned inactivity lease.
    session.deadline = Number.POSITIVE_INFINITY;
    clearTimeout(session.timer);
    session.timer = setTimeout(() => { void this.expire(session, "worker_idle_timeout"); },
      Math.max(30_000, (2 * session.request.step_timeout_seconds + 10) * 1000));
    session.timer.unref();
  }
  private timeout(session: Session): number {
    requireVision(!session.expired && Date.now() < session.deadline, this.timeoutCode(session));
    return Math.max(1, Math.min(session.request.step_timeout_seconds == null ? 3000 :
      session.request.step_timeout_seconds * 1000, session.deadline - Date.now()));
  }
  private pageId(session: Session, page: Page): string {
    let id = session.pages.get(page);
    if (!id) { id = randomUUID(); session.pages.set(page, id); }
    return id;
  }
  private async expire(session: Session, code = this.timeoutCode(session)): Promise<void> {
    session.expired = true;
    for (const runtime of session.operations.values()) {
      if (["prepared", "executing"].includes(runtime.result.operation.status)) {
        this.finalize(runtime, runtime.result.operation.status === "executing" ? "unknown" : "rejected", code);
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
      // Advisory exploration uses the site's accessible reduced-motion variant.
      // Sites that honor it can stop decorative pulses on actionable controls;
      // live geometry, identity and Playwright actionability checks still apply.
      const context = await browser.newContext({ viewport: { width: 1280, height: 720 },
        acceptDownloads: false, serviceWorkers: "block", reducedMotion: "reduce" });
      // Route/page callbacks may run before the initial page has been inspected.
      // eslint-disable-next-line prefer-const
      let session: Session | undefined;
      context.on("request", navigation => {
        if (!session || !navigation.isNavigationRequest()) return;
        try {
          const frame = navigation.frame(), page = frame.page();
          if (frame === page.mainFrame()) session.navigationMethods.set(page, navigation.method());
        } catch { /* A popup's first navigation may precede its Page; no GET proof yet. */ }
      });
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
        setInteractionScope(page, request.interaction_scope);
        page.on("dialog", (dialog) => { if (session) session.policyFailure = "dialog_unsupported"; void dialog.dismiss().catch(() => undefined); });
        page.on("download", (download) => {
          if (session && !session.downloadOwner?.(page, download.url())) session.policyFailure = "download_unsupported";
          // Initiation is evidence, never permission to retain a downloaded file.
          void download.cancel().catch(() => undefined);
        });
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
        externalOrigins: new Map(), originsTruncated: false, domSnapshots: new Map(), navigationMethods: new WeakMap() };
      const opened = session;
      clearTimeout(opened.timer);
      opened.timer = setTimeout(() => { void this.expire(opened); }, Math.max(1, deadline - Date.now()));
      opened.timer.unref();
      this.idleLease(opened);
      this.pageId(opened, page);
      this.sessions.set(request.session_id, opened);
      return { session_id: request.session_id, contract_version: "v4", state_fingerprint: state.fingerprint,
        operation_budget: this.budget(opened), capabilities: ["dom-observation-v1", "step-timeout-v1", "button-scope-v1", "anonymous-button-v1", "visual-button-scope-v1", "viewport-context-v1", "target-preflight-v1"] };
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
  async checkTarget(value: unknown): Promise<VisualWorkerTargetCheck> {
    const request = validateVision<VisualWorkerCheckTarget>("VisualWorkerCheckTarget", value);
    const session = this.identity(this.scope(request), request.session_id);
    return this.serialized(session, async () => {
      requireVision(!session.pending, "operation_pending");
      requireVision(!session.policyFailure, session.policyFailure ?? "policy_block");
      this.timeout(session);
      const old = session.domSnapshots.get(request.snapshot_id);
      const checkpoint = session.checkpoints.get(request.checkpoint_id);
      requireVision(old && checkpoint, "stale_dom_snapshot");
      const binding = old.data.bindings.find(item => item.element_id === request.element_id);
      requireVision(binding, "unknown_dom_element");
      requireVision(binding.descriptor.schema_version === 'v3' && binding.descriptor.strategy === 'dom_path', 'unsupported_target');
      // Keep per-node action identity (not deduplicated page identity), while
      // allowing cosmetic animation classes and ancestor whitespace to change.
      const signature = old.actionSignatures?.has(request.element_id) ? targetActionSignature : targetSignature;
      const expectedSignature = old.actionSignatures?.get(request.element_id) ?? old.targetSignatures.get(request.element_id);
      const before = await inspectState(session.page), a = old.state;
      const sameDocument = await old.document.evaluate(el => el.isConnected).catch(() => false);
      let context = old.page === session.page && a.url_fingerprint === before.url_fingerprint &&
        a.scroll_x === before.scroll_x && a.scroll_y === before.scroll_y &&
        a.form_presence_fingerprint === before.form_presence_fingerprint && a.privateForms === before.privateForms &&
        old.contextSignature === await contextSignature(session.page) &&
          (request.allow_restored_document ? equivalentState(checkpoint.state, before) : sameDocument);
      let matches = false;
      if (context && equivalentState(a, before)) {
        const target = await session.page.locator(binding.descriptor.value).elementHandle();
        try {
          const original = old.anonymousTargets.get(request.element_id);
            if (target && (request.allow_restored_document || original && await target.evaluate(
            (node, prior) => node === prior && node.isConnected, original).catch(() => false)) &&
              await signature(target) === expectedSignature) {
            await target.waitForElementState('stable', { timeout: Math.min(500, this.timeout(session)) });
            const box = await target.boundingBox(), viewport = session.page.viewportSize();
            if (box && viewport) {
              const grounded = await groundLocator(session.page,
                (box.x + box.width / 2) / (viewport.width - 1),
                (box.y + box.height / 2) / (viewport.height - 1), false, binding.descriptor);
              try {
                matches = grounded.status === 'verified' && !!grounded.target &&
                  await grounded.target.evaluate((node, prior) => node === prior && node.isConnected, target) &&
                  await signature(target) === expectedSignature &&
                  equivalentState(before, await inspectState(session.page));
              } finally { await grounded.target?.dispose(); }
            }
          }
        } catch { matches = false; }
        finally { await target?.dispose(); }
      }
      const after = await inspectState(session.page);
      context = context && before.url_fingerprint === after.url_fingerprint &&
        before.scroll_x === after.scroll_x && before.scroll_y === after.scroll_y &&
        before.form_presence_fingerprint === after.form_presence_fingerprint && before.privateForms === after.privateForms &&
        old.contextSignature === await contextSignature(session.page) &&
        (!sameDocument || await old.document.evaluate(el => el.isConnected).catch(() => false));
      matches = matches && context && equivalentState(before, after);
      this.timeout(session);
      const scope = visionLogScope.getStore();
      logVisionEvent('info', 'vision.target.preflight', 'Approved target checked without dispatch.', scope?.context, {
        ...scope?.fields, session_id: request.session_id, snapshot_id: request.snapshot_id,
        checkpoint_id: request.checkpoint_id, matches_current: matches,
        context_matches: context, same_document: sameDocument,
      });
      return validateVision<VisualWorkerTargetCheck>('VisualWorkerTargetCheck', {
        ...request, matches_current: matches, context_matches: context, same_document: sameDocument,
      });
    });
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
      if (request.revalidate_snapshot_id) {
        const previous = session.domSnapshots.get(request.revalidate_snapshot_id);
        requireVision(previous && (request.revalidate_context_only || request.revalidate_element_ids.length > 0), "stale_dom_snapshot");
        await revalidateDom(previous, snapshot, request.revalidate_element_ids);
        requireVision(equivalentState(snapshot.state, await inspectState(session.page)), "state_changed_during_observation");
      }
      this.timeout(session);
      session.domSnapshots.set(request.snapshot_id, snapshot);
      return validateVision<VisualWorkerDomObservation>("VisualWorkerDomObservation", {
        ...this.scope(request), capability: "dom-observation-v1", data: snapshot.data,
      });
    });
  }
  async screen(value: unknown, id: string): Promise<Buffer> {
    const session = this.identity(value, id);
    const timeout = Math.min(3000, this.timeout(session));
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
  private async sampleClickOutcome(session: Session, page: Page, operationId: string): Promise<OutcomeSample | null> {
    // Observe a settled in-page result while the unchanged popup grace window runs.
    // This is optional evidence only: no persistence, actions or timer manipulation.
    const deadline = Math.min(session.deadline, Date.now() + 500);
    const started = performance.now();
    let stage = "settle", stageStarted = started, outcome = "error", errorType: string | null = null;
    let settleMs = 0, captureMs = 0, verifyMs = 0;
    try {
      const settled = await settleState(page, deadline, 160, false);
      settleMs = Math.round(performance.now() - stageStarted);
      if (!settled.settled || Date.now() >= deadline) { outcome = "settle_deadline"; return null; }
      stage = "capture"; stageStarted = performance.now();
      const bytes = await captureVisionScreen(page, deadline - Date.now(), true);
      captureMs = Math.round(performance.now() - stageStarted);
      const capturedAt = new Date().toISOString();
      stage = "verify"; stageStarted = performance.now();
      const state = await inspectState(page);
      verifyMs = Math.round(performance.now() - stageStarted);
      if (Date.now() >= deadline) { outcome = "verify_deadline"; return null; }
      if (!equivalentState(settled.state, state)) { outcome = "state_changed"; return null; }
      if (bytes.length > session.request.max_screenshot_bytes) { outcome = "byte_limit"; return null; }
      outcome = "sampled";
      return { page, state, bytes, capturedAt };
    } catch (error) {
      errorType = visionErrorType(error);
      return null; // Normal final capture remains authoritative on failure.
    } finally {
      const scope = visionLogScope.getStore();
      logVisionEvent("info", "vision.evidence.sample", "Optional local outcome observation finished.", scope?.context, {
        ...scope?.fields, session_id: session.request.session_id, operation_id: operationId,
        sample_status: outcome, sample_stage: stage, sample_budget_ms: 500,
        duration_ms: Math.round(performance.now() - started), stage_ms: Math.round(performance.now() - stageStarted),
        settle_ms: settleMs, capture_ms: captureMs, verify_ms: verifyMs, error_type: errorType,
      });
    }
  }

  private async capture(session: Session, runtime: OperationRuntime, role: "before" | "after", page: Page, stable = false, sample: OutcomeSample | null = null): Promise<RuntimeState | null> {
    const timeout = this.timeout(session);
    // Successful after-captures may need another sample after late hydration.
    // Share one navigation-sized budget across retries, always within the session.
    const deadline = Math.min(session.deadline, Date.now() + (stable ? 10_000 : timeout));
    const started = Date.now();
    let attempts = 0, mismatches = 0, contextResets = 0, phase = "state_before";
    let bytes: Buffer, observed: RuntimeState | null = null, capturedAt: string | undefined;
    try {
    let reuse = false;
    if (stable && sample?.page === page) {
      try { reuse = equivalentState(sample.state, await inspectState(page)); }
      catch { /* A late navigation/read interruption uses normal final capture. */ }
    }
    if (sample) {
      const scope = visionLogScope.getStore();
      logVisionEvent("info", "vision.evidence.sample_reuse", "Optional local outcome reuse checked.", scope?.context, {
        ...scope?.fields, session_id: session.request.session_id, operation_id: runtime.result.operation.id,
        reused: reuse, sample_age_ms: Math.max(0, Date.now() - Date.parse(sample.capturedAt)),
      });
    }
    if (reuse) {
      bytes = sample!.bytes; observed = sample!.state; capturedAt = sample!.capturedAt;
    } else {
    for (;;) {
      requireVision(Date.now() < deadline, "capture_failed");
      attempts++;
      try {
        phase = "state_before";
        const before = stable ? await inspectState(page) : null;
        phase = "image";
        bytes = await captureVisionScreen(page, deadline - Date.now());
        if (!before) break;
        phase = "state_after";
        observed = await inspectState(page);
        // Hydration may finish between settle and capture. Publish only an image
        // bracketed by matching states; retries are read-only and share one timeout.
        if (equivalentState(before, observed)) break;
        mismatches++;
      } catch (error) {
        // Navigation can destroy either bracketing read. Discard this image and
        // retry evidence only within the original budget, never the physical action.
        if (!stable || !(error instanceof Error) ||
            !error.message.includes("Execution context was destroyed")) throw error;
        contextResets++;
        if (Date.now() + 80 < deadline) await page.waitForTimeout(80);
      }
    }
    }
    phase = "persist";
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
      checksum: digest(bytes), byte_count: bytes.length, content_type: "image/png", captured_at: capturedAt ?? new Date().toISOString(),
    });
    runtime.result.frames.push(frame); runtime.paths.set(frame.id, path);
    runtime.result.operation[`actual_${role}_frame_id`] = frame.id;
    runtime.result.operation[`${role}_page_id`] = this.pageId(session, page);
    return observed;
    } catch (error) {
      logVisionFailure("vision.evidence.capture_failed", { role, capture_stage: phase,
        error_type: visionErrorType(error), attempts, state_mismatches: mismatches,
        context_resets: contextResets, duration_ms: Date.now() - started,
        page_closed: page.isClosed(), browser_connected: session.browser.isConnected() });
      throw error;
    }
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
        state_id: request.state_id, proposal_id: request.proposal_id, checkpoint_id: request.restore_checkpoint_id ?? request.history_checkpoint_id,
        expected_parent_fingerprint: request.expected_state_fingerprint,
        parent_operation_id: request.action.kind === "navigate" ? null : session.ancestry.at(-1) ?? null,
        started_at: new Date().toISOString(), status: "prepared",
      });
      const runtime: OperationRuntime = { payloadHash, submittedAction: canonical(request.action), prepare: request, before: null, page: session.page, paths: new Map(), replayable: false,
        result: { operation, frames: [], locator: null, prepared_handle: randomUUID(), state_fingerprint: null,
          checkpoint: null, semantic_change: "unavailable", duration_ms: 0, acknowledged: false, replayable: false,
          history_restore_available: false,
          dispatch_started: false, failure_stage: null } };
      session.operations.set(request.operation_id, runtime);
      try {
        if (session.request.step_timeout_seconds != null) {
          const deadline = Date.parse(request.step_deadline ?? "");
          requireVision(deadline > Date.now() && deadline <= Date.now() + session.request.step_timeout_seconds * 1000, "invalid_step_deadline");
          session.deadline = deadline;
          clearTimeout(session.timer);
          session.timer = setTimeout(() => { void this.expire(session); }, Math.max(1, deadline - Date.now()));
          session.timer.unref();
        } else requireVision(request.step_deadline == null, "invalid_step_deadline");
        if (session.policyFailure) throw new VisionWorkerError(session.policyFailure);
        if (request.refresh_observation) {
          requireVision(request.purpose === "setup" && request.action.kind === "wait" &&
            request.checkpoint_id && !request.proposal_id && !request.dom_snapshot_id &&
            !request.expected_locator && !request.restore_checkpoint_id && !request.replay_operation_id,
          "invalid_observation_refresh");
          requireVision(request.expected_state_fingerprint === session.state.fingerprint, "state_mismatch");
          // A refresh may follow scrolling into lazy content or a carousel.
          // Use the navigation readiness window, still bounded by this step.
          const settled = await settleState(session.page, Math.min(session.deadline, Date.now() + 10_000), 800);
          requireVision(settled.settled, "settle_timeout");
          runtime.before = settled.state;
        } else {
          runtime.before = await inspectState(session.page);
          if (!equivalentState(runtime.before, session.state)) logStateMismatch(session.state, runtime.before, "prepare_start");
          requireVision(runtime.before.fingerprint === request.expected_state_fingerprint &&
            equivalentState(runtime.before, session.state), "state_mismatch");
        }
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
        if (request.expected_locator?.strategy === "dom_path") requireVision(
          ["buttons", "visual_buttons"].includes(session.request.interaction_scope) && request.dom_snapshot_id && request.dom_element_id,
          "live_node_binding_required");
        if (request.purpose === "explore") requireVision(session.ancestry.length <= session.request.max_hops, "hop_limit");
        if (request.purpose === "explore" || request.purpose === "setup") requireVision(session.exploredStates < session.request.max_states, "state_limit");
        if (request.checkpoint_id) {
          requireVision(!session.checkpoints.has(request.checkpoint_id), "checkpoint_already_exists");
          requireVision(session.checkpoints.size < session.request.max_states, "state_limit");
        }
        if (request.restore_checkpoint_id) requireVision(session.checkpoints.has(request.restore_checkpoint_id), "checkpoint_unavailable");
        if (request.history_checkpoint_id) runtime.historyFromEntryId = await validateHistory(
          session.checkpoints.get(request.history_checkpoint_id)?.history, runtime.page);
        if (request.purpose === "replay") {
          const source = session.operations.get(request.replay_operation_id!);
          requireVision(source?.result.operation.status === "completed" && source.replayable && source.prepare, "unsafe_replay");
          requireVision(source.submittedAction === canonical(request.action) &&
            canonical(source.result.locator?.descriptor ?? null) === canonical(request.expected_locator), "replay_mismatch");
          // DOM proposals carry placeholder coordinates. Replay must first match
          // the original request, then use the worker's verified coordinates;
          // the fresh state and locator checks below still gate dispatch.
          request.action = structuredClone(source.prepare.action);
        }
        if (request.action.kind === "navigate") {
          requireVision(request.purpose === "setup" || request.purpose === "replay" ||
            (request.purpose === "restore" && request.restore_checkpoint_id &&
              session.checkpoints.get(request.restore_checkpoint_id)?.navigable), "invalid_navigation_purpose");
        }
        if (["back", "close_popup"].includes(request.action.kind)) requireVision(request.purpose === "restore", "invalid_restore_purpose");
        // Before bytes are staged before metadata can be acknowledged by the caller.
        await this.capture(session, runtime, "before", session.page);
        if (["click", "type"].includes(request.action.kind)) {
          if (request.dom_snapshot_id) {
            // Screenshot capture can span a carousel transition. Resolve the
            // retained node again instead of hit-testing its pre-capture point.
            const target = await resolveDomTarget(session.domSnapshots.get(request.dom_snapshot_id!)!,
              session.page, request.dom_element_id!, Math.min(1000, this.timeout(session)));
            request.action.x = target.x; request.action.y = target.y;
          }
          const ground = await groundLocator(session.page, request.action.x!, request.action.y!, request.action.kind === "type", request.expected_locator);
          runtime.grounded = ground;
          // Only serializable evidence crosses the transport; handles stay in RAM.
          const evidence = { status: ground.status, reason_code: ground.reason_code,
            descriptor: ground.descriptor, bounding_box: ground.bounding_box,
            matched_count: ground.matched_count, target_match: ground.target_match,
            actionable: ground.actionable, verified_at: ground.verified_at };
          runtime.result.locator = validateVision<VisualLocatorEvidence>("VisualLocatorEvidence", {
            ...evidence, id: randomUUID(), tenant_id: request.tenant_id, project_id: request.project_id,
            session_id: request.session_id, operation_id: request.operation_id, state_id: request.state_id,
            proposal_id: request.proposal_id, originating_frame_id: operation.actual_before_frame_id,
            model_confidence: request.model_confidence,
          });
          operation.locator_id = runtime.result.locator.id;
          requireVision(ground.status === "verified", ground.reason_code ?? "locator_unresolved");
          if (request.dom_snapshot_id) {
            await verifySnapshotTarget(session.domSnapshots.get(request.dom_snapshot_id)!, ground.target!, request.dom_element_id!);
          }
          if (session.request.interaction_scope === "buttons") {
            requireVision(request.action.kind === "click" && await ground.target!.evaluate(el =>
              el.getAttribute("role") === "button" || (!el.hasAttribute("role") &&
              el.matches('button,input[type="button"],input[type="submit"],input[type="reset"]'))), "out_of_scope_target");
          }
          if (session.request.interaction_scope === "visual_buttons") {
            requireVision(request.action.kind === "click" && (await ground.target!.evaluate(visualButtonSemantics)).length === 1, "out_of_scope_target");
          }
          if (request.action.kind === "click") runtime.replayable = await ground.target!.evaluate((el) => el.tagName === "A" &&
            !!el.getAttribute("href") && !el.hasAttribute("download") && !el.hasAttribute("onclick"));
        }
        const preparedState = await inspectState(session.page);
        if (!equivalentState(runtime.before, preparedState)) logStateMismatch(runtime.before, preparedState, "prepare_end");
        requireVision(equivalentState(runtime.before, preparedState), "state_changed_during_prepare");
        runtime.result.state_fingerprint = runtime.before.fingerprint;
        session.pending = request.operation_id;
      } catch (error) {
        runtime.result.failure_stage = "prepare";
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
      requireVision(!session.expired && Date.now() < session.deadline, this.timeoutCode(session));
      requireVision(session.pending === request.operation_id && runtime.prepare && runtime.before, "operation_not_prepared");
      const command = runtime.prepare, action = command.action;
      let expectsPopup = false;
      let status: "completed" | "rejected" | "failed" | "unknown" = "rejected", code = "state_mismatch";
      let afterPage = runtime.page;
      let earlyOutcome: Promise<OutcomeSample | null> = Promise.resolve(null);
      let documentChanged = false;
      const onFrameNavigated = (frame: Frame) => {
        if (frame === runtime.page.mainFrame()) documentChanged = true;
      };
      runtime.page.on("framenavigated", onFrameNavigated);
      const initialPages = new Set(session.context.pages());
      let pageCreated: (() => void) | undefined;
      const popupReady = new Promise<void>((resolve) => { pageCreated = resolve; });
      let downloadStarted = false;
      const downloadDestinations = new Set<string>();
      let downloadDestinationsTruncated = false;
      const navigationChain = new Map<string, { url_sha256: string; redirected_from_sha256: string | null }>();
      const onNavigation = (navigation: Request) => {
        try {
          if (session.activeOperation !== request.operation_id || action.kind !== "click" ||
              !navigation.isNavigationRequest()) return;
          const hash = digest(navigation.url());
          if (navigationChain.size >= 32 && !navigationChain.has(hash)) {
            downloadDestinationsTruncated = true;
            return;
          }
          const previous = navigation.redirectedFrom();
          navigationChain.set(hash, { url_sha256: hash,
            redirected_from_sha256: previous ? digest(previous.url()) : null });
        } catch { /* Evidence failures must not affect browser execution. */ }
      };
      session.context.on("request", onNavigation);
      session.downloadOwner = (page, url) => {
        if (session.activeOperation !== request.operation_id || action.kind !== "click" ||
            (page !== runtime.page && initialPages.has(page))) return false;
        downloadStarted = true;
        const hash = digest(url);
        if (downloadDestinations.size < 8 || downloadDestinations.has(hash)) downloadDestinations.add(hash);
        else downloadDestinationsTruncated = true;
        pageCreated?.();
        return true;
      };
      const onPage = () => { pageCreated?.(); };
      session.context.on("page", onPage);
      try {
        requireVision(!session.policyFailure, session.policyFailure ?? "origin_denied");
        const dispatchState = await inspectState(runtime.page);
        if (!equivalentState(runtime.before, dispatchState)) logStateMismatch(runtime.before, dispatchState, "before_dispatch");
        requireVision(equivalentState(runtime.before, dispatchState), "state_mismatch");
        if (runtime.grounded) {
          if (runtime.grounded.descriptor?.strategy === "dom_path") {
            const box = await runtime.grounded.target!.boundingBox(), viewport = runtime.page.viewportSize();
            requireVision(box && viewport && box.x >= 0 && box.y >= 0 && box.x + box.width <= viewport.width &&
              box.y + box.height <= viewport.height, "stale_dom_target");
            action.x = (box.x + box.width / 2) / (viewport.width - 1);
            action.y = (box.y + box.height / 2) / (viewport.height - 1);
          }
          const fresh = await groundLocator(runtime.page, action.x!, action.y!, action.kind === "type", runtime.grounded.descriptor);
          const sameTarget = fresh.target && runtime.grounded.target && await fresh.target.evaluate((el, old) => el === old, runtime.grounded.target).catch(() => false);
          await fresh.target?.dispose();
          requireVision(fresh.status === "verified" && sameTarget, "stale_locator");
          if (session.request.interaction_scope === "visual_buttons") requireVision(
            (await runtime.grounded.target!.evaluate(visualButtonSemantics)).length === 1,
            "out_of_scope_target");
        }
        if (command.history_checkpoint_id) await validateHistory(
          session.checkpoints.get(command.history_checkpoint_id)?.history, runtime.page, runtime.historyFromEntryId);
        runtime.result.operation.status = "executing";
        runtime.result.dispatch_started = true;
        if (command.purpose === "explore" || command.purpose === "setup") session.exploredStates++;
        session.activeOperation = request.operation_id;
        status = "unknown"; code = "action_outcome_unknown";
        const timeout = this.timeout(session);
        if (action.kind === "navigate") {
          const saved = command.purpose === "restore" && command.restore_checkpoint_id
            ? session.checkpoints.get(command.restore_checkpoint_id) : null;
          // A URL comes only from the worker's own checkpoint, never from a model.
          await runtime.page.goto(saved?.url ?? session.request.target_url, { waitUntil: "domcontentloaded", timeout });
          if (saved) await runtime.page.evaluate(({ x, y }) => scrollTo(x, y), { x: saved.state.scroll_x, y: saved.state.scroll_y });
        }
        else if (action.kind === "back") {
          if (command.history_checkpoint_id) await returnToHistory(
            session.checkpoints.get(command.history_checkpoint_id)!.history!, runtime.page, runtime.historyFromEntryId!, timeout);
          else await runtime.page.goBack({ waitUntil: "domcontentloaded", timeout });
        } else if (action.kind === "close_popup") {
          const parent = session.parents.get(runtime.page);
          requireVision(parent && !parent.isClosed(), "popup_parent_unavailable");
          await runtime.page.close(); afterPage = parent;
        } else if (action.kind === "click") {
          expectsPopup = await runtime.grounded!.target!.evaluate(el =>
            el.closest('a')?.getAttribute('target')?.toLowerCase() === '_blank');
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
          const canRecord = runtime.grounded!.descriptor?.strategy !== "dom_path" && viewport?.width === 1280 && viewport.height === 720 && point &&
            point.x >= 0 && point.x <= 1279 && point.y >= 0 && point.y <= 719 &&
            box.x >= 0 && box.y >= 0 && box.x + box.width <= 1280 && box.y + box.height <= 720 &&
            !runtime.grounded!.descriptor?.scope.some((scope) => scope.kind === "iframe") &&
            groundedBox && Math.abs(groundedBox.width * 1280 - box.width) < 1 &&
            Math.abs(groundedBox.height * 720 - box.height) < 1;
          const capture = await observeClick(runtime.grounded!.target!).catch(() => null);
          let actual: Awaited<NonNullable<typeof capture>["result"]> = null;
          try {
            if (runtime.grounded!.descriptor?.strategy === "dom_path") {
              // The retained node must survive through dispatch. A replacement
              // at the same CSS path can never inherit this proposal.
              await runtime.grounded!.target!.click({ timeout });
            } else await runtime.grounded!.locator!.click({ timeout, position: {
              x: action.x! * 1279 - box.x, y: action.y! * 719 - box.y } });
          } finally {
            // A navigation may destroy the event context; retain the existing
            // conservative geometry fallback only when its checks succeed.
            if (capture) { await capture.dispose(); actual = await capture.result; }
          }
          if (actual && actual.width === 1280 && actual.height === 720 &&
              actual.x >= 0 && actual.x <= 1279 && actual.y >= 0 && actual.y <= 719) runtime.confirmedClick = {
            x: actual.x / 1279, y: actual.y / 719, viewport_width: 1280, viewport_height: 720,
            before_frame_id: beforeFrame.id, confirmed_at: new Date().toISOString(),
          };
          else if (canRecord) runtime.confirmedClick = {
            x: point.x / 1279, y: point.y / 719, viewport_width: 1280, viewport_height: 720,
            before_frame_id: beforeFrame.id, confirmed_at: new Date().toISOString(),
          };
        } else if (action.kind === "type") {
          // Preserve append semantics; do not persist text in evidence or fill/clear.
          await runtime.grounded!.locator!.press("ControlOrMeta+End", { timeout });
          await runtime.grounded!.locator!.pressSequentially(action.text!, { timeout });
        } else if (action.kind === "scroll") await runtime.page.mouse.wheel(0, action.delta_y!);
        else { requireVision(action.duration_ms! < session.deadline - Date.now(), this.timeoutCode(session)); await runtime.page.waitForTimeout(action.duration_ms!); }
        status = "completed"; code = "observed";
        if (action.kind === "click") {
          if (!expectsPopup && !downloadStarted && !documentChanged &&
              session.request.interaction_scope === "visual_buttons" &&
              runtime.grounded?.descriptor?.strategy === "dom_path") {
            earlyOutcome = this.sampleClickOutcome(session, runtime.page, request.operation_id);
          }
          // Playwright can resolve click before the popup page event is delivered.
          // The listener was armed before dispatch and remains armed through settle.
          let timer: ReturnType<typeof setTimeout> | undefined;
          await Promise.race([popupReady, new Promise<void>((resolve) => {
            timer = setTimeout(resolve, Math.min(expectsPopup ? 8000 : 500, Math.max(1, session.deadline - Date.now())));
          })]);
          clearTimeout(timer);
        }
        let popups = session.context.pages().filter((page) => !initialPages.has(page));
        if (downloadStarted) {
          // Chromium exposes an uncommitted download tab as "" or ":" before
          // it can become about:blank. It has no navigated document to inspect.
          for (const page of popups) if (["", ":", "about:blank"].includes(page.url())) await page.close();
          popups = popups.filter(page => !page.isClosed());
          code = "download_started";
          runtime.replayable = false;
        }
        if (expectsPopup && !downloadStarted) requireVision(popups.length > 0, "popup_open_timeout");
        requireVision(popups.length <= 1, "multiple_popups_unsupported");
        if (popups[0]) {
          afterPage = popups[0]; session.parents.set(afterPage, runtime.page);
          await afterPage.waitForLoadState("domcontentloaded", { timeout: this.timeout(session) }).catch(() => undefined);
        }
        if (downloadStarted && afterPage !== runtime.page && ["", ":", "about:blank"].includes(afterPage.url())) {
          // A page event may win the race with its download event.
          session.parents.delete(afterPage);
          await afterPage.close();
          afterPage = runtime.page;
        }
        this.observeOrigin(session, afterPage.url(), afterPage === runtime.page ? "navigation" : "popup");
        if (session.policyFailure) throw new VisionWorkerError(session.policyFailure);
        // DOMContentLoaded can precede hydration and carousel initialization by
        // several seconds. Scrolling can reveal lazy content and make DOM reads
        // slow too, including during replay. Keep the original step deadline.
        const navigated = ["navigate", "back", "close_popup"].includes(action.kind) ||
          afterPage !== runtime.page || runtime.before.url_fingerprint !== digest(afterPage.url());
        const viewportChanged = navigated || action.kind === "scroll";
        const settleTimeout = viewportChanged ? 10_000 : 1500;
        const settled = await settleState(afterPage, Math.min(session.deadline, Date.now() + settleTimeout), viewportChanged ? 800 : 160);
        if (!settled.settled) { status = "failed"; code = "settle_timeout"; }
        if (downloadStarted) {
          // Download events can precede Chromium's popup page event. Reconcile
          // again after settle so a late uncommitted tab cannot leak into the
          // next operation or become its screenshot source.
          for (const page of session.context.pages()) {
            if (!initialPages.has(page) && ["", ":", "about:blank"].includes(page.url())) await page.close();
          }
          if (status === "completed") code = "download_started";
          runtime.replayable = false;
        }
        session.state = settled.state; runtime.result.state_fingerprint = settled.state.fingerprint;
        runtime.result.semantic_change = runtime.before.semantic_fingerprint === settled.state.semantic_fingerprint ? "unchanged" : "changed";
        runtime.result.operation.url_change = runtime.before.url_fingerprint === settled.state.url_fingerprint ? "unchanged" : "changed";
        if (!command.restore_checkpoint_id && status === "completed") {
          if (action.kind === "navigate") session.ancestry = [request.operation_id];
          else if (command.purpose === "explore" || command.purpose === "replay" || command.refresh_observation ||
              (command.purpose === "setup" && action.kind === "scroll")) session.ancestry.push(request.operation_id);
        }
        runtime.replayable ||= ["navigate", "scroll", "wait"].includes(action.kind);
        runtime.result.replayable = runtime.replayable && status === "completed";
      } catch (error) {
        code = error instanceof VisionWorkerError ? error.code : "action_outcome_unknown";
        if (status === "rejected" && runtime.result.dispatch_started === false)
          runtime.result.failure_stage = "before_dispatch";
        if (status === "completed") status = "failed";
      } finally {
        runtime.page.off("framenavigated", onFrameNavigated);
        session.context.off("request", onNavigation);
        session.context.off("page", onPage);
        session.downloadOwner = undefined;
        session.activeOperation = null; session.pending = null; session.page = afterPage;
        let captured: RuntimeState | null = null;
        try {
          // Failed/unknown actions retain diagnostic pixels even when the page
          // never settles; only a successful action can create a checkpoint.
          const sample = await earlyOutcome;
          const retainedTarget = sample && await runtime.grounded?.target?.evaluate(
            element => element.isConnected).catch(() => false);
          captured = await this.capture(session, runtime, "after", afterPage, status === "completed",
            status === "completed" && retainedTarget && !documentChanged && !downloadStarted ? sample : null);
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
            const metadata = checkpointMetadata(command.checkpoint_id, command.checkpoint_state_id!, [...session.ancestry], captured, afterPage.url());
            // Only stateless navigations may be restored directly. Forms and in-page
            // state continue through verified back/replay and strict equality checks.
            const navigable = runtime.replayable && runtime.result.operation.url_change === "changed" &&
              await afterPage.locator("input,textarea,select,[contenteditable=true]").count() === 0;
            metadata.url_restore_allowed = navigable;
            const history = await captureHistory(afterPage, captured, session.navigationMethods.get(afterPage));
            session.checkpoints.set(metadata.id, { metadata, state: captured, url: afterPage.url(), navigable, history }); runtime.result.checkpoint = metadata;
            runtime.result.history_restore_available = history !== null;
          }
        }
        if (status === "completed" && command.restore_checkpoint_id && !captured) {
          status = "failed"; code = "state_restore_failed";
        }
        runtime.result.replayable = runtime.replayable && status === "completed";
        if (status === "unknown" || code === "state_restore_failed") session.policyFailure = code;
        this.finalize(runtime, status, code);
        if (downloadStarted) logVisionEvent("info", "vision.download.destinations",
          "Observed download destinations; files cancelled without retention.", {}, {
            session_id: session.request.session_id, operation_id: request.operation_id,
            destination_hashes: [...downloadDestinations], truncated: downloadDestinationsTruncated,
            navigation_chain: [...navigationChain.values()],
            status: runtime.result.operation.status,
          });
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
    return this.serialized(session, async () => {
      const observed = await inspectState(session.page);
      const matches = equivalentState(checkpoint.state, observed);
      if (!matches) {
        const scope = visionLogScope.getStore(), saved = checkpoint.state;
        logVisionEvent("warn", "vision.checkpoint.mismatch", "Current page does not match the saved checkpoint.", scope?.context, {
          ...scope?.fields, session_id: sessionId, checkpoint_id: checkpointId, state_id: checkpoint.metadata.state_id,
          code: "checkpoint_mismatch", url_changed: saved.url_fingerprint !== observed.url_fingerprint,
          interaction_changed: saved.interaction_fingerprint !== observed.interaction_fingerprint,
          visual_semantics_changed: saved.semantic_fingerprint !== observed.semantic_fingerprint,
          form_presence_changed: saved.form_presence_fingerprint !== observed.form_presence_fingerprint,
          form_values_changed: saved.privateForms !== observed.privateForms,
          scroll_changed: saved.scroll_x !== observed.scroll_x || saved.scroll_y !== observed.scroll_y,
        });
      }
      // A verified self-link navigation may replace the browser entry ID while
      // preserving this exact checkpoint. Refresh only the private GET handle;
      // never change the saved state, forms, ancestry or public metadata.
      if (matches && checkpoint.history?.page === session.page) {
        const history = await captureHistory(session.page, checkpoint.state,
          session.navigationMethods.get(session.page));
        if (history) checkpoint.history = history;
      }
      return { checkpoint: structuredClone(checkpoint.metadata), matches_current: matches };
    });
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
