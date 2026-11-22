"use client";

import { AlertCircle, Check, Circle } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { safeNextPath } from "../components/app-shell-state";
import { AuthShell, PasswordInput } from "../components/auth-shell";

const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
const csrf = () => document.cookie.split("; ").find((cookie) => cookie.startsWith("auto_at_csrf="))?.split("=")[1] ?? "";

const policy = [
  { id: "length", label: "At least 12 characters", test: (value: string) => value.length >= 12 },
  { id: "upper", label: "One uppercase letter", test: (value: string) => /[A-Z]/.test(value) },
  { id: "lower", label: "One lowercase letter", test: (value: string) => /[a-z]/.test(value) },
  { id: "digit", label: "One digit", test: (value: string) => /\d/.test(value) },
];

export default function ChangePasswordPage() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/change-password`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf() },
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      if (!response.ok) {
        setError("Password could not be changed. Use at least 12 characters with upper, lower, and digit.");
        return;
      }
      window.location.assign(safeNextPath(new URLSearchParams(window.location.search).get("next")));
    } catch {
      setError("Cannot reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return <AuthShell
    eyebrow="Action required"
    title="Choose a new password"
    description="Your temporary password cannot be used after this change."
  >
    <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-5">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="cp-current">Current password</FieldLabel>
          <PasswordInput id="cp-current" required value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} autoComplete="current-password" />
        </Field>
        <Field>
          <FieldLabel htmlFor="cp-new">New password</FieldLabel>
          <PasswordInput id="cp-new" required value={newPassword} onChange={(e) => setNewPassword(e.target.value)} autoComplete="new-password" aria-describedby="cp-policy" />
          <FieldDescription id="cp-policy" className="sr-only">Password requirements are listed below.</FieldDescription>
          <ul aria-label="Password requirements" className="grid gap-1.5 pt-1 text-sm sm:grid-cols-2">
            {policy.map((rule) => {
              const met = rule.test(newPassword);
              return <li key={rule.id} className={cn("flex items-center gap-2", met ? "text-success" : "text-muted-foreground")}>
                {met ? <Check className="size-4" aria-hidden="true" /> : <Circle className="size-4" aria-hidden="true" />}
                <span>{rule.label}</span>
                <span className="sr-only">{met ? "(met)" : "(not met)"}</span>
              </li>;
            })}
          </ul>
        </Field>
      </FieldGroup>
      {error && <Alert variant="destructive">
        <AlertCircle />
        <AlertDescription>{error}</AlertDescription>
      </Alert>}
      <Button type="submit" size="lg" disabled={busy} className="w-full">
        {busy && <Spinner />}
        {busy ? "Saving…" : "Save password"}
      </Button>
    </form>
  </AuthShell>;
}
