"use client";

import { useState } from "react";

const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000";

export default function LoginPage() {
  const [tenantId, setTenantId] = useState("demo-tenant"); const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setBusy(true); setError(""); const response = await fetch(`${apiUrl}/api/v1/auth/login`, { method: "POST", credentials: "include", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tenant_id: tenantId, email, password }) }); setBusy(false); if (!response.ok) { setError("We could not sign you in. Check your details and try again."); return; } const me = await response.json(); window.location.assign(me.force_password_change ? "/change-password" : "/"); };
  return <main className="auth-page"><form className="panel auth-card" onSubmit={(event) => void submit(event)}><p className="eyebrow">Auto-AT Control</p><h1>Sign in</h1><p>Use your tenant account to access governed testing.</p><label className="field">Tenant<input required value={tenantId} onChange={(e) => setTenantId(e.target.value)} autoComplete="organization" /></label><label className="field">Email<input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" /></label><label className="field">Password<input required type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>{error && <p className="notice notice--error" role="alert">{error}</p>}<button className="button" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button></form></main>;
}
