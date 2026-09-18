import { create } from "zustand";

import {
  fetchCurrentUser,
  login as apiLogin,
  logout as apiLogout,
  register as apiRegister,
} from "@/api/auth";
import { setUnauthorizedHandler, toApiError } from "@/api/client";
import type { User } from "@/types";

export type AuthStatus = "idle" | "loading" | "authenticated" | "unauthenticated";

interface AuthState {
  user: User | null;
  status: AuthStatus;
  /** True once the startup session check has resolved (success or not). */
  initialized: boolean;
  error: string | null;
  /** Resolve the session on startup: stored token -> /me, else anonymous. */
  initialize: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, displayName: string) => Promise<void>;
  logout: () => Promise<void>;
  /** Backwards-compatible no-arg sign-out for legacy callers. */
  signOut: () => void;
}

let unauthorizedWired = false;

export const useAuthStore = create<AuthState>((set, get) => {
  if (!unauthorizedWired) {
    unauthorizedWired = true;
    // Expired/revoked token observed mid-session -> drop to anonymous.
    setUnauthorizedHandler(() => {
      if (get().status === "authenticated") set({ user: null, status: "unauthenticated" });
    });
  }

  return {
    user: null,
    status: "idle",
    initialized: false,
    error: null,

    initialize: async () => {
      if (get().status === "loading" || get().status === "authenticated") return;
      set({ status: "loading", error: null });
      try {
        const user = await fetchCurrentUser();
        set(user ? { user, status: "authenticated" } : { user: null, status: "unauthenticated" });
      } catch (e) {
        // fetchCurrentUser only throws on transport errors; 401 resolves via
        // the interceptor (token cleared) and lands here as anonymous.
        const err = toApiError(e);
        set({
          user: null,
          status: "unauthenticated",
          error: err.status === 0 ? err.message : null,
        });
      } finally {
        set({ initialized: true });
      }
    },

    login: async (email, password) => {
      set({ status: "loading", error: null });
      try {
        const { user } = await apiLogin(email, password);
        set({ user, status: "authenticated", error: null });
      } catch (e) {
        set({ user: null, status: "unauthenticated", error: toApiError(e).message });
        throw e;
      }
    },

    register: async (email, password, displayName) => {
      set({ status: "loading", error: null });
      try {
        const { user } = await apiRegister(email, password, displayName);
        set({ user, status: "authenticated", error: null });
      } catch (e) {
        set({ user: null, status: "unauthenticated", error: toApiError(e).message });
        throw e;
      }
    },

    logout: async () => {
      try {
        await apiLogout();
      } catch {
        // The credential is cleared inside apiLogout regardless; logout must
        // always land in the anonymous state, even offline.
      } finally {
        set({ user: null, status: "unauthenticated", error: null });
      }
    },

    signOut: () => {
      void get().logout();
    },
  };
});
