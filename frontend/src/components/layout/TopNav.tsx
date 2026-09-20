import { ChevronDown, LogOut, Menu, X } from "lucide-react";
import * as React from "react";
import { NavLink, useNavigate } from "react-router-dom";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui";
import { useAuthStore } from "@/stores/useAuthStore";
import { cn } from "@/lib/utils";

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return (parts[0]?.slice(0, 2) ?? "?").toUpperCase();
  return `${parts[0]?.[0] ?? ""}${parts[parts.length - 1]?.[0] ?? ""}`.toUpperCase();
}

/**
 * Top of the app, two visually separate regions:
 *  1. Dark-gradient hero — brand identity only (caption, gap, title).
 *  2. Its own light navigation bar — links + account, never inside the hero.
 */
export function TopNav() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const isAdmin = user?.role === "admin";
  const [menuOpen, setMenuOpen] = React.useState(false);

  const displayName = user?.displayName || user?.email || "Account";

  async function handleSignOut() {
    await logout();
    setMenuOpen(false);
    navigate("/login", { replace: true });
  }

  const links = [
    { to: "/", label: "Home", end: true },
    { to: "/spaces", label: "Spaces", end: false },
    { to: "/analytics", label: "Analytics", end: false },
    ...(isAdmin ? [{ to: "/admin", label: "Admin", end: false }] : []),
  ];

  // Active route: solid dark-blue pill with white text — visible without
  // relying on text color alone. Hover/focus keep the label readable in
  // every state (inactive, hover, active, active+hover, focus).
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "rounded-md px-4 py-2 text-sm font-medium transition-colors",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary",
      isActive
        ? "bg-primary text-primary-foreground hover:bg-primary-hover"
        : "text-muted-foreground hover:bg-primary/10 hover:text-foreground",
    );

  return (
    <header className="shrink-0">
      {/* 1 — Hero: product identity. Caption first, deliberate gap, then the
        dominant title. Outfit throughout (inherited from body). */}
      <div className="bg-[linear-gradient(180deg,hsl(var(--primary-hover)),hsl(var(--primary)))] text-primary-foreground">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center px-4 pb-6 pt-6 text-center sm:px-6">
          <span className="font-mono-tech text-[10px] uppercase tracking-[0.22em] text-primary-foreground/60">
            Learn&nbsp;&nbsp;→&nbsp;&nbsp;Practice&nbsp;&nbsp;→&nbsp;&nbsp;Master
          </span>
          <span className="mt-3 text-4xl font-bold tracking-tight sm:text-5xl">
            AI Learning Companion
          </span>
        </div>
      </div>

      {/* 2 — Navigation bar: its own light region below the hero. */}
      <div className="border-b bg-card/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-2 px-4 sm:px-6">
          {/* Mobile menu button */}
          <div className="flex items-center md:hidden">
            <button
              type="button"
              onClick={() => setMenuOpen((v) => !v)}
              aria-label={menuOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={menuOpen}
              className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            >
              {menuOpen ? (
                <X className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Menu className="h-5 w-5" aria-hidden="true" />
              )}
            </button>
          </div>

          {/* Desktop nav row */}
          <nav className="hidden items-center gap-1 py-2 md:flex" aria-label="Primary">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={linkClass}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          {/* Mobile spacer keeps the account pinned right */}
          <span className="md:hidden" aria-hidden="true" />

          {/* Account (real auth state) */}
          <div className="flex items-center py-1.5">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={`Account: ${displayName}`}
                  className="flex items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <span
                    className="flex h-8 w-8 items-center justify-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary"
                    aria-hidden="true"
                  >
                    {initials(displayName)}
                  </span>
                  <span className="hidden min-w-0 leading-tight sm:block">
                    <span className="block max-w-32 truncate text-[13px] font-medium">
                      {displayName}
                    </span>
                    <span className="block text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                      {user?.role ?? "learner"}
                    </span>
                  </span>
                  <ChevronDown
                    className="hidden h-4 w-4 text-muted-foreground sm:block"
                    aria-hidden="true"
                  />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-60">
                {user ? (
                  <DropdownMenuItem disabled>
                    <span className="flex min-w-0 flex-col">
                      <span className="truncate font-medium">{displayName}</span>
                      <span className="truncate text-xs text-muted-foreground">{user.email}</span>
                      <span className="font-mono-tech mt-0.5 text-[10px] uppercase tracking-[0.12em] text-muted-foreground">
                        {user.role}
                      </span>
                    </span>
                  </DropdownMenuItem>
                ) : null}
                <DropdownMenuItem onSelect={() => void handleSignOut()}>
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>

        {/* Mobile nav panel */}
        {menuOpen ? (
          <nav
            className="mx-auto flex w-full max-w-6xl flex-col gap-1 px-4 pb-3 sm:px-6 md:hidden"
            aria-label="Primary mobile"
          >
            {links.map((l) => (
              <NavLink
                key={l.to}
                to={l.to}
                end={l.end}
                onClick={() => setMenuOpen(false)}
                className={linkClass}
              >
                {l.label}
              </NavLink>
            ))}
          </nav>
        ) : null}
      </div>
    </header>
  );
}
