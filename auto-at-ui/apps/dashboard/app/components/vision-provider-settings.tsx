import type { FormEvent } from "react";
import type { VisionPolicy, VisionProvider } from "../generation-types";
import { codexReadinessLabel, hasImageConsent, hasVisionConsent, screenshotDisclosure, switchVisionProvider, visionDisclosure, visionProviderLabel } from "./vision-provider-model";

export function VisionProviderSettings({ policy, providers, canManage, saving, dirty, onChange, onSave, onDiscard }: {
  policy: VisionPolicy; providers: VisionProvider[]; canManage: boolean; saving: boolean; dirty: boolean;
  onChange: (policy: VisionPolicy) => void; onSave: (event: FormEvent<HTMLFormElement>) => void; onDiscard: () => void;
}) {
  const provider = providers.find((item) => item.id === policy.provider);
  const label = visionProviderLabel(policy.provider);
  return <form onSubmit={onSave} className="form-grid form-grid--one">
    {canManage ? <>
      <label className="field">Vision provider<select aria-label="Vision provider" value={policy.provider} disabled={saving} onChange={(event) => {
        const next = providers.find((item) => item.id === event.target.value);
        if (next) onChange(switchVisionProvider(policy, next));
      }}>{!provider && <option value={policy.provider}>{label}</option>}{providers.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
      <label className="field">Vision model{policy.provider === "huggingface"
        ? <input required value={policy.model} disabled={saving} onChange={(event) => onChange({ ...policy, model: event.target.value })} />
        : <select aria-label="Vision model" value={policy.model} disabled={saving} onChange={(event) => onChange({ ...policy, model: event.target.value })}>{provider?.models.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select>}</label>
    </> : <p>Provider: {label}<br />Model: <code>{policy.model}</code></p>}
    {policy.provider === "codex_cli" ? <p role="status">{codexReadinessLabel(provider)}</p> : !provider?.configured && <p role="status">{label} is not configured on the server.</p>}
    <p>Limits: {policy.max_session_seconds}s, {policy.max_screenshot_bytes} bytes. Project policy sets BFS depth and total states.</p>
    <p>{visionDisclosure(policy)}</p>
    {policy.provider === "codex_cli" && <p>{screenshotDisclosure(policy.provider)} Existing account usage and quota limits apply.</p>}
    {canManage && <>
      {policy.provider === "codex_cli" && <label className="field field--checkbox"><input type="checkbox" disabled={saving || !provider} checked={hasVisionConsent(policy)} onChange={(event) => onChange({ ...policy, codex: { input_mode: "dom_first", max_dom_elements: 100, max_dom_bytes: 65536, ...policy.codex, dom_transfer_accepted: event.target.checked, dom_transfer_provider: event.target.checked ? "codex_cli" : null }, enabled: event.target.checked && policy.enabled })} /> I accept sanitized page elements and text transfer to OpenAI.</label>}
      <label className="field field--checkbox"><input type="checkbox" disabled={saving || !provider} checked={hasImageConsent(policy)} onChange={(event) => onChange({ ...policy, raw_screenshot_transfer_accepted: event.target.checked, raw_screenshot_transfer_provider: event.target.checked ? policy.provider : null, enabled: policy.provider === "codex_cli" ? policy.enabled : event.target.checked && policy.enabled })} /> {policy.provider === "codex_cli" ? "Allow screenshots to OpenAI when needed (optional)." : `I accept raw screenshot transfer to ${label}.`}</label>
      <label className="field field--checkbox"><input type="checkbox" checked={policy.enabled} disabled={saving || (!policy.enabled && (!provider?.configured || !hasVisionConsent(policy)))} onChange={(event) => onChange({ ...policy, enabled: event.target.checked })} /> Enable vision exploration</label>
      <div className="form-actions"><button className="button button--secondary" disabled={saving || !provider || !policy.model.trim() || (policy.enabled && (!provider.configured || !hasVisionConsent(policy)))}>{saving ? "Saving…" : "Save vision settings"}</button><button type="button" className="button button--secondary" disabled={saving || !dirty} onClick={onDiscard}>Discard changes</button></div>
    </>}
    <p>Only a tenant administrator can save these settings. The server verifies authorization and consent.</p>
  </form>;
}
