import * as React from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { LoadingState } from "@/components/ui";
import { PageContainer } from "@/components/layout/PageHeader";
import { useAuthStore } from "@/stores/useAuthStore";

function useEnsureInitialized() {
  const status = useAuthStore((s) => s.status);
  React.useEffect(() => {
    if (status === "idle") void useAuthStore.getState().initialize();
  }, [status]);
}

/**
 * Gates protected areas. The loading shell shows only until the startup
 * session check resolves; form-driven "loading" states must never unmount
 * the page tree (that would wipe form state and server errors).
 */
export function RequireAuth() {
  const initialized = useAuthStore((s) => s.initialized);
  const status = useAuthStore((s) => s.status);
  const location = useLocation();
  useEnsureInitialized();

  if (!initialized) {
    return (
      <PageContainer>
        <LoadingState label="Restoring your session…" />
      </PageContainer>
    );
  }
  if (status !== "authenticated") {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <Outlet />;
}

/**
 * Server-side RBAC is the real gate (every /api/v1/admin/* route depends on
 * require_admin); this only avoids showing the admin shell to learners.
 * A learner reaching /admin by URL still gets a proper 403-driven denial.
 */
export function RequireAdmin() {
  const initialized = useAuthStore((s) => s.initialized);
  const status = useAuthStore((s) => s.status);
  const user = useAuthStore((s) => s.user);
  useEnsureInitialized();

  if (!initialized) {
    return (
      <PageContainer>
        <LoadingState label="Restoring your session…" />
      </PageContainer>
    );
  }
  if (status !== "authenticated" || user?.role !== "admin") {
    return (
      <PageContainer>
        <div className="rounded-lg border p-6">
          <h1 className="text-lg font-semibold">Admin access required</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Your account does not have administrator privileges.
          </p>
        </div>
      </PageContainer>
    );
  }
  return <Outlet />;
}

/** Redirects already-authenticated users away from login/register. */
export function RedirectIfAuthenticated() {
  const initialized = useAuthStore((s) => s.initialized);
  const status = useAuthStore((s) => s.status);
  useEnsureInitialized();

  if (!initialized) {
    return (
      <PageContainer>
        <LoadingState label="Restoring your session…" />
      </PageContainer>
    );
  }
  if (status === "authenticated") return <Navigate to="/" replace />;
  return <Outlet />;
}
