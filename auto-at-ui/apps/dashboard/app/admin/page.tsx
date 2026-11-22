"use client";

import { Check, Copy, KeyRound, Search, UserPlus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Spinner } from "@/components/ui/spinner";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ConfirmDialog } from "../components/confirm-dialog";
import { PageHeader } from "../components/page-header";
import { Section } from "../components/section";
import { EmptyState, ErrorState } from "../components/states";
import { StatusBadge } from "../components/status-badge";

type User = { id: string; email: string; role: string; enabled: boolean; force_password_change: boolean };
const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
const csrf = () => document.cookie.split("; ").find((cookie) => cookie.startsWith("auto_at_csrf="))?.split("=")[1] ?? "";

const roles = [
  { value: "viewer", label: "Viewer", description: "Read-only access to runs and results." },
  { value: "contributor", label: "Contributor", description: "Create and run tests within projects." },
  { value: "reviewer", label: "Reviewer", description: "Approve or reject generated changes." },
  { value: "project_admin", label: "Project admin", description: "Manage project settings and members." },
  { value: "tenant_admin", label: "Tenant admin", description: "Full control of the tenant, including users." },
];
const roleLabel = (role: string) => roles.find((entry) => entry.value === role)?.label ?? role.replaceAll("_", " ");

export default function AdminPage() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("contributor");
  const [temporaryPassword, setTemporaryPassword] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [provisioning, setProvisioning] = useState(false);
  const [query, setQuery] = useState("");
  const [pendingDisable, setPendingDisable] = useState<User | null>(null);
  const [disabling, setDisabling] = useState(false);

  const load = async () => {
    const response = await fetch(`${apiUrl}/api/v1/admin/users`, { credentials: "include" });
    if (!response.ok) {
      setError("User administration is unavailable for this account.");
      return;
    }
    setUsers(await response.json());
  };
  useEffect(() => { void load(); }, []);

  const provision = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setProvisioning(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/admin/users`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ email, role }),
      });
      if (!response.ok) {
        setError("The account could not be provisioned.");
        return;
      }
      const user = await response.json();
      setTemporaryPassword(user.temporary_password);
      setCopied(false);
      toast.success(`Account provisioned for ${email}`);
      setEmail("");
      await load();
    } finally {
      setProvisioning(false);
    }
  };

  const disable = async () => {
    if (!pendingDisable) return;
    setDisabling(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/admin/users/${pendingDisable.id}`, {
        method: "DELETE",
        credentials: "include",
        headers: { "X-CSRF-Token": csrf() },
      });
      if (response.ok) toast.success(`${pendingDisable.email} was disabled`);
      else toast.error(`Could not disable ${pendingDisable.email}`);
      await load();
    } finally {
      setDisabling(false);
      setPendingDisable(null);
    }
  };

  const copyPassword = async () => {
    if (!temporaryPassword) return;
    try {
      await navigator.clipboard.writeText(temporaryPassword);
      setCopied(true);
      toast.success("Temporary password copied");
    } catch {
      toast.error("Copy failed. Select the password and copy it manually.");
    }
  };

  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    if (!users || !term) return users;
    return users.filter((user) => user.email.toLowerCase().includes(term) || user.role.toLowerCase().includes(term) || roleLabel(user.role).toLowerCase().includes(term));
  }, [users, query]);

  const selectedRole = roles.find((entry) => entry.value === role);

  return <>
    <PageHeader
      eyebrow="Administration"
      title="Users"
      description="Provision tenant accounts and assign least-privilege roles."
      actions={users && <Badge variant="secondary" className="px-3 py-1 text-sm font-normal">{users.length} {users.length === 1 ? "user" : "users"}</Badge>}
    />
    <div className="flex flex-col gap-6">
      {temporaryPassword && <Alert role="status" className="border-warning/40 bg-warning/10">
        <KeyRound />
        <AlertTitle className="font-semibold">Copy this temporary password now:</AlertTitle>
        <AlertDescription className="gap-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <code className="min-w-0 select-all break-all rounded-md border bg-background px-3 py-2 font-mono text-sm text-foreground">{temporaryPassword}</code>
            <div className="flex flex-wrap gap-2">
              <Button type="button" variant="outline" size="sm" onClick={() => void copyPassword()}>
                {copied ? <Check /> : <Copy />}
                {copied ? "Copied" : "Copy"}
              </Button>
              <Button type="button" size="sm" onClick={() => setTemporaryPassword(null)}>I have copied it</Button>
            </div>
          </div>
          <p>It will not be shown again after this acknowledgement, navigation, or reload.</p>
        </AlertDescription>
      </Alert>}

      <Section title="Provision user" description="The new user receives a one-time temporary password and must change it at first sign-in.">
        <form onSubmit={(e) => void provision(e)} className="grid gap-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1.2fr)_auto] md:items-start">
          <Field>
            <FieldLabel htmlFor="provision-email">Email</FieldLabel>
            <Input id="provision-email" required type="email" autoComplete="off" placeholder="name@company.com" value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Field>
            <FieldLabel htmlFor="provision-role">Role</FieldLabel>
            <NativeSelect id="provision-role" className="w-full" value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((entry) => <NativeSelectOption key={entry.value} value={entry.value}>{entry.label}</NativeSelectOption>)}
            </NativeSelect>
            <FieldDescription>{selectedRole?.description}</FieldDescription>
          </Field>
          <Button type="submit" disabled={provisioning} className="md:mt-[1.625rem]">
            {provisioning ? <Spinner /> : <UserPlus />}
            Provision account
          </Button>
        </form>
      </Section>

      {error && <ErrorState title="Unable to load users">{error}</ErrorState>}

      {users === null && !error && <Section aria-label="Loading users" aria-busy="true" contentClassName="flex flex-col gap-3">
        <span className="sr-only" role="status">Loading users</span>
        {[0, 1, 2, 3].map((row) => <div key={row} className="flex items-center gap-3">
          <Skeleton className="size-9 rounded-full" />
          <div className="flex-1 space-y-2"><Skeleton className="h-4 w-1/3" /><Skeleton className="h-3 w-1/5" /></div>
          <Skeleton className="h-6 w-20" />
        </div>)}
      </Section>}

      {users?.length === 0 && <EmptyState title="No tenant users">Provision the first collaborator above.</EmptyState>}

      {users && users.length > 0 && <Section
        title="Tenant users"
        className="overflow-hidden"
        contentClassName="px-0"
      >
        <div className="relative px-6 pb-4 sm:max-w-sm">
          <Search className="pointer-events-none absolute left-9 top-[0.625rem] size-4 text-muted-foreground" aria-hidden="true" />
          <Input type="search" aria-label="Search users by email or role" placeholder="Search email or role" className="pl-9" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="pl-6">User</TableHead>
              <TableHead>Role</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="pr-6 text-right"><span className="sr-only">Actions</span></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered?.length === 0 && <TableRow>
              <TableCell colSpan={4} className="py-10 text-center text-muted-foreground">No users match “{query}”.</TableCell>
            </TableRow>}
            {filtered?.map((user) => <TableRow key={user.id}>
              <TableCell className="pl-6">
                <div className="flex items-center gap-3">
                  <Avatar className="size-9">
                    <AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">{user.email.slice(0, 2).toUpperCase()}</AvatarFallback>
                  </Avatar>
                  <div className="min-w-0">
                    <p className="max-w-[18rem] truncate font-medium">{user.email}</p>
                    {user.force_password_change && <p className="text-xs text-warning-foreground dark:text-warning">Password change required</p>}
                  </div>
                </div>
              </TableCell>
              <TableCell><Badge variant="secondary" className="capitalize">{roleLabel(user.role)}</Badge></TableCell>
              <TableCell><StatusBadge status={user.enabled ? "completed" : "cancelled"}>{user.enabled ? "Active" : "Disabled"}</StatusBadge></TableCell>
              <TableCell className="pr-6 text-right">
                {user.enabled && <Button type="button" variant="outline" size="sm" className="text-destructive hover:text-destructive" aria-label={`Disable ${user.email}`} onClick={() => setPendingDisable(user)}>Disable</Button>}
              </TableCell>
            </TableRow>)}
          </TableBody>
        </Table>
      </Section>}
    </div>

    <ConfirmDialog
      open={pendingDisable !== null}
      title="Disable this account?"
      description={`${pendingDisable?.email ?? "This user"} will no longer be able to sign in to this tenant.`}
      confirmLabel="Disable account"
      busy={disabling}
      onConfirm={() => void disable()}
      onCancel={() => setPendingDisable(null)}
    />
  </>;
}
