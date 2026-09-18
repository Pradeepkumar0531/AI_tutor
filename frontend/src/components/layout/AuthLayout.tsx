import { Link, Outlet } from "react-router-dom";
import { GraduationCap } from "lucide-react";

/** Minimal public layout for login/register: brand + centered card column. */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="flex h-16 items-center border-b bg-card px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <GraduationCap className="h-4 w-4" aria-hidden="true" />
          </span>
          <span className="leading-tight">
            <span className="block text-[15px] font-semibold tracking-tight">StudyAI</span>
            <span className="font-mono-tech block text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Learning
            </span>
          </span>
        </Link>
      </header>
      <main className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
