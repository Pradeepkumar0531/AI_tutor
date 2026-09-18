import { create } from "zustand";

import { toApiError } from "@/api/client";
import {
  masteryApi,
  type MasteryDetail,
  type MasteryHistoryItem,
  type MasteryItem,
} from "@/api/mastery";
import type { LoadStatus } from "./useSpacesStore";

interface MasteryState {
  items: MasteryItem[];
  total: number;
  listState: LoadStatus;
  sort: string;
  detail: MasteryDetail | null;
  detailState: LoadStatus;
  history: MasteryHistoryItem[];
  historyState: LoadStatus;
  error: string | null;
  fetchList: (projectId: string, sort?: string) => Promise<void>;
  openDetail: (projectId: string, conceptId: string) => Promise<void>;
  backToList: () => void;
  reset: () => void;
}

const initial = {
  items: [] as MasteryItem[],
  total: 0,
  listState: "idle" as LoadStatus,
  sort: "lowest",
  detail: null as MasteryDetail | null,
  detailState: "idle" as LoadStatus,
  history: [] as MasteryHistoryItem[],
  historyState: "idle" as LoadStatus,
  error: null as string | null,
};

export const useMasteryStore = create<MasteryState>((set) => ({
  ...initial,

  fetchList: async (projectId, sort) => {
    const nextSort = sort ?? useMasteryStore.getState().sort;
    set({ listState: "loading", sort: nextSort, error: null });
    try {
      const { items, total } = await masteryApi.list(projectId, { sort: nextSort });
      set({ items, total, listState: "ready" });
    } catch (e) {
      set({ listState: "error", error: toApiError(e).message });
    }
  },

  openDetail: async (projectId, conceptId) => {
    set({ detailState: "loading", historyState: "loading", error: null });
    try {
      const [detail, history] = await Promise.all([
        masteryApi.detail(projectId, conceptId),
        masteryApi.history(projectId, conceptId),
      ]);
      set({ detail, detailState: "ready", history, historyState: "ready" });
    } catch (e) {
      set({ detailState: "error", historyState: "error", error: toApiError(e).message });
    }
  },

  backToList: () => set({ detail: null, detailState: "idle", history: [], historyState: "idle" }),

  reset: () => set(initial),
}));
