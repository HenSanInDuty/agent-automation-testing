"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "../api-client";

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
  return <section className="workspace-section" aria-label="Test generation provider">
    <div className="section-heading"><h2>Test generation provider</h2><button className="button button--secondary" disabled={saving} onClick={() => { setNotice(""); setRefresh((value) => value + 1); }}>Refresh settings</button></div>
    {catalogue && draft && <>
      <p>Saved provider: <strong>{saved?.label ?? catalogue.policy.provider}</strong> · <code>{catalogue.policy.model}</code>. Applies to text drafts and drafts from Vision evidence.</p>
      <div className="form-actions" role="group" aria-label="Choose test generation provider">
        {catalogue.providers.map((provider) => <button key={provider.id} type="button" className={`button ${draft.provider === provider.id ? "" : "button--secondary"}`} aria-pressed={draft.provider === provider.id} disabled={saving || !canManage} onClick={() => setDraft({ ...draft, provider: provider.id, model: provider.model, text_transfer_accepted: draft.provider === provider.id ? draft.text_transfer_accepted : false })}>{provider.label}</button>)}
      </div>
      <p>Redacted task text and recorded test evidence are sent to {recipient}. No screenshots are sent for draft generation. Use approved data. {draft.provider === "codex_cli" && "Existing account usage and quota limits apply."}</p>
      {!selected?.configured && <p role="status">This provider is unavailable. Check its connection, then refresh settings.</p>}
      {canManage ? <>
        <label className="field">Generation model<input aria-label="Generation model" value={draft.model} readOnly={draft.provider === "codex_cli"} disabled={saving} onChange={(event) => setDraft({ ...draft, model: event.target.value })} /></label>
        <label className="field field--checkbox"><input type="checkbox" checked={draft.text_transfer_accepted} disabled={saving} onChange={(event) => setDraft({ ...draft, text_transfer_accepted: event.target.checked })} />I accept text and recorded evidence transfer to this generation provider.</label>
        <div className="form-actions"><button type="button" className="button" disabled={saving || !dirty || !draft.model.trim() || (draft.text_transfer_accepted && !selected?.configured)} onClick={() => void save()}>{saving ? "Saving…" : "Save generation provider"}</button><button type="button" className="button button--secondary" disabled={saving || !dirty} onClick={() => setDraft(catalogue.policy)}>Discard changes</button></div>
        {dirty && <p role="status">Unsaved changes. New requests use the saved generation provider.</p>}
      </> : <p>Only a tenant administrator can change the generation provider.</p>}
      <p>Changing provider stops an active Codex generation request. It does not retry failed drafts or change past results. Vision exploration has its own provider setting below.</p>
    </>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}
