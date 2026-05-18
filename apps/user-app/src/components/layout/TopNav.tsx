"use client";

import React, { useState, useRef, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@auto-at/shared";
import { LogOut, User as UserIcon, ChevronDown } from "lucide-react";

export function TopNav() {
  const { user, logout, isAdmin } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = () => {
    logout();
    router.replace("/login");
  };

  if (!user) return null;

  return (
    <header className="sticky top-0 z-30 h-14 border-b border-[#2b3b55] bg-[#101622]/95 backdrop-blur supports-[backdrop-filter]:bg-[#101622]/80">
      <div className="page-container h-full flex items-center justify-between gap-4">
        <Link
          href="/pipelines"
          className="flex items-center gap-2 font-bold tracking-tight text-white"
        >
          <span className="w-7 h-7 rounded-md bg-blue-600 grid place-items-center text-xs">
            AT
          </span>
          <span>Auto-AT</span>
          <span className="text-xs text-gray-500 font-normal">User Portal</span>
        </Link>

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-sm text-gray-200 hover:bg-[#18202F] transition"
          >
            <UserIcon className="w-4 h-4" />
            <span>{user.full_name || user.username}</span>
            <span
              className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${
                isAdmin
                  ? "bg-blue-500/15 text-blue-300"
                  : "bg-gray-500/15 text-gray-300"
              }`}
            >
              {user.role.toUpperCase()}
            </span>
            <ChevronDown className="w-3.5 h-3.5 text-gray-400" />
          </button>

          {open && (
            <div className="absolute right-0 mt-2 w-44 rounded-md border border-[#2b3b55] bg-[#18202F] shadow-lg py-1 text-sm">
              {isAdmin && (
                <a
                  href={
                    process.env.NEXT_PUBLIC_ADMIN_APP_URL ||
                    "http://localhost:3001"
                  }
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block px-3 py-2 text-gray-200 hover:bg-[#263450]"
                >
                  Open Admin Console
                </a>
              )}
              <button
                type="button"
                onClick={handleLogout}
                className="w-full text-left px-3 py-2 text-red-300 hover:bg-[#263450] inline-flex items-center gap-2"
              >
                <LogOut className="w-3.5 h-3.5" /> Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export default TopNav;
