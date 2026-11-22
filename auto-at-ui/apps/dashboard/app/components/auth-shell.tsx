"use client";

import { Eye, EyeOff, FlaskConical } from "lucide-react";
import { type ComponentProps, type ReactNode, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ThemeToggle } from "./theme-provider";

/** Centered layout for routes rendered without the app shell (login, change password). */
export function AuthShell({ eyebrow, title, description, children, footer }: {
  eyebrow?: string;
  title: string;
  description: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return <main className="relative grid min-h-svh place-items-center overflow-hidden bg-background px-4 py-10">
    <div
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_50%_-10%,color-mix(in_oklab,var(--primary)_14%,transparent),transparent)]"
    />
    <div className="absolute right-4 top-4"><ThemeToggle /></div>
    <div className="relative flex w-full max-w-md flex-col gap-6">
      <div className="flex items-center justify-center gap-2.5">
        <span className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm"><FlaskConical className="size-5" /></span>
        <span className="leading-tight">
          <span className="block text-base font-semibold tracking-tight">Auto-AT</span>
          <span className="block text-xs text-muted-foreground">Control plane</span>
        </span>
      </div>
      <Card className="shadow-sm">
        <CardHeader>
          {eyebrow && <p className="text-xs font-medium uppercase tracking-wider text-primary">{eyebrow}</p>}
          <CardTitle><h1 className="text-xl font-semibold tracking-tight">{title}</h1></CardTitle>
          <CardDescription>{description}</CardDescription>
        </CardHeader>
        <CardContent>{children}</CardContent>
      </Card>
      {footer && <p className="text-center text-xs text-muted-foreground">{footer}</p>}
    </div>
  </main>;
}

/** Password input with a show/hide toggle. Accepts the same props as <Input>. */
export function PasswordInput({ className, ...props }: Omit<ComponentProps<typeof Input>, "type">) {
  const [visible, setVisible] = useState(false);
  return <div className="relative">
    <Input {...props} type={visible ? "text" : "password"} className={`pr-10 ${className ?? ""}`} />
    <Button
      type="button"
      variant="ghost"
      size="icon"
      className="absolute right-0.5 top-0.5 size-8 text-muted-foreground"
      aria-label={visible ? "Hide password" : "Show password"}
      aria-pressed={visible}
      onClick={() => setVisible((value) => !value)}
    >
      {visible ? <EyeOff /> : <Eye />}
    </Button>
  </div>;
}
