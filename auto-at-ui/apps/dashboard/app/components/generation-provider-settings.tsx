"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiRequest } from "../api-client";
import { CheckboxField, Code, FormField, Hint, Notice } from "./agent-ui";
import { Section } from "./section";

type Policy = { provider: "codex_cli" | "huggingface" | "openrouter"; model: string; text_transfer_accepted: boolean; max_seconds: number };
type Catalogue = { policy: Policy; providers: { id: Policy["provider"]; label: string; model: string; configured: boolean }[]; revision: string };

export function GenerationProviderSettings({ apiUrl }: { apiUrl: string }) {
  const [catalogue, setCatalogue] = useState<Catalogue | null>(null);
  const [draft, setDraft] = useState<Policy | null>(null);
  const [canManage, setCanManage] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState("");
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let disposed = false;
    setCatalogue(null); setDraft(null); setCanManage(false);
    Promise.all([
      apiRequest<Catalogue>(apiUrl, "/api/v1/test-generations/provider"),
      apiRequest<{ role: string }>(apiUrl, "/api/v1/auth/me"),
    ]).then(([next, me]) => {
      if (!disposed) { setCatalogue(next); setDraft(next.policy); setCanManage(me.role === "tenant_admin"); }
    }).catch(() => { if (!disposed) setNotice("Generation settings are unavailable. Refresh to try again."); });
    return () => { disposed = true; };
  }, [apiUrl, refresh]);

  async function save() {
    if (!draft || saving) return;
    setSaving(true); setNotice("");
    try {
      const next = await apiRequest<Catalogue>(apiUrl, "/api/v1/test-generations/provider", { method: "PUT", body: JSON.stringify(draft) });
      setCatalogue(next); setDraft(next.policy); setNotice("Generation provider saved. Drafts still require approval before execution.");
    } catch (error) { setNotice(error instanceof Error ? error.message : "Could not save generation provider."); }
    finally { setSaving(false); }
  }

  const selected = catalogue?.providers.find((item) => item.id === draft?.provider);
  const saved = catalogue?.providers.find((item) => item.id === catalogue.policy.provider);
  const dirty = Boolean(draft && catalogue && JSON.stringify(draft) !== JSON.stringify(catalogue.policy));
  const recipient = draft?.provider === "codex_cli" ? "OpenAI through your existing Codex account" : selected?.label ?? "the selected provider";
  return <Section aria-label="Test generation provider" title="Test generation provider" contentClassName="grid gap-4"
    actions={<Button type="button" variant="outline" size="sm" disabled={saving} onClick={() => { setNotice(""); setRefresh((value) => value + 1); }}><RefreshCw aria-hidden="true" />Refresh settings</Button>}>
    {!catalogue && !notice && <p className="text-sm text-muted-foreground" role="status">Loading generation settings…</p>}
    {catalogue && draft && <>
      <p className="text-sm">Saved provider: <strong>{saved?.label ?? catalogue.policy.provider}</strong> · <Code>{catalogue.policy.model}</Code>. Applies to text drafts and drafts from Vision evidence.</p>
      <div className="flex flex-wrap gap-2" role="group" aria-label="Choose test generation provider">
        {catalogue.providers.map((provider) => <Button key={provider.id} type="button" variant={draft.provider === provider.id ? "default" : "outline"} aria-pressed={draft.provider === provider.id} disabled={saving || !canManage} onClick={() => setDraft({ ...draft, provider: provider.id, model: provider.model, text_transfer_accepted: draft.provider === provider.id ? draft.text_transfer_accepted : false })}>{provider.label}</Button>)}
      </div>
      <Hint>Redacted task text and recorded test evidence are sent to {recipient}. No screenshots are sent for draft generation. Use approved data. {draft.provider === "codex_cli" && "Existing account usage and quota limits apply."}</Hint>
      {!selected?.configured && <Notice tone="warning" role="status">This provider is unavailable. Check its connection, then refresh settings.</Notice>}
      {canManage ? <>
        <FormField id="generation-model" label="Generation model" className="max-w-md"><Input id="generation-model" value={draft.model} readOnly={draft.provider === "codex_cli"} disabled={saving} onChange={(event) => setDraft({ ...draft, model: event.target.value })} /></FormField>
        <CheckboxField checked={draft.text_transfer_accepted} disabled={saving} onCheckedChange={(checked) => setDraft({ ...draft, text_transfer_accepted: checked })}>I accept text and recorded evidence transfer to this generation provider.</CheckboxField>
        <div className="flex flex-wrap gap-2"><Button type="button" disabled={saving || !dirty || !draft.model.trim() || (draft.text_transfer_accepted && !selected?.configured)} onClick={() => void save()}>{saving ? "Saving…" : "Save generation provider"}</Button><Button type="button" variant="outline" disabled={saving || !dirty} onClick={() => setDraft(catalogue.policy)}>Discard changes</Button></div>
        {dirty && <Notice tone="info" role="status">Unsaved changes. New requests use the saved generation provider.</Notice>}
      </> : <Hint>Only a tenant administrator can change the generation provider.</Hint>}
      <Hint>Changing provider stops an active Codex generation request. It does not retry failed drafts or change past results. Vision exploration has its own provider setting below.</Hint>
    </>}
    {notice && <Notice tone={notice.startsWith("Generation provider saved") ? "success" : notice.includes("unavailable") ? "warning" : "danger"} role="status">{notice}</Notice>}
  </Section>;
}
