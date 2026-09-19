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

/** Centered top navigation: brand + tagline, nav row, account top-right. */
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

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      "rounded-md px-4 py-2 text-sm font-medium transition-colors",
      "text-primary-foreground/80 hover:bg-white/10 hover:text-primary-foreground",
      "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70",
      isActive && "bg-white/15 text-primary-foreground",
    );

  return (
    <header className="shrink-0 bg-[linear-gradient(180deg,hsl(var(--primary-hover)),hsl(var(--primary)))] text-primary-foreground shadow-[0_1px_12px_rgba(15,49,90,0.35)]">
      <div className="relative mx-auto w-full max-w-6xl px-4 sm:px-6">
        {/* Mobile menu button (left) */}
        <div className="absolute inset-y-0 left-4 flex items-center sm:left-6 md:hidden">
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            aria-expanded={menuOpen}
            className="rounded-md p-2 text-primary-foreground/90 transition-colors hover:bg-white/10"
          >
            {menuOpen ? (
              <X className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Menu className="h-5 w-5" aria-hidden="true" />
            )}
          </button>
        </div>

        {/* Account (top-right, real auth state) */}
        <div className="absolute inset-y-0 right-4 flex items-center sm:right-6">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <button
                type="button"
                aria-label={`Account: ${displayName}`}
                className="flex items-center gap-2 rounded-md px-1.5 py-1 text-left transition-colors hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
              >
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-[11px] font-semibold text-primary-foreground"
                  aria-hidden="true"
                >
                  {initials(displayName)}
                </span>
                <span className="hidden min-w-0 leading-tight sm:block">
                  <span className="block max-w-32 truncate text-[13px] font-medium">
                    {displayName}
                  </span>
                  <span className="block text-[10px] uppercase tracking-[0.12em] text-primary-foreground/70">
                    {user?.role ?? "learner"}
                  </span>
                </span>
                <ChevronDown
                  className="hidden h-4 w-4 text-primary-foreground/70 sm:block"
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

        {/* Centered brand */}
        <div className="flex flex-col items-center px-14 pb-1 pt-5 text-center md:px-40">
          <span className="text-3xl font-bold tracking-tight sm:text-4xl">
            AI Learning Companion
          </span>
          <span className="font-mono-tech mt-1 text-[10px] uppercase tracking-[0.18em] text-primary-foreground/70">
            Learn&nbsp;&nbsp;→&nbsp;&nbsp;Practice&nbsp;&nbsp;→&nbsp;&nbsp;Master
          </span>
        </div>

        {/* Desktop nav row */}
        <nav className="hidden items-center justify-center gap-1 pb-3 md:flex" aria-label="Primary">
          {links.map((l) => (
            <NavLink key={l.to} to={l.to} end={l.end} className={linkClass}>
              {l.label}
            </NavLink>
          ))}
        </nav>

        {/* Mobile nav panel */}
        {menuOpen ? (
          <nav className="flex flex-col gap-1 pb-4 md:hidden" aria-label="Primary mobile">
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
