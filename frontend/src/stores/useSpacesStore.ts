import { create } from "zustand";

import { spacesApi } from "@/api/spaces";
import { toApiError } from "@/api/client";
import type { Space } from "@/types";

export type LoadStatus = "idle" | "loading" | "ready" | "error";

interface SpacesState {
  items: Space[];
  total: number;
  page: number;
  pageSize: number;
  search: string;
  includeArchived: boolean;
  status: LoadStatus;
  error: string | null;
  current: Space | null;
  /** Route identity owning `current`: responses for any other id are dropped,
   * and `reset()` (which nulls it) invalidates in-flight fetches. */
  currentId: string | null;
  fetch: (params?: { page?: number; search?: string; includeArchived?: boolean }) => Promise<void>;
  fetchOne: (id: string) => Promise<Space | null>;
  create: (input: { name: string; description?: string }) => Promise<Space>;
  update: (id: string, input: { name?: string; description?: string }) => Promise<Space>;
  archive: (id: string) => Promise<void>;
  restore: (id: string) => Promise<void>;
  reset: () => void;
}

const initial = {
  items: [] as Space[],
  total: 0,
  page: 1,
  pageSize: 20,
  search: "",
  includeArchived: false,
  status: "idle" as LoadStatus,
  error: null as string | null,
  current: null as Space | null,
  currentId: null as string | null,
};

export const useSpacesStore = create<SpacesState>((set, get) => {
  // Collapse duplicate concurrent list fetches (rapid navigation, StrictMode
  // remounts): identical in-flight params share one request instead of
  // storming the API. Settles (success or error) always release the slot.
  let inflight: { key: string; promise: Promise<void> } | null = null;

  return {
    ...initial,

    fetch: (params = {}) => {
      const page = params.page ?? 1;
      const search = params.search ?? get().search;
      const includeArchived = params.includeArchived ?? get().includeArchived;
      const key = JSON.stringify({ page, search, includeArchived });
      if (inflight && inflight.key === key) return inflight.promise;
      const promise = (async () => {
        set({ status: "loading", error: null, page, search, includeArchived });
        try {
          const res = await spacesApi.list({
            page,
            pageSize: get().pageSize,
            search,
            includeArchived,
          });
          set({ items: res.items, total: res.total, status: "ready" });
        } catch (e) {
          set({ status: "error", error: toApiError(e).message });
        } finally {
          if (inflight?.key === key) inflight = null;
        }
      })();
      inflight = { key, promise };
      return promise;
    },

    fetchOne: async (id) => {
      // Switching entities: drop the previous space synchronously so it can
      // never render under the new route while loading (same contract as the
      // project-scoped feature stores). `currentId` marks the wanted entity;
      // a late response for any other id — or after reset() — is discarded.
      if (get().current?.id !== id) set({ current: null });
      set({ currentId: id, status: "loading", error: null });
      try {
        const space = await spacesApi.get(id);
        if (get().currentId !== id) return null;        set((s) => ({
          current: space,
          items: s.items.some((i) => i.id === id)
            ? s.items.map((i) => (i.id === id ? space : i))
            : [...s.items, space],
          status: "ready",
        }));
        return space;
      } catch (e) {
        const err = toApiError(e);
        if (get().currentId !== id) return null;
        set({ status: "error", error: err.message, current: null });
        return null;
      }
    },

    create: async (input) => {
      const space = await spacesApi.create(input);
      // Prepend to the current page view instead of refetching the world.
      set((s) => ({ items: [space, ...s.items], total: s.total + 1 }));
      return space;
    },

    update: async (id, input) => {
      const space = await spacesApi.update(id, input);
      set((s) => ({
        items: s.items.map((i) => (i.id === id ? space : i)),
        current: s.current?.id === id ? space : s.current,
      }));
      return space;
    },

    archive: async (id) => {
      await spacesApi.archive(id);
      // Archived rows vanish from active listings: drop locally, refetch counts.
      set((s) => ({
        items: s.items.filter((i) => i.id !== id),
        total: Math.max(0, s.total - 1),
        current: s.current?.id === id ? null : s.current,
      }));
    },

    restore: async (id) => {
      await spacesApi.restore(id);
      // Re-run the current listing so the restored row (or its absence when
      // hidden) is reflected without guessing.
      const s = get();
      await s.fetch({ page: s.page, search: s.search, includeArchived: s.includeArchived });
    },

    reset: () => set(initial),
  };
});
