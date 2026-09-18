import { create } from "zustand";

import { toApiError } from "@/api/client";
import { knowledgeApi } from "@/api/knowledge";
import type { Concept, KnowledgeSearchResponse, KnowledgeStatus, KnowledgeTotals } from "@/types";
import type { LoadStatus } from "./useSpacesStore";

interface KnowledgeState {
  status: KnowledgeStatus | null;
  totals: KnowledgeTotals | null;
  statusState: LoadStatus;
  concepts: Concept[];
  conceptsTotal: number;
  conceptsState: LoadStatus;
  search: KnowledgeSearchResponse | null;
  searchState: LoadStatus;
  error: string | null;
  fetchStatus: (projectId: string) => Promise<void>;
  fetchConcepts: (projectId: string, page?: number) => Promise<void>;
  runSearch: (projectId: string, query: string) => Promise<void>;
  reprocess: (projectId: string, materialId: string) => Promise<void>;
  reset: () => void;
}

const initial = {
  status: null as KnowledgeStatus | null,
  totals: null as KnowledgeTotals | null,
  statusState: "idle" as LoadStatus,
  concepts: [] as Concept[],
  conceptsTotal: 0,
  conceptsState: "idle" as LoadStatus,
  search: null as KnowledgeSearchResponse | null,
  searchState: "idle" as LoadStatus,
  error: null as string | null,
};

export const useKnowledgeStore = create<KnowledgeState>((set) => ({
  ...initial,

  fetchStatus: async (projectId) => {
    set({ statusState: "loading", error: null });
    try {
      const res = await knowledgeApi.status(projectId);
      set({ status: res.status, totals: res.totals, statusState: "ready" });
    } catch (e) {
      set({ statusState: "error", error: toApiError(e).message });
    }
  },

  fetchConcepts: async (projectId, page = 1) => {
    set({ conceptsState: "loading", error: null });
    try {
      const res = await knowledgeApi.concepts(projectId, { page });
      set({ concepts: res.items, conceptsTotal: res.total, conceptsState: "ready" });
    } catch (e) {
      set({ conceptsState: "error", error: toApiError(e).message });
    }
  },

  runSearch: async (projectId, query) => {
    set({ searchState: "loading", error: null });
    try {
      const res = await knowledgeApi.search(projectId, { query });
      set({ search: res, searchState: "ready" });
    } catch (e) {
      set({ searchState: "error", error: toApiError(e).message });
    }
  },

  reprocess: async (projectId, materialId) => {
    await knowledgeApi.reprocess(projectId, materialId);
    await useKnowledgeStore.getState().fetchStatus(projectId);
  },

  reset: () => set(initial),
}));
