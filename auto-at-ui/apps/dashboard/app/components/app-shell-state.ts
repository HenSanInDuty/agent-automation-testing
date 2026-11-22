export const navigationItems = [
  { href: "/", label: "Overview" },
  { href: "/runs", label: "Runs" },
  { href: "/projects", label: "Projects & Tests" },
  { href: "/agent", label: "Agent workspace" },
  { href: "/reviews", label: "Reviews" },
  { href: "/admin", label: "Admin" },
] as const;

export function isActiveRoute(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

export function nextDrawerState(current: boolean, event: "toggle" | "close" | "navigate" | "escape"): boolean {
  return event === "toggle" ? !current : false;
}

/** Routes that render without the app shell; they handle their own session state. */
export const publicRoutes = ["/login", "/change-password", "/select-tenant"] as const;

export function isPublicRoute(pathname: string): boolean {
  return (publicRoutes as readonly string[]).includes(pathname);
}

/** Credential pages are never a useful destination after signing in. */
const credentialRoutes = ["/login", "/change-password"];

/** Only same-origin absolute paths are allowed as a post-login destination (blocks `//evil.test`, `https://…`, `/login`). */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return "/";
  const path = next.split(/[?#]/, 1)[0];
  return credentialRoutes.includes(path) ? "/" : next;
}

export function loginRedirectPath(pathname: string, search = ""): string {
  const target = `${pathname}${search}`;
  return target === "/" ? "/login" : `/login?next=${encodeURIComponent(target)}`;
}

export function tenantSelectionPath(next: string): string {
  return next === "/" ? "/select-tenant" : `/select-tenant?next=${encodeURIComponent(next)}`;
}

/** Where to go after a successful login: password change first, then tenant choice, then the page the user wanted. */
export function postLoginPath(login: { force_password_change: boolean; tenant_selection_required?: boolean }, next: string | null | undefined): string {
  const destination = safeNextPath(next);
  const afterPassword = login.tenant_selection_required ? tenantSelectionPath(destination) : destination;
  if (!login.force_password_change) return afterPassword;
  return afterPassword === "/" ? "/change-password" : `/change-password?next=${encodeURIComponent(afterPassword)}`;
}
