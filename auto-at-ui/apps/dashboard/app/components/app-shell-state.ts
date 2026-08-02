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
