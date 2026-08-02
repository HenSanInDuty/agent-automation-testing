"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect, useState } from "react";
import { isActiveRoute, navigationItems, nextDrawerState } from "./app-shell-state";

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  return <nav aria-label="Primary navigation"><ul className="navigation-list">{navigationItems.map((item) => <li key={item.href}><Link href={item.href} aria-current={isActiveRoute(pathname, item.href) ? "page" : undefined} onClick={onNavigate}>{item.label}</Link></li>)}</ul></nav>;
}

export function AppShell({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [account, setAccount] = useState<{ email: string; role: string; tenant_id: string } | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_CONTROL_PLANE_URL ?? "http://localhost:7000";
  const pathname = usePathname();
  const closeDrawer = () => setDrawerOpen((open) => nextDrawerState(open, "close"));
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setDrawerOpen((open) => nextDrawerState(open, "escape")); };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  useEffect(() => { void fetch(`${apiUrl}/api/v1/auth/me`, { credentials: "include" }).then(async (response) => response.ok ? setAccount(await response.json()) : setAccount(null)).catch(() => setAccount(null)); }, [apiUrl, pathname]);
  if (pathname === "/login" || pathname === "/change-password") return <>{children}</>;
  const initials = account ? account.email.slice(0, 2).toUpperCase() : "?";
  const logout = async () => { const csrf = document.cookie.split("; ").find((cookie) => cookie.startsWith("auto_at_csrf="))?.split("=")[1]; await fetch(`${apiUrl}/api/v1/auth/logout`, { method: "POST", credentials: "include", headers: { "X-CSRF-Token": csrf ?? "" } }); window.location.assign("/login"); };
  return <div className="app-shell">
    <aside className="sidebar"><Link className="brand" href="/">Auto-AT <span>Control</span></Link><Navigation /><div className="sidebar-footer">Tenant <strong>{account?.tenant_id ?? "Sign in required"}</strong></div></aside>
    {drawerOpen && <button className="drawer-scrim" type="button" aria-label="Close navigation" onClick={closeDrawer} />}
    <aside className={`mobile-drawer ${drawerOpen ? "mobile-drawer--open" : ""}`} aria-label="Mobile navigation"><div className="drawer-heading"><span>Navigation</span><button type="button" className="icon-button" aria-label="Close navigation" onClick={closeDrawer}>×</button></div><Navigation onNavigate={closeDrawer} /></aside>
    <div className="app-main"><header className="top-bar"><button type="button" className="icon-button menu-button" aria-label="Open navigation" aria-expanded={drawerOpen} onClick={() => setDrawerOpen((open) => nextDrawerState(open, "toggle"))}>☰</button><div className="top-bar__context"><span className="tenant-label">{account?.tenant_id ?? "Unauthenticated"}</span><span className="environment-label">Local development</span></div><details className="user-menu"><summary aria-label="Current user menu"><span className="user-avatar" aria-hidden="true">{initials}</span><span><strong>{account?.email ?? "Sign in"}</strong><small>{account?.role ?? "No session"}</small></span></summary><div className="user-menu__panel">{account ? <button className="button button--secondary" type="button" onClick={() => void logout()}>Sign out</button> : <Link href="/login">Sign in</Link>}</div></details></header><main className="content">{children}</main></div>
  </div>;
}
