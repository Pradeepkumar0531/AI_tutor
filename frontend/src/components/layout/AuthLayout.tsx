import { Link, Outlet } from "react-router-dom";

/** Minimal public layout for login/register: centered brand + card column. */
export function AuthLayout() {
  return (
    <div className="flex min-h-screen flex-col bg-background">
      <header className="hero-dark flex items-center justify-center border-b px-4 py-5 text-primary-foreground sm:px-6">
        <Link to="/" className="text-center leading-tight">
          <span className="font-mono-tech block text-[10px] uppercase tracking-[0.18em] text-primary-foreground/70">
            Learn&nbsp;&nbsp;→&nbsp;&nbsp;Practice&nbsp;&nbsp;→&nbsp;&nbsp;Master
          </span>
          <span className="mt-2 block text-2xl font-bold tracking-tight sm:text-3xl">
            AI Learning Companion
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
