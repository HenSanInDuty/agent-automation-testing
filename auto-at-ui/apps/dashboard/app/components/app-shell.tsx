"use client";

import { ArrowLeftRight, Bot, ChevronsUpDown, FlaskConical, FolderKanban, KeyRound, LayoutDashboard, LogIn, LogOut, Menu, PlayCircle, ShieldCheck, Users } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";
import { isActiveRoute, isPublicRoute, loginRedirectPath, navigationItems, nextDrawerState, tenantSelectionPath } from "./app-shell-state";
import { ThemeToggle } from "./theme-provider";

type Account = { email: string; role: string; tenant_id: string };
type NavHref = (typeof navigationItems)[number]["href"];

const navigationIcons: Record<NavHref, LucideIcon> = {
  "/": LayoutDashboard,
  "/runs": PlayCircle,
  "/projects": FolderKanban,
  "/agent": Bot,
  "/reviews": ShieldCheck,
  "/admin": Users,
};

const navigationGroups: { label: string; hrefs: NavHref[] }[] = [
  { label: "Workspace", hrefs: ["/", "/runs", "/projects", "/agent"] },
  { label: "Governance", hrefs: ["/reviews", "/admin"] },
];

const roleLabel = (role: string) => role.replaceAll("_", " ");

function Brand() {
  return <Link href="/" className="flex items-center gap-2.5 rounded-md px-2 py-1 outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50">
    <span className="grid size-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm"><FlaskConical className="size-4" /></span>
    <span className="leading-tight">
      <span className="block text-sm font-semibold tracking-tight text-foreground">Auto-AT</span>
      <span className="block text-xs text-muted-foreground">Control plane</span>
    </span>
  </Link>;
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return <nav aria-label="Primary navigation" className="flex flex-col gap-6">
    {navigationGroups.map((group) => <div key={group.label} className="flex flex-col gap-1">
      <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted-foreground/80">{group.label}</p>
      <ul className="flex flex-col gap-0.5">
        {group.hrefs.map((href) => {
          const item = navigationItems.find((entry) => entry.href === href)!;
          const Icon = navigationIcons[href];
          const active = isActiveRoute(pathname, href);
          return <li key={href}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              onClick={onNavigate}
              className={cn(
                "group flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground outline-none transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-[3px] focus-visible:ring-sidebar-ring/50",
                active && "bg-sidebar-accent text-sidebar-accent-foreground",
              )}
            >
              <Icon className={cn("size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-sidebar-accent-foreground", active && "text-sidebar-primary")} />
              {item.label}
            </Link>
          </li>;
        })}
      </ul>
    </div>)}
  </nav>;
}

function TenantCard({ account, switchHref, onNavigate }: { account: Account | null; switchHref: string | null; onNavigate?: () => void }) {
  const body = <>
    <span className="min-w-0 flex-1">
      <span className="block text-muted-foreground">Tenant</span>
      <span className="mt-0.5 block truncate font-medium text-foreground">{account?.tenant_id ?? "Sign in required"}</span>
    </span>
    {switchHref && <ArrowLeftRight className="size-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />}
  </>;
  const frame = "group flex items-center gap-2 rounded-lg border bg-card p-3 text-xs";
  if (!switchHref) return <div className={frame}>{body}</div>;
  return <Link href={switchHref} onClick={onNavigate} aria-label={`Switch tenant (current: ${account?.tenant_id ?? "none"})`} className={cn(frame, "outline-none transition-colors hover:bg-accent focus-visible:ring-[3px] focus-visible:ring-ring/50")}>{body}</Link>;
}

function UserMenu({ account, switchHref, onLogout }: { account: Account | null; switchHref: string | null; onLogout: () => void }) {
  const initials = account ? account.email.slice(0, 2).toUpperCase() : "?";
  if (!account) return <Button asChild size="sm" variant="outline"><Link href="/login"><LogIn /> Sign in</Link></Button>;
  // A popover with real buttons (not a role="menu"): "Sign out" must stay a button for dashboard-auth.spec.ts.
  return <Popover>
    <PopoverTrigger asChild>
      <Button variant="ghost" className="h-10 gap-2.5 px-2" aria-label="Current user menu">
        <Avatar className="size-8"><AvatarFallback className="bg-primary/10 text-xs font-semibold text-primary">{initials}</AvatarFallback></Avatar>
        <span className="hidden min-w-0 text-left leading-tight sm:block">
          <span className="block max-w-48 truncate text-sm font-medium">{account.email}</span>
          <span className="block text-xs capitalize text-muted-foreground">{roleLabel(account.role)}</span>
        </span>
        <ChevronsUpDown className="hidden size-4 text-muted-foreground sm:block" />
      </Button>
    </PopoverTrigger>
    <PopoverContent align="end" className="w-64 p-1">
      <div className="px-2 py-1.5">
        <p className="truncate text-sm font-medium">{account.email}</p>
        <p className="text-xs capitalize text-muted-foreground">{roleLabel(account.role)} · {account.tenant_id}</p>
      </div>
      <Separator className="my-1" />
      {switchHref && <Button asChild variant="ghost" size="sm" className="w-full justify-start font-normal"><Link href={switchHref}><ArrowLeftRight className="text-muted-foreground" /> Switch tenant</Link></Button>}
      <Button asChild variant="ghost" size="sm" className="w-full justify-start font-normal"><Link href="/change-password"><KeyRound className="text-muted-foreground" /> Change password</Link></Button>
      <Separator className="my-1" />
      <Button type="button" variant="ghost" size="sm" className="w-full justify-start font-normal text-destructive hover:bg-destructive/10 hover:text-destructive" onClick={onLogout}><LogOut /> Sign out</Button>
    </PopoverContent>
  </Popover>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [account, setAccount] = useState<Account | null>(null);
  const [tenantCount, setTenantCount] = useState(0);
  // "checking" until the first /auth/me answer; "unreachable" keeps the old behaviour (pages show their own errors).
  const [session, setSession] = useState<"checking" | "authenticated" | "anonymous" | "unreachable">("checking");
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "";
  const pathname = usePathname();
  const router = useRouter();
  useEffect(() => {
    if (isPublicRoute(pathname)) return;
    let disposed = false;
    fetch(`${apiUrl}/api/v1/auth/me`, { credentials: "include" }).then(async (response) => {
      if (disposed) return;
      if (response.ok) { setAccount(await response.json()); setSession("authenticated"); return; }
      setAccount(null);
      if (response.status === 401) { setSession("anonymous"); router.replace(loginRedirectPath(pathname, window.location.search)); return; }
      setSession("unreachable");
    }).catch(() => { if (!disposed) { setAccount(null); setSession("unreachable"); } });
    return () => { disposed = true; };
  }, [apiUrl, pathname, router]);
  const tenantId = account?.tenant_id;
  useEffect(() => {
    if (!tenantId) return;
    let disposed = false;
    // Optional extra: the switcher only appears when the user can actually switch.
    fetch(`${apiUrl}/api/v1/auth/tenants`, { credentials: "include" })
      .then(async (response) => response.ok ? response.json() : [])
      .then((options: unknown) => { if (!disposed) setTenantCount(Array.isArray(options) ? options.length : 0); })
      .catch(() => { if (!disposed) setTenantCount(0); });
    return () => { disposed = true; };
  }, [apiUrl, tenantId]);
  if (isPublicRoute(pathname)) return <>{children}</>;
  if (session === "checking" || session === "anonymous") return <div className="grid min-h-svh place-items-center bg-background" role="status" aria-live="polite">
    <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
      <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm"><FlaskConical className="size-5" /></span>
      <span className="flex items-center gap-2"><Spinner />{session === "anonymous" ? "Redirecting to sign in…" : "Checking your session…"}</span>
    </div>
  </div>;
  const current = navigationItems.find((item) => isActiveRoute(pathname, item.href));
  const logout = async () => { const csrf = document.cookie.split("; ").find((cookie) => cookie.startsWith("auto_at_csrf="))?.split("=")[1]; await fetch(`${apiUrl}/api/v1/auth/logout`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf ?? "" } }); window.location.assign("/login"); };
  const closeDrawer = () => setDrawerOpen((open) => nextDrawerState(open, "navigate"));
  const switchHref = tenantCount > 1 ? tenantSelectionPath(pathname) : null;

  return <div className="min-h-svh bg-background">
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
      <div className="flex h-16 items-center px-4"><Brand /></div>
      <div className="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin"><Navigation /></div>
      <div className="p-3"><TenantCard account={account} switchHref={switchHref} /></div>
    </aside>

    <Sheet open={drawerOpen} onOpenChange={(open) => setDrawerOpen((current) => open ? nextDrawerState(current, "toggle") : nextDrawerState(current, "close"))}>
      <SheetContent side="left" className="w-72 gap-0 bg-sidebar p-0">
        <SheetHeader className="h-16 justify-center px-4"><SheetTitle className="sr-only">Navigation</SheetTitle><SheetDescription className="sr-only">Move between dashboard sections.</SheetDescription><Brand /></SheetHeader>
        <Separator />
        <div className="flex-1 overflow-y-auto px-3 py-4"><Navigation onNavigate={closeDrawer} /></div>
        <div className="p-3"><TenantCard account={account} switchHref={switchHref} onNavigate={closeDrawer} /></div>
      </SheetContent>
    </Sheet>

    <div className="flex min-h-svh flex-col lg:pl-64">
      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/70 sm:px-6">
        <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" aria-expanded={drawerOpen} onClick={() => setDrawerOpen((open) => nextDrawerState(open, "toggle"))}><Menu /></Button>
        <Separator orientation="vertical" className="h-5! lg:hidden" />
        <div className="flex min-w-0 items-center gap-2 text-sm">
          <span className="hidden truncate text-muted-foreground sm:inline">{account?.tenant_id ?? "Unauthenticated"}</span>
          <span className="hidden text-muted-foreground/50 sm:inline">/</span>
          <span className="truncate font-medium">{current?.label ?? "Dashboard"}</span>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <Badge variant="outline" className="hidden gap-1.5 font-normal text-muted-foreground md:inline-flex"><span className="size-1.5 rounded-full bg-success" aria-hidden="true" />Local development</Badge>
          <ThemeToggle />
          <UserMenu account={account} switchHref={switchHref} onLogout={() => void logout()} />
        </div>
      </header>
      <main className="mx-auto w-full max-w-[90rem] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
    </div>
  </div>;
}
