"use client";

import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/layout/Sidebar";
import {
  Brain,
  Bot,
  Zap,
  Menu,
  X,
  Bell,
  ExternalLink,
  ChevronRight,
  Layers,
} from "lucide-react";
import { cn } from "@/lib/utils";

// ─────────────────────────────────────────────────────────────────────────────
// Breadcrumb helpers
// ─────────────────────────────────────────────────────────────────────────────

interface BreadcrumbSegment {
  label: string;
  href?: string;
  icon?: React.ReactNode;
}

function resolveBreadcrumbs(pathname: string): BreadcrumbSegment[] {
  const crumbs: BreadcrumbSegment[] = [
    { label: "Auto-AT", href: "/", icon: <Zap className="w-3.5 h-3.5" /> },
  ];

  if (pathname.startsWith("/admin")) {
    crumbs.push({ label: "Admin", href: "/admin/llm" });

    if (pathname.startsWith("/admin/llm")) {
      crumbs.push({
        label: "LLM Profiles",
        icon: <Brain className="w-3.5 h-3.5" />,
      });
    } else if (pathname.startsWith("/admin/agents")) {
      crumbs.push({
        label: "Agent Configs",
        icon: <Bot className="w-3.5 h-3.5" />,
      });
    } else if (pathname.startsWith("/admin/stages")) {
      crumbs.push({
        label: "Stage Configs",
        icon: <Layers className="w-3.5 h-3.5" />,
      });
    }
  } else if (pathname.startsWith("/pipeline")) {
    crumbs.push({
      label: "Pipeline",
      icon: <Zap className="w-3.5 h-3.5" />,
    });
  }

  return crumbs;
}

// ─────────────────────────────────────────────────────────────────────────────
// Navbar
// ─────────────────────────────────────────────────────────────────────────────

interface NavbarProps {
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
  mobileMenuOpen: boolean;
  onToggleMobileMenu: () => void;
  pathname: string;
}

function Navbar({
  sidebarCollapsed,
  onToggleSidebar,
  mobileMenuOpen,
  onToggleMobileMenu,
  pathname,
}: NavbarProps) {
  const breadcrumbs = resolveBreadcrumbs(pathname);

  return (
    <header
      className={cn(
        "sticky top-0 z-30 flex items-center h-14 shrink-0",
        "bg-[#18202F]/95 backdrop-blur-md",
        "border-b border-[#2b3b55]",
        "px-4 gap-3",
      )}
    >
      {/* Desktop: sidebar collapse toggle */}
      <button
        type="button"
        onClick={onToggleSidebar}
        aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        className={cn(
          "hidden md:flex items-center justify-center",
          "w-8 h-8 rounded-lg",
          "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
          "shrink-0",
        )}
      >
        <Menu className="w-4 h-4" aria-hidden="true" />
      </button>

      {/* Mobile: hamburger */}
      <button
        type="button"
        onClick={onToggleMobileMenu}
        aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
        aria-expanded={mobileMenuOpen}
        className={cn(
          "flex md:hidden items-center justify-center",
          "w-8 h-8 rounded-lg shrink-0",
          "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
          "transition-colors duration-150",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
        )}
      >
        {mobileMenuOpen ? (
          <X className="w-4 h-4" aria-hidden="true" />
        ) : (
          <Menu className="w-4 h-4" aria-hidden="true" />
        )}
      </button>

      {/* Vertical divider */}
      <div
        className="hidden md:block h-5 w-px bg-[#2b3b55] shrink-0"
        aria-hidden="true"
      />

      {/* Breadcrumbs */}
      <nav
        aria-label="Breadcrumb"
        className="flex items-center gap-1.5 min-w-0 flex-1"
      >
        <ol className="flex items-center gap-1.5 min-w-0">
          {breadcrumbs.map((crumb, i) => {
            const isLast = i === breadcrumbs.length - 1;

            return (
              <li key={i} className="flex items-center gap-1.5 min-w-0">
                {/* Separator */}
                {i > 0 && (
                  <ChevronRight
                    className="w-3 h-3 text-[#3d5070] shrink-0"
                    aria-hidden="true"
                  />
                )}

                {/* Crumb */}
                {crumb.href && !isLast ? (
                  <Link
                    href={crumb.href}
                    className={cn(
                      "flex items-center gap-1.5 text-sm shrink-0",
                      "text-[#92a4c9] hover:text-white",
                      "transition-colors duration-150",
                      "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#135bec] rounded",
                    )}
                  >
                    {crumb.icon && (
                      <span className="shrink-0" aria-hidden="true">
                        {crumb.icon}
                      </span>
                    )}
                    <span className="truncate">{crumb.label}</span>
                  </Link>
                ) : (
                  <span
                    className={cn(
                      "flex items-center gap-1.5 text-sm min-w-0",
                      isLast ? "text-white font-medium" : "text-[#92a4c9]",
                    )}
                    aria-current={isLast ? "page" : undefined}
                  >
                    {crumb.icon && (
                      <span className="shrink-0" aria-hidden="true">
                        {crumb.icon}
                      </span>
                    )}
                    <span className="truncate">{crumb.label}</span>
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {/* Right actions */}
      <div className="flex items-center gap-2 shrink-0 ml-auto">
        {/* API Docs link */}
        <a
          href="http://localhost:8000/docs"
          target="_blank"
          rel="noopener noreferrer"
          className={cn(
            "hidden sm:flex items-center gap-1.5 h-8 px-3 rounded-lg text-sm",
            "text-[#92a4c9] hover:text-white border border-transparent",
            "hover:bg-[#1e2a3d] hover:border-[#2b3b55]",
            "transition-all duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
          )}
        >
          <ExternalLink className="w-3.5 h-3.5" aria-hidden="true" />
          <span>API Docs</span>
        </a>

        {/* Notification placeholder */}
        <button
          type="button"
          aria-label="Notifications"
          className={cn(
            "relative flex items-center justify-center w-8 h-8 rounded-lg",
            "text-[#92a4c9] hover:text-white hover:bg-[#1e2a3d]",
            "transition-colors duration-150",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#135bec]",
          )}
        >
          <Bell className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>
    </header>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Mobile nav overlay
// ─────────────────────────────────────────────────────────────────────────────

interface MobileNavOverlayProps {
  open: boolean;
  onClose: () => void;
}

function MobileNavOverlay({ open, onClose }: MobileNavOverlayProps) {
  // Lock body scroll while menu is open
  React.useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  if (!open) return null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* Slide-in sidebar */}
      <div
        className={cn(
          "fixed inset-y-0 left-0 z-50 md:hidden",
          "animate-in slide-in-from-right duration-200",
        )}
        style={{ animationName: "slideInFromLeft" }}
      >
        <Sidebar collapsed={false} />
      </div>
    </>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Admin Layout
// ─────────────────────────────────────────────────────────────────────────────

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const toggleSidebar = () => setSidebarCollapsed((prev) => !prev);
  const toggleMobileMenu = () => setMobileMenuOpen((prev) => !prev);
  const closeMobileMenu = () => setMobileMenuOpen(false);

  // Close mobile menu on route change
  React.useEffect(() => {
    closeMobileMenu();
  }, [pathname]);

  return (
    <div className="flex h-dvh overflow-hidden bg-[#101622]">
      {/* ── Desktop Sidebar ── */}
      <div className="hidden md:flex shrink-0">
        <Sidebar
          collapsed={sidebarCollapsed}
          onToggleCollapse={toggleSidebar}
        />
      </div>

      {/* ── Mobile nav overlay ── */}
      <MobileNavOverlay open={mobileMenuOpen} onClose={closeMobileMenu} />

      {/* ── Main column ── */}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        {/* Top navbar */}
        <Navbar
          sidebarCollapsed={sidebarCollapsed}
          onToggleSidebar={toggleSidebar}
          mobileMenuOpen={mobileMenuOpen}
          onToggleMobileMenu={toggleMobileMenu}
          pathname={pathname}
        />

        {/* Page content */}
        <main
          id="main-content"
          className="flex-1 overflow-y-auto"
          tabIndex={-1}
        >
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-6">{children}</div>
        </main>
      </div>
    </div>
  );
}
