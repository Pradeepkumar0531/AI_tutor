import { create } from "zustand";

import { toApiError } from "@/api/client";
import { recommendationsApi, type Recommendation } from "@/api/recommendations";
import type { LoadStatus } from "./useSpacesStore";

interface RecommendationsState {
  /** Project owning every slice below (tutor-store scoping contract). */
  projectId: string | null;
  items: Recommendation[];
  listState: LoadStatus;
  busyId: string | null;
  error: string | null;
  fetchList: (projectId: string) => Promise<void>;
  complete: (projectId: string, id: string) => Promise<void>;
  dismiss: (projectId: string, id: string) => Promise<void>;
  reset: () => void;
}

const initial = {
  projectId: null as string | null,
  items: [] as Recommendation[],
  listState: "idle" as LoadStatus,
  busyId: null as string | null,
  error: null as string | null,
};

export const useRecommendationsStore = create<RecommendationsState>((set, get) => ({
  ...initial,

  fetchList: async (projectId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ listState: "loading", error: null });
    try {
      const items = await recommendationsApi.list(projectId);
      if (get().projectId !== projectId) return;
      set({ items, listState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ listState: "error", error: toApiError(e).message });
    }
  },

  complete: async (projectId, id) => {
    if (get().projectId !== projectId) return;
    if (get().busyId) return;
    set({ busyId: id, error: null });
    try {
      await recommendationsApi.complete(projectId, id);
      // Server is the source of truth: re-read the active list so completed
      // rows leave exactly once, in order.
      const items = await recommendationsApi.list(projectId);
      if (get().projectId !== projectId) return;
      set({ items, listState: "ready", busyId: null });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ busyId: null, error: toApiError(e).message });
    }
  },

  dismiss: async (projectId, id) => {
    if (get().projectId !== projectId) return;
    if (get().busyId) return;
    set({ busyId: id, error: null });
    try {
      await recommendationsApi.dismiss(projectId, id);
      const items = await recommendationsApi.list(projectId);
      if (get().projectId !== projectId) return;
      set({ items, listState: "ready", busyId: null });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ busyId: null, error: toApiError(e).message });
    }
  },

  reset: () => set(initial),
}));
