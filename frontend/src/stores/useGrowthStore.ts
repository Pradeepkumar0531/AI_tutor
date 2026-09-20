import { create } from "zustand";

import { toApiError } from "@/api/client";
import { growthApi, type GrowthHistoryPoint, type ProjectGrowth } from "@/api/growth";
import type { LoadStatus } from "./useSpacesStore";

interface GrowthState {
  /** Project owning every slice below (tutor-store scoping contract). */
  projectId: string | null;
  growth: ProjectGrowth | null;
  growthState: LoadStatus;
  history: GrowthHistoryPoint[];
  historyState: LoadStatus;
  error: string | null;
  fetchGrowth: (projectId: string) => Promise<void>;
  reset: () => void;
}

const initial = {
  projectId: null as string | null,
  growth: null as ProjectGrowth | null,
  growthState: "idle" as LoadStatus,
  history: [] as GrowthHistoryPoint[],
  historyState: "idle" as LoadStatus,
  error: null as string | null,
};

export const useGrowthStore = create<GrowthState>((set, get) => ({
  ...initial,

  fetchGrowth: async (projectId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ growthState: "loading", historyState: "loading", error: null });
    try {
      const [growth, history] = await Promise.all([
        growthApi.get(projectId),
        growthApi.history(projectId),
      ]);
      if (get().projectId !== projectId) return;
      set({ growth, growthState: "ready", history, historyState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ growthState: "error", historyState: "error", error: toApiError(e).message });
    }
  },

  reset: () => set(initial),
}));
