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
  /** Project owning every slice below; switching projects clears stale
   * slices synchronously and drops late responses (tutor-store contract). */
  projectId: string | null;
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
  projectId: null as string | null,
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

export const useMasteryStore = create<MasteryState>((set, get) => ({
  ...initial,

  fetchList: async (projectId, sort) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    const nextSort = sort ?? useMasteryStore.getState().sort;
    set({ listState: "loading", sort: nextSort, error: null });
    try {
      const { items, total } = await masteryApi.list(projectId, { sort: nextSort });
      if (get().projectId !== projectId) return;
      set({ items, total, listState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ listState: "error", error: toApiError(e).message });
    }
  },

  openDetail: async (projectId, conceptId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ detailState: "loading", historyState: "loading", error: null });
    try {
      const [detail, history] = await Promise.all([
        masteryApi.detail(projectId, conceptId),
        masteryApi.history(projectId, conceptId),
      ]);
      if (get().projectId !== projectId) return;
      set({ detail, detailState: "ready", history, historyState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ detailState: "error", historyState: "error", error: toApiError(e).message });
    }
  },

  backToList: () => set({ detail: null, detailState: "idle", history: [], historyState: "idle" }),

  reset: () => set(initial),
}));
