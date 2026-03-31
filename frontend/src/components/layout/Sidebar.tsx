"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Brain,
  Bot,
  FlaskConical,
  LayoutDashboard,
  ChevronRight,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Nav item definition
// ─────────────────────────────────────────────────────────────────────────────

interface NavItem {
  label: string;
  href: string;
  icon: React.ReactNode;
  badge?: string;
  exact?: boolean;
}

interface NavGroup {
  groupLabel?: string;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    items: [
      {
        label: "Pipeline",
        href: "/pipeline",
        icon: <Zap className="w-4 h-4" />,
      },
    ],
  },
  {
    groupLabel: "Admin",
    items: [
      {
        label: "LLM Profiles",
        href: "/admin/llm",
        icon: <Brain className="w-4 h-4" />,
      },
      {
        label: "Agent Configs",
        href: "/admin/agents",
        icon: <Bot className="w-4 h-4" />,
      },
    ],
  },
  {
    groupLabel: "Dev",
    items: [
      {
        label: "API Docs",
        href: "http://localhost:8000/docs",
        icon: <FlaskConical className="w-4 h-4" />,
        badge: "Ext",
      },
    ],
  },
];

// ─────────────────────────────────────────────────────────────────────────────
// NavLink
// ─────────────────────────────────────────────────────────────────────────────

interface NavLinkProps {
  item: NavItem;
  pathname: string;
  collapsed: boolean;
}

function NavLink({ item, pathname, collapsed }: NavLinkProps) {
  const isExternal = item.href.startsWith("http");
  const isActive = item.exact
    ? pathname === item.href
    : pathname === item.href || pathname.startsWith(item.href + "/");

  const linkClass = cn(
    // Layout
    "group relative flex items-center gap-3 rounded-lg transition-all duration-150",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec] focus-visible:ring-offset-1 focus-visible:ring-offset-[#18202F]",
    // Spacing
    collapsed ? "justify-center px-2.5 py-2.5" : "px-3 py-2.5",
    // Active vs idle
    isActive
      ? "bg-[#135bec]/15 text-white"
      : "text-[#92a4c9] hover:bg-[#1e2a3d] hover:text-white"
  );

  const content = (
    <>
      {/* Active indicator bar */}
      {isActive && (
        <span
          className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-[#135bec] rounded-full"
          aria-hidden="true"
        />
      )}

      {/* Icon */}
      <span
        className={cn(
          "shrink-0 transition-colors duration-150",
          isActive ? "text-[#5b9eff]" : "text-[#92a4c9] group-hover:text-white"
        )}
      >
        {item.icon}
      </span>

      {/* Label + Badge */}
      {!collapsed && (
        <span className="flex-1 flex items-center justify-between gap-2 min-w-0">
          <span className="truncate text-sm font-medium">{item.label}</span>
          {item.badge && (
            <span className="shrink-0 px-1.5 py-0.5 text-[10px] font-semibold rounded bg-[#2b3b55] text-[#92a4c9]">
              {item.badge}
            </span>
          )}
          {isExternal && (
            <ChevronRight
              className="shrink-0 w-3 h-3 opacity-40"
              aria-hidden="true"
            />
          )}
        </span>
      )}

      {/* Tooltip when collapsed */}
      {collapsed && (
        <span
          className={cn(
            "absolute left-full ml-3 px-2.5 py-1.5 rounded-lg",
            "bg-[#18202F] border border-[#2b3b55] text-white text-xs font-medium",
            "whitespace-nowrap shadow-xl",
            "opacity-0 pointer-events-none",
            "group-hover:opacity-100 group-hover:pointer-events-auto",
            "transition-opacity duration-150 z-50"
          )}
          role="tooltip"
        >
          {item.label}
        </span>
      )}
    </>
  );

  if (isExternal) {
    return (
      <a
        href={item.href}
        target="_blank"
        rel="noopener noreferrer"
        className={linkClass}
        aria-label={collapsed ? item.label : undefined}
      >
        {content}
      </a>
    );
  }

  return (
    <Link
      href={item.href}
      className={linkClass}
      aria-current={isActive ? "page" : undefined}
      aria-label={collapsed ? item.label : undefined}
    >
      {content}
    </Link>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Sidebar
// ─────────────────────────────────────────────────────────────────────────────

export interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  className?: string;
}

export function Sidebar({
  collapsed = false,
  onToggleCollapse,
  className,
}: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        // Layout
        "relative flex flex-col h-full",
        // Visual
        "bg-[#18202F] border-r border-[#2b3b55]",
        // Transition
        "transition-[width] duration-200 ease-in-out",
        // Width
        collapsed ? "w-16" : "w-56",
        className
      )}
      aria-label="Main navigation"
    >
      {/* ── Logo / Brand ── */}
      <div
        className={cn(
          "flex items-center gap-3 border-b border-[#2b3b55]",
          "shrink-0",
          collapsed ? "px-2.5 py-4 justify-center" : "px-4 py-4"
        )}
      >
        {/* Icon mark */}
        <div className="shrink-0 w-8 h-8 rounded-xl bg-[#135bec] flex items-center justify-center shadow-lg shadow-[#135bec]/30">
          <LayoutDashboard className="w-4 h-4 text-white" aria-hidden="true" />
        </div>

        {/* Wordmark */}
        {!collapsed && (
          <div className="min-w-0">
            <p className="text-sm font-bold text-white tracking-tight leading-none">
              Auto-AT
            </p>
            <p className="text-[11px] text-[#92a4c9] leading-none mt-0.5">
              AI Test Pipeline
            </p>
          </div>
        )}
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto px-2 py-3 space-y-5">
        {NAV_GROUPS.map((group, gi) => (
          <div key={gi}>
            {/* Group label */}
            {group.groupLabel && !collapsed && (
              <p className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-widest text-[#3d5070]">
                {group.groupLabel}
              </p>
            )}

            {/* Group separator when collapsed */}
            {group.groupLabel && collapsed && gi > 0 && (
              <div
                className="mx-auto w-6 h-px bg-[#2b3b55] mb-2"
                aria-hidden="true"
              />
            )}

            {/* Items */}
            <ul className="space-y-0.5" role="list">
              {group.items.map((item) => (
                <li key={item.href}>
                  <NavLink
                    item={item}
                    pathname={pathname}
                    collapsed={collapsed}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      {/* ── Collapse toggle ── */}
      {onToggleCollapse && (
        <div className="shrink-0 border-t border-[#2b3b55] p-2">
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            className={cn(
              "w-full flex items-center gap-2 rounded-lg px-2.5 py-2",
              "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
              "transition-colors duration-150",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
              collapsed ? "justify-center" : "justify-start"
            )}
          >
            <ChevronRight
              className={cn(
                "w-4 h-4 transition-transform duration-200",
                !collapsed && "rotate-180"
              )}
              aria-hidden="true"
            />
            {!collapsed && (
              <span className="text-sm font-medium">Collapse</span>
            )}
          </button>
        </div>
      )}
    </aside>
  );
}

export default Sidebar;
