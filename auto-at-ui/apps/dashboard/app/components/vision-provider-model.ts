import type { VisionPolicy, VisionProvider, VisualAgentStep } from "../generation-types";

const bridgeVendors: Record<string, string> = { codex_cli: "OpenAI", claude_cli: "Anthropic" };

/** Local DOM-first CLI bridge providers (`codex exec`, `claude -p`). */
export function isBridgeProvider(provider: string | null | undefined): boolean {
  return Boolean(provider && Object.hasOwn(bridgeVendors, provider));
}

/** Company that receives page elements/screenshots for a bridge provider. */
export function bridgeVendor(provider: string): string {
  return Object.hasOwn(bridgeVendors, provider) ? bridgeVendors[provider] : "the provider";
}

export function visionProviderLabel(provider: string): string {
  if (provider === "gemini") return "Gehihi (Google Gemini)";
  if (provider === "claude_cli") return "Claude (claude -p, existing account)";
  if (provider === "huggingface") return "Hugging Face";
  if (provider === "codex_cli") return "Codex (existing account)";
  return "Unknown Vision provider";
}

export function screenshotDisclosure(provider: string): string {
  if (isBridgeProvider(provider)) return `When separately permitted and requested, screenshots are sent to ${bridgeVendor(provider)}. Images may contain personal data or secrets. Use only approved synthetic data.`;
  return provider === "gemini"
    ? "Raw screenshots will be sent to Google through Gehihi (Google Gemini). They may contain personal data or secrets. Google's free tier has data-use conditions, including use to improve its products. Use only approved synthetic data."
    : `Raw screenshots may be sent to ${visionProviderLabel(provider)}. They may contain personal data or secrets. Use only approved data.`;
}

export function visionDisclosure(policy: VisionPolicy): string {
  if (!isBridgeProvider(policy.provider)) return screenshotDisclosure(policy.provider);
  const account = policy.provider === "claude_cli" ? "Claude Code" : "Codex";
  return `Sanitized page elements and task text are sent to ${bridgeVendor(policy.provider)} using the existing ${account} account. The local bridge does not mean offline model processing. `
    + (hasImageConsent(policy) ? "Screenshots may also be sent when requested; each image request counts toward the same call limit." : "Screenshot transfer is disabled. The agent stops if an image is needed.");
}

export function codexReadinessLabel(provider: VisionProvider | undefined): string {
  const status = provider?.bridge_readiness;
  if (!status?.configured || !status.online) return "Codex bridge disconnected";
  if (!status.authenticated) return "Codex login required";
  if (!status.capabilities_qualified) return "Codex bridge needs a compatible CLI";
  if (status.model_access === "unavailable") return "Selected Codex model unavailable";
  if (status.failure_code || !provider?.configured) return "Codex exploration unavailable";
  if (status.busy) return "Codex bridge busy; requests wait in the queue";
  return status.model_access === "unverified" ? "Bridge ready; model access unverified" : "Codex bridge ready";
}

export function switchVisionProvider(policy: VisionPolicy, provider: VisionProvider): VisionPolicy {
  if (policy.provider === provider.id) return policy;
  return { ...policy, provider: provider.id, model: provider.models[0]?.id ?? "", enabled: false, raw_screenshot_transfer_accepted: false, raw_screenshot_transfer_provider: null,
    input_policy_fingerprint: null, codex: isBridgeProvider(provider.id) ? { input_mode: "dom_first", dom_transfer_accepted: false, dom_transfer_provider: null, max_dom_elements: 100, max_dom_bytes: 65536 } : null };
}

export function hasVisionConsent(policy: VisionPolicy): boolean {
  if (isBridgeProvider(policy.provider)) return Boolean(policy.codex?.dom_transfer_accepted && policy.codex.dom_transfer_provider === policy.provider);
  return hasImageConsent(policy);
}

export function hasImageConsent(policy: VisionPolicy): boolean {
  return policy.raw_screenshot_transfer_accepted && (policy.raw_screenshot_transfer_provider === policy.provider
    || (policy.provider === "huggingface" && policy.raw_screenshot_transfer_provider == null));
}

export function hasUnsavedVisionPolicy(saved: VisionPolicy | null, draft: VisionPolicy | null): boolean {
  return Boolean(saved && draft && (Object.keys(saved) as (keyof VisionPolicy)[]).concat(Object.keys(draft) as (keyof VisionPolicy)[]).some((key) => JSON.stringify(saved[key]) !== JSON.stringify(draft[key])));
}

export function visionConfirmation(saved: VisionPolicy): { expected_provider: string; expected_model: string; expected_input_policy_fingerprint?: string } {
  return { expected_provider: saved.provider, expected_model: saved.model,
    ...(isBridgeProvider(saved.provider) && saved.input_policy_fingerprint ? { expected_input_policy_fingerprint: saved.input_policy_fingerprint } : {}) };
}

const failureMessages: Record<string, string> = {
  state_mismatch: "The page changed after its saved screenshot. Exploration stopped before using stale targets. Reload to capture the current page.",
  state_changed_during_observation: "The page changed while its controls were being read. No action was taken from that observation. Reload to try again.",
  dom_snapshot_limit: "The session reached its page observation limit. Saved controls and screenshots remain available.",
  dom_observation_unavailable: "The browser could not read the page controls. Saved screenshots remain available; reload to start a new session.",
  unattributed_popup: "A new tab appeared outside a recorded browser action. Exploration stopped because the source of that tab could not be verified.",
  popup_open_timeout: "The link was clicked, but its new tab did not open within the allowed time. The click was not repeated.",
  bridge_offline: "The Codex bridge is disconnected. Start the bridge, then reload to create a new session.",
  bridge_cli_unsupported: "The Codex bridge needs a compatible CLI before it can accept requests.",
  bridge_login_required: "The Codex login is unavailable or expired. Renew the existing login, then reload.",
  bridge_model_unavailable: "The selected Codex model is unavailable for the existing account.",
  bridge_provider_unavailable: "Codex could not complete the request. Check account access, quota and service availability.",
  bridge_stale_result: "The page or session changed while Codex was working. The result was discarded.",
  bridge_malformed_output: "Codex returned an invalid proposal. No action was taken from that response.",
  bridge_cancelled: "The Codex request was cancelled. Retained browser evidence is still available.",
  bridge_deadline_exceeded: "The Codex request exceeded the session deadline and was stopped.",
  bridge_policy_revoked: "The Codex request stopped because its transfer permission changed or expired.",
  bridge_interrupted: "The Codex bridge restarted during this request. Reload to start a new session.",
  bridge_io_error: "The Codex bridge could not exchange a request safely. Exploration stopped.",
  bridge_output_limit: "The Codex response exceeded its size limit and was discarded.",
  bridge_queue_full: "The Codex bridge queue is full. Try a new session when it is available.",
  bridge_tool_rejected: "Codex attempted an unsupported tool action. The proposal request was stopped.",
  bridge_cleanup_pending: "The request was cancelled, but the bridge has not yet confirmed temporary-file cleanup.",
  image_consent_required: "This page needs an image, but screenshot transfer is disabled. No image was sent.",
  step_limit: "The model-call limit was reached. Image requests count toward the same limit.",
  worker_state_unavailable: "The browser session was interrupted and cannot be resumed. The last saved screen is shown. Use Reload to start a new session; previous evidence is preserved.",
  session_timeout: "The exploration time limit was reached. The last saved screen is shown. Use Reload to start a new session.",
  step_timeout: "This step exceeded its time limit. Earlier evidence is saved; an interrupted click is not repeated automatically.",
  worker_idle_timeout: "The browser was closed after the controller stopped sending work. Earlier evidence is saved.",
  state_restore_failed: "Vision could not restore the recorded page state, so exploration stopped. Check the rejected operations below for the underlying cause.",
  origin_denied: "The browser blocked a request outside the project's allowed origins. Review the permitted domains before starting a new session.",
  initial_capture_failed: "Vision could not capture the opened page. Exploration stopped before requesting model actions. Use Reload to start a new session.",
  exploration_call_limit: "Partial exploration: the model-call budget was reached. Some controls or page regions remain unchecked; retained actions are not a full-site test result.",
  exploration_coverage_incomplete: "Partial exploration: some controls were skipped, rejected or remain unchecked. Review the retained evidence and page inventory.",
  capture_failed: "Vision could not capture the page after a browser action. Exploration stopped; recorded actions remain available.",
  provider_not_configured: "The Vision provider is not configured on the server. Ask a tenant administrator to check its availability.",
  provider_auth_failed: "The Vision provider rejected access. An administrator must check the server credentials and permissions.",
  provider_billing_required: "The Vision provider requires billing for this request. Exploration stopped; no provider fallback was attempted.",
  provider_rate_limited: "The Vision provider quota or request rate limit was reached. Exploration stopped.",
  provider_unavailable: "The Vision provider or selected model is unavailable.",
  provider_model_unavailable: "The selected Vision model is unavailable from its provider.",
  model_unavailable: "The Vision model is unavailable. Retained evidence remains available.",
  provider_timeout: "The Vision provider did not respond within the allowed time. Exploration stopped.",
  model_output_invalid: "The Vision model returned an invalid response or coordinates. No action was taken from that response.",
  vision_reload_active: "This session is still running. Wait for it to finish before reloading.",
  vision_reload_intent_unavailable: "The saved request has expired or is unavailable. Enter the target URL and exploration intent to start a new session.",
  policy_disabled: "Exploration stopped because its policy or consent was disabled or changed.",
  policy_changed: "Exploration stopped because its policy or consent changed.",
  vision_policy_changed: "Vision settings changed. Review the refreshed settings and confirm a new exploration.",
  invalid_vision_policy: "Vision settings are invalid. Check the model and provider consent before saving.",
  image_delivery_auth_required: "Exploration stopped because Google Drive authorization must be renewed. An administrator must reconnect image delivery, then start a new exploration. Button coverage is incomplete.",
  stale_ref: "The page changed after the agent chose this element, so that action was skipped. No browser action was taken from it.",
  invalid_ref: "The agent referred to an element that is not in the current page snapshot. That action was skipped.",
  origin_blocked: "The action would leave the project's allowed origins, so it was skipped.",
  sensitive_action_blocked: "The action could submit a form or send restricted input, so it was skipped. No text was typed.",
  action_kind_blocked: "The agent proposed an action type this exploration does not allow. It was skipped.",
  ineligible_target: "The target element cannot take this action, for example because it is disabled or not editable. It was skipped.",
  batch_stopped: "An earlier action in this step changed the page, so the remaining actions were not run.",
  agent_step_limit: "The agent reached its step limit. Retained steps remain available; this is not a test verdict.",
  agent_done: "The agent finished its exploration goal. Retained steps remain available; this is not a test verdict.",
  agent_stopped: "The agent stopped because it found no safe action to continue. Retained steps remain available.",
};

export function visionFailureMessage(reason: string | null | undefined): string | undefined {
  return reason && Object.hasOwn(failureMessages, reason) ? failureMessages[reason] : undefined;
}

export type ExplorationEngine = "planner" | "agent_loop";

/** Unknown or missing engine values behave exactly like the Planner. */
export function explorationEngine(value: unknown): ExplorationEngine {
  return value === "agent_loop" ? "agent_loop" : "planner";
}

/** Planner requests omit `engine` so their payload is unchanged from before the Agent loop existed. */
export function engineRequestFields(engine: ExplorationEngine): { engine?: "agent_loop" } {
  return engine === "agent_loop" ? { engine: "agent_loop" } : {};
}

/** Safe, bounded copy for one skipped agent action; never shows an unmapped code as a generic message. */
export function blockedReasonMessage(reason: unknown): string {
  if (typeof reason !== "string" || !reason) return "Skipped before it was sent to the browser.";
  return visionFailureMessage(reason) ?? `Skipped (${reason.replaceAll("_", " ").slice(0, 80)}).`;
}

const agentTextLimit = 600;
const agentKindLimit = 40;
const agentBlockedLimit = 20;

export type AgentStepView = { previous: string; memory: string; next: string; blocked: string[] };

function agentText(value: unknown): string {
  if (typeof value !== "string" || !value.trim()) return "Not recorded";
  const text = value.trim();
  return text.length > agentTextLimit ? `${text.slice(0, agentTextLimit)}…` : text;
}

/** Display model for the agent-step block of the ledger; null when the operation has no agent step. */
export function agentStepView(item: { agent_step?: VisualAgentStep | null }): AgentStepView | null {
  const step = item.agent_step;
  if (!step || typeof step !== "object") return null;
  const skipped = Array.isArray(step.skipped_actions) ? step.skipped_actions.slice(0, agentBlockedLimit) : [];
  return {
    previous: agentText(step.evaluation_previous_goal),
    memory: agentText(step.memory),
    next: agentText(step.next_goal),
    blocked: skipped.map((action) => {
      const kind = typeof action?.kind === "string" && action.kind.trim() ? action.kind.trim().slice(0, agentKindLimit) : "Action";
      return `${kind}: ${blockedReasonMessage(action?.skipped_reason)}`;
    }),
  };
}
