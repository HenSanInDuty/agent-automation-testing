"use client";

import { AlertCircle, Building2, Check, ChevronRight, LogOut } from "lucide-react";
import { useEffect, useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { apiRequest, ControlPlaneError } from "../api-client";
import { loginRedirectPath, safeNextPath } from "../components/app-shell-state";
import { AuthShell } from "../components/auth-shell";

type TenantOption = { tenant_id: string; role: string };
type Me = { email: string; tenant_id: string };

const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
const roleLabel = (role: string) => role.replaceAll("_", " ");

export default function SelectTenantPage() {
  const [tenants, setTenants] = useState<TenantOption[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [choosing, setChoosing] = useState<string | null>(null);
  const [error, setError] = useState("");

  const destination = () => safeNextPath(new URLSearchParams(window.location.search).get("next"));

  useEffect(() => {
    Promise.all([
      apiRequest<TenantOption[]>(apiUrl, "/api/v1/auth/tenants"),
      apiRequest<Me>(apiUrl, "/api/v1/auth/me"),
    ]).then(([options, account]) => {
      // Nothing to choose: continue straight to the page the user asked for.
      if (options.length <= 1) { window.location.replace(destination()); return; }
      setTenants(options);
      setMe(account);
    }).catch((reason) => {
      if (reason instanceof ControlPlaneError && reason.status === 401) {
        window.location.replace(loginRedirectPath(window.location.pathname, window.location.search));
        return;
      }
      setError("Your tenants could not be loaded. Refresh to try again.");
    });
  }, []);

  async function choose(tenantId: string) {
    if (choosing) return;
    setChoosing(tenantId);
    setError("");
    try {
      if (tenantId !== me?.tenant_id) {
        await apiRequest(apiUrl, "/api/v1/auth/tenant", { method: "POST", body: JSON.stringify({ tenant_id: tenantId }) });
      }
      window.location.assign(destination());
    } catch {
      setError("This tenant is not available for your account. Choose another one.");
      setChoosing(null);
    }
  }

  async function signOut() {
    await apiRequest(apiUrl, "/api/v1/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.assign("/login");
  }

  return <AuthShell
    eyebrow="Auto-AT Control"
    title="Choose a tenant"
    description={me ? `Signed in as ${me.email}. Pick the workspace you want to open.` : "Pick the workspace you want to open."}
    footer={<Button type="button" variant="link" size="sm" className="h-auto p-0 text-xs text-muted-foreground" onClick={() => void signOut()}><LogOut className="size-3.5" /> Sign in with a different account</Button>}
  >
    {error && <Alert variant="destructive" className="mb-4"><AlertCircle /><AlertDescription>{error}</AlertDescription></Alert>}
    {tenants === null && !error && <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading tenants">
      {[0, 1].map((key) => <Skeleton key={key} className="h-16 w-full rounded-lg" />)}
    </div>}
    {tenants && <ul className="flex flex-col gap-2" aria-label="Your tenants">
      {tenants.map((tenant) => {
        const current = tenant.tenant_id === me?.tenant_id;
        const busy = choosing === tenant.tenant_id;
        return <li key={tenant.tenant_id}>
          <button
            type="button"
            onClick={() => void choose(tenant.tenant_id)}
            disabled={Boolean(choosing)}
            aria-current={current ? "true" : undefined}
            className={cn(
              "group flex w-full items-center gap-3 rounded-lg border bg-card p-3 text-left outline-none transition-colors hover:border-primary/40 hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-60",
              current && "border-primary/40 bg-accent/60",
            )}
          >
            <span className="grid size-10 shrink-0 place-items-center rounded-md bg-primary/10 text-primary"><Building2 className="size-5" /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{tenant.tenant_id}</span>
              <span className="mt-1 flex flex-wrap items-center gap-1.5">
                <Badge variant="secondary" className="capitalize">{roleLabel(tenant.role)}</Badge>
                {current && <Badge variant="outline" className="gap-1 text-muted-foreground"><Check className="size-3" />Current</Badge>}
              </span>
            </span>
            {busy ? <Spinner className="text-primary" /> : <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />}
          </button>
        </li>;
      })}
    </ul>}
  </AuthShell>;
}
