import type { VisionPolicy, VisionProvider } from "../generation-types";

export function visionProviderLabel(provider: string): string {
  if (provider === "gemini") return "Gehihi (Google Gemini)";
  if (provider === "huggingface") return "Hugging Face";
  return "Unknown Vision provider";
}

export function screenshotDisclosure(provider: string): string {
  return provider === "gemini"
    ? "Raw screenshots will be sent to Google through Gehihi (Google Gemini). They may contain personal data or secrets. Google's free tier has data-use conditions, including use to improve its products. Use only approved synthetic data."
    : `Raw screenshots may be sent to ${visionProviderLabel(provider)}. They may contain personal data or secrets. Use only approved data.`;
}

export function switchVisionProvider(policy: VisionPolicy, provider: VisionProvider): VisionPolicy {
  if (policy.provider === provider.id) return policy;
  return { ...policy, provider: provider.id, model: provider.models[0]?.id ?? "", enabled: false, raw_screenshot_transfer_accepted: false, raw_screenshot_transfer_provider: null };
}

export function hasVisionConsent(policy: VisionPolicy): boolean {
  return policy.raw_screenshot_transfer_accepted && (policy.raw_screenshot_transfer_provider === policy.provider
    || (policy.provider === "huggingface" && policy.raw_screenshot_transfer_provider == null));
}

export function hasUnsavedVisionPolicy(saved: VisionPolicy | null, draft: VisionPolicy | null): boolean {
  return Boolean(saved && draft && (Object.keys(saved) as (keyof VisionPolicy)[]).concat(Object.keys(draft) as (keyof VisionPolicy)[]).some((key) => saved[key] !== draft[key]));
}

export function visionConfirmation(saved: VisionPolicy): { expected_provider: string; expected_model: string } {
  return { expected_provider: saved.provider, expected_model: saved.model };
}

const failureMessages: Record<string, string> = {
  provider_not_configured: "The Vision provider is not configured on the server. Ask a tenant administrator to check its availability.",
  provider_auth_failed: "The Vision provider rejected access. An administrator must check the server credentials and permissions.",
  provider_billing_required: "The Vision provider requires billing for this request. Exploration stopped; no provider fallback was attempted.",
  provider_rate_limited: "The Vision provider quota or request rate limit was reached. Exploration stopped.",
  provider_unavailable: "The Vision provider or selected model is unavailable.",
  provider_model_unavailable: "The selected Vision model is unavailable from its provider.",
  model_unavailable: "The Vision model is unavailable. Retained evidence remains available.",
  provider_timeout: "The Vision provider did not respond within the allowed time. Exploration stopped.",
  model_output_invalid: "The Vision model returned an invalid response or coordinates. No action was taken from that response.",
  policy_disabled: "Exploration stopped because its policy or consent was disabled or changed.",
  policy_changed: "Exploration stopped because its policy or consent changed.",
  vision_policy_changed: "Vision settings changed. Review the refreshed settings and confirm a new exploration.",
  invalid_vision_policy: "Vision settings are invalid. Check the model and provider consent before saving.",
  image_delivery_auth_required: "Exploration stopped because Google Drive authorization must be renewed. An administrator must reconnect image delivery, then start a new exploration. Button coverage is incomplete.",
};

export function visionFailureMessage(reason: string | null | undefined): string | undefined {
  return reason && Object.hasOwn(failureMessages, reason) ? failureMessages[reason] : undefined;
}
