import type { VisionPolicy, VisionProvider } from "../generation-types";

export function visionProviderLabel(provider: string): string {
  if (provider === "gemini") return "Gehihi (Google Gemini)";
  if (provider === "huggingface") return "Hugging Face";
  if (provider === "codex_cli") return "Codex (existing account)";
  return "Unknown Vision provider";
}

export function screenshotDisclosure(provider: string): string {
  if (provider === "codex_cli") return "When separately permitted and requested, screenshots are sent to OpenAI. Images may contain personal data or secrets. Use only approved synthetic data.";
  return provider === "gemini"
    ? "Raw screenshots will be sent to Google through Gehihi (Google Gemini). They may contain personal data or secrets. Google's free tier has data-use conditions, including use to improve its products. Use only approved synthetic data."
    : `Raw screenshots may be sent to ${visionProviderLabel(provider)}. They may contain personal data or secrets. Use only approved data.`;
}

export function visionDisclosure(policy: VisionPolicy): string {
  if (policy.provider !== "codex_cli") return screenshotDisclosure(policy.provider);
  return "Sanitized page elements and task text are sent to OpenAI using the existing Codex account. The local bridge does not mean offline model processing. "
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
    input_policy_fingerprint: null, codex: provider.id === "codex_cli" ? { input_mode: "dom_first", dom_transfer_accepted: false, dom_transfer_provider: null, max_dom_elements: 100, max_dom_bytes: 65536 } : null };
}

export function hasVisionConsent(policy: VisionPolicy): boolean {
  if (policy.provider === "codex_cli") return Boolean(policy.codex?.dom_transfer_accepted && policy.codex.dom_transfer_provider === "codex_cli");
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
    ...(saved.provider === "codex_cli" && saved.input_policy_fingerprint ? { expected_input_policy_fingerprint: saved.input_policy_fingerprint } : {}) };
}

const failureMessages: Record<string, string> = {
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
  state_restore_failed: "Vision could not restore the recorded page state, so exploration stopped. Check the rejected operations below for the underlying cause.",
  origin_denied: "The browser blocked a request outside the project's allowed origins. Review the permitted domains before starting a new session.",
  initial_capture_failed: "Vision could not capture the opened page. Exploration stopped before requesting model actions. Use Reload to start a new session.",
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
};

export function visionFailureMessage(reason: string | null | undefined): string | undefined {
  return reason && Object.hasOwn(failureMessages, reason) ? failureMessages[reason] : undefined;
}
