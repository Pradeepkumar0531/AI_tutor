import { Outlet } from "react-router-dom";

import { ErrorBoundary } from "@/components/common/ErrorBoundary";
import { TopNav } from "@/components/layout/TopNav";
import { ToastHost } from "@/components/ui";

export function AppShell() {
  return (
    <ToastHost>
      <div className="flex min-h-screen flex-col bg-background">
        <TopNav />
        <main className="flex-1">
          <ErrorBoundary>
            <Outlet />
          </ErrorBoundary>
        </main>
      </div>
    </ToastHost>
  );
}
