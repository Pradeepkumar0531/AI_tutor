import { create } from "zustand";

import { homeApi, type GlobalSummary, type HomeData } from "@/api/home";
import { toApiError } from "@/api/client";
import type { LoadStatus } from "./useSpacesStore";

interface HomeState {
  home: HomeData | null;
  homeState: LoadStatus;
  summary: GlobalSummary | null;
  summaryState: LoadStatus;
  error: string | null;
  fetchHome: () => Promise<void>;
  fetchSummary: () => Promise<void>;
  reset: () => void;
}

const initial = {
  home: null as HomeData | null,
  homeState: "idle" as LoadStatus,
  summary: null as GlobalSummary | null,
  summaryState: "idle" as LoadStatus,
  error: null as string | null,
};

export const useHomeStore = create<HomeState>((set) => {
  // Collapse duplicate concurrent fetches (StrictMode remounts, rapid
  // re-navigation): identical in-flight calls share one request.
  let homeInflight: Promise<void> | null = null;
  let summaryInflight: Promise<void> | null = null;

  return {
    ...initial,

    fetchHome: () => {
      if (homeInflight) return homeInflight;
      homeInflight = (async () => {
        set({ homeState: "loading", error: null });
        try {
          const home = await homeApi.home();
          set({ home, homeState: "ready" });
        } catch (e) {
          set({ homeState: "error", error: toApiError(e).message });
        } finally {
          homeInflight = null;
        }
      })();
      return homeInflight;
    },

    fetchSummary: () => {
      if (summaryInflight) return summaryInflight;
      summaryInflight = (async () => {
        set({ summaryState: "loading", error: null });
        try {
          const summary = await homeApi.summary();
          set({ summary, summaryState: "ready" });
        } catch (e) {
          set({ summaryState: "error", error: toApiError(e).message });
        } finally {
          summaryInflight = null;
        }
      })();
      return summaryInflight;
    },

    reset: () => set(initial),
  };
});
