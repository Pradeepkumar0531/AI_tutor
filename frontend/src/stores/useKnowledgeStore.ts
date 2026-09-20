import { create } from "zustand";

import { toApiError } from "@/api/client";
import { knowledgeApi } from "@/api/knowledge";
import type { Concept, KnowledgeSearchResponse, KnowledgeStatus, KnowledgeTotals } from "@/types";
import type { LoadStatus } from "./useSpacesStore";

interface KnowledgeState {
  /** Project owning every slice below (tutor-store scoping contract). */
  projectId: string | null;
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
  projectId: null as string | null,
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

export const useKnowledgeStore = create<KnowledgeState>((set, get) => ({
  ...initial,

  fetchStatus: async (projectId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ statusState: "loading", error: null });
    try {
      const res = await knowledgeApi.status(projectId);
      if (get().projectId !== projectId) return;
      set({ status: res.status, totals: res.totals, statusState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ statusState: "error", error: toApiError(e).message });
    }
  },

  fetchConcepts: async (projectId, page = 1) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ conceptsState: "loading", error: null });
    try {
      const res = await knowledgeApi.concepts(projectId, { page });
      if (get().projectId !== projectId) return;
      set({ concepts: res.items, conceptsTotal: res.total, conceptsState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ conceptsState: "error", error: toApiError(e).message });
    }
  },

  runSearch: async (projectId, query) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ searchState: "loading", error: null });
    try {
      const res = await knowledgeApi.search(projectId, { query });
      if (get().projectId !== projectId) return;
      set({ search: res, searchState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ searchState: "error", error: toApiError(e).message });
    }
  },

  reprocess: async (projectId, materialId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    await knowledgeApi.reprocess(projectId, materialId);
    await get().fetchStatus(projectId);
  },

  reset: () => set(initial),
}));
