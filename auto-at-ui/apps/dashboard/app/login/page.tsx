"use client";

import { AlertCircle } from "lucide-react";
import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { postLoginPath } from "../components/app-shell-state";
import { AuthShell, PasswordInput } from "../components/auth-shell";

const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/login`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        // No tenant here: the user picks one after signing in when they belong to several.
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setError("We could not sign you in. Check your details and try again.");
        return;
      }
      const me = await response.json();
      const session = await fetch(`${apiUrl}/api/v1/auth/me`, { credentials: "include" });
      if (!session.ok) {
        setError("Your session could not be established. Allow cookies for this site and try again.");
        return;
      }
      window.location.assign(postLoginPath(me, new URLSearchParams(window.location.search).get("next")));
    } catch {
      setError("Cannot reach the server. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  return <AuthShell
    eyebrow="Auto-AT Control"
    title="Sign in"
    description="Sign in with your email. You choose the tenant next if you belong to more than one."
  >
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-5">
      <FieldGroup>
        <Field>
          <FieldLabel htmlFor="login-email">Email</FieldLabel>
          <Input id="login-email" required type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
        </Field>
        <Field>
          <FieldLabel htmlFor="login-password">Password</FieldLabel>
          <PasswordInput id="login-password" required value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </Field>
      </FieldGroup>
      {error && <Alert variant="destructive">
        <AlertCircle />
        <AlertDescription>{error}</AlertDescription>
      </Alert>}
      <Button type="submit" size="lg" disabled={busy} className="w-full">
        {busy && <Spinner />}
        {busy ? "Signing in…" : "Sign in"}
      </Button>
    </form>
  </AuthShell>;
}
