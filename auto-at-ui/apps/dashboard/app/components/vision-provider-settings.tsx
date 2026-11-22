import type { FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import type { CodexInputPolicy, VisionPolicy, VisionProvider } from "../generation-types";
import { CheckboxField, Code, FormField, Hint, Notice } from "./agent-ui";
import { bridgeVendor, codexReadinessLabel, hasImageConsent, hasVisionConsent, isBridgeProvider, screenshotDisclosure, switchVisionProvider, visionDisclosure, visionProviderLabel } from "./vision-provider-model";

export function VisionProviderSettings({ policy, providers, canManage, saving, dirty, onChange, onSave, onDiscard }: {
  policy: VisionPolicy; providers: VisionProvider[]; canManage: boolean; saving: boolean; dirty: boolean;
  onChange: (policy: VisionPolicy) => void; onSave: (event: FormEvent<HTMLFormElement>) => void; onDiscard: () => void;
}) {
  const provider = providers.find((item) => item.id === policy.provider);
  const label = visionProviderLabel(policy.provider);
  return <form onSubmit={onSave} className="grid gap-5">
    {canManage ? <div className="grid gap-4 min-[640px]:grid-cols-2">
      <FormField id="vision-provider" label="Vision provider">
        <NativeSelect id="vision-provider" className="w-full" value={policy.provider} disabled={saving} onChange={(event) => {
          const next = providers.find((item) => item.id === event.target.value);
          if (next) onChange(switchVisionProvider(policy, next));
        }}>{!provider && <option value={policy.provider}>{label}</option>}{providers.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</NativeSelect>
      </FormField>
      <FormField id="vision-model" label="Vision model">{policy.provider === "huggingface"
        ? <Input id="vision-model" required value={policy.model} disabled={saving} onChange={(event) => onChange({ ...policy, model: event.target.value })} />
        : <NativeSelect id="vision-model" className="w-full" value={policy.model} disabled={saving} onChange={(event) => onChange({ ...policy, model: event.target.value })}>{provider?.models.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</NativeSelect>}
      </FormField>
    </div> : <p className="text-sm">Provider: {label}<br />Model: <Code>{policy.model}</Code></p>}
    {isBridgeProvider(policy.provider) ? <Notice tone="info" role="status">{codexReadinessLabel(provider)}</Notice> : !provider?.configured && <Notice tone="warning" role="status">{label} is not configured on the server.</Notice>}
    <div className="grid gap-2">
      <Hint>Limits: {policy.max_session_seconds}s per step; no session time limit for new explorations, {policy.max_screenshot_bytes} bytes. Project policy sets BFS depth and total states.</Hint>
      <Hint>{visionDisclosure(policy)}</Hint>
      {isBridgeProvider(policy.provider) && <Hint>{screenshotDisclosure(policy.provider)} Existing account usage and quota limits apply.</Hint>}
    </div>
    {canManage && <>
      <div className="grid gap-3 rounded-lg border bg-muted/30 p-4">
        {isBridgeProvider(policy.provider) && <CheckboxField disabled={saving || !provider} checked={hasVisionConsent(policy)} onCheckedChange={(checked) => onChange({ ...policy, codex: { input_mode: "dom_first", max_dom_elements: 100, max_dom_bytes: 65536, ...policy.codex, dom_transfer_accepted: checked, dom_transfer_provider: checked ? policy.provider as CodexInputPolicy["dom_transfer_provider"] : null }, enabled: checked && policy.enabled })}>I accept sanitized page elements and text transfer to {bridgeVendor(policy.provider)}.</CheckboxField>}
        <CheckboxField disabled={saving || !provider} checked={hasImageConsent(policy)} onCheckedChange={(checked) => onChange({ ...policy, raw_screenshot_transfer_accepted: checked, raw_screenshot_transfer_provider: checked ? policy.provider : null, enabled: isBridgeProvider(policy.provider) ? policy.enabled : checked && policy.enabled })}>{isBridgeProvider(policy.provider) ? `Allow screenshots to ${bridgeVendor(policy.provider)} when needed (optional).` : `I accept raw screenshot transfer to ${label}.`}</CheckboxField>
        <CheckboxField checked={policy.enabled} disabled={saving || (!policy.enabled && (!provider?.configured || !hasVisionConsent(policy)))} onCheckedChange={(checked) => onChange({ ...policy, enabled: checked })}>Enable vision exploration</CheckboxField>
      </div>
      <div className="flex flex-wrap gap-2"><Button disabled={saving || !provider || !policy.model.trim() || (policy.enabled && (!provider.configured || !hasVisionConsent(policy)))}>{saving ? "Saving…" : "Save vision settings"}</Button><Button type="button" variant="outline" disabled={saving || !dirty} onClick={onDiscard}>Discard changes</Button></div>
    </>}
    <Hint>Only a tenant administrator can save these settings. The server verifies authorization and consent.</Hint>
  </form>;
}
