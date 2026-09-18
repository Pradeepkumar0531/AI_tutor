import { create } from "zustand";

import { toApiError } from "@/api/client";
import { projectsApi, type ProjectInput, type ProjectUpdateInput } from "@/api/projects";
import type { Project } from "@/types";
import type { LoadStatus } from "./useSpacesStore";

interface ProjectsState {
  items: Project[];
  total: number;
  page: number;
  pageSize: number;
  spaceId: string | null;
  search: string;
  includeArchived: boolean;
  status: LoadStatus;
  error: string | null;
  current: Project | null;
  fetch: (params?: {
    spaceId?: string | null;
    page?: number;
    search?: string;
    includeArchived?: boolean;
  }) => Promise<void>;
  fetchOne: (id: string) => Promise<Project | null>;
  create: (input: ProjectInput) => Promise<Project>;
  update: (id: string, input: ProjectUpdateInput) => Promise<Project>;
  archive: (id: string) => Promise<void>;
  restore: (id: string) => Promise<void>;
  reset: () => void;
}

const initial = {
  items: [] as Project[],
  total: 0,
  page: 1,
  pageSize: 20,
  spaceId: null as string | null,
  search: "",
  includeArchived: false,
  status: "idle" as LoadStatus,
  error: null as string | null,
  current: null as Project | null,
};

export const useProjectsStore = create<ProjectsState>((set, get) => {
  // Collapse duplicate concurrent list fetches (rapid navigation, StrictMode
  // remounts): identical in-flight params share one request instead of
  // storming the API. Settles (success or error) always release the slot.
  let inflight: { key: string; promise: Promise<void> } | null = null;

  return {
    ...initial,

    fetch: (params = {}) => {
      const page = params.page ?? 1;
      const spaceId = params.spaceId !== undefined ? params.spaceId : get().spaceId;
      const search = params.search ?? get().search;
      const includeArchived = params.includeArchived ?? get().includeArchived;
      const key = JSON.stringify({ page, spaceId, search, includeArchived });
      if (inflight && inflight.key === key) return inflight.promise;
      const promise = (async () => {
        set({ status: "loading", error: null, page, spaceId, search, includeArchived });
        try {
          const res = await projectsApi.list({
            spaceId: spaceId ?? undefined,
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
      set({ status: "loading", error: null });
      try {
        const project = await projectsApi.get(id);
        set((s) => ({
          current: project,
          items: s.items.some((i) => i.id === id)
            ? s.items.map((i) => (i.id === id ? project : i))
            : [...s.items, project],
          status: "ready",
        }));
        return project;
      } catch (e) {
        set({ status: "error", error: toApiError(e).message, current: null });
        return null;
      }
    },

    create: async (input) => {
      const project = await projectsApi.create(input);
      set((s) => ({ items: [project, ...s.items], total: s.total + 1 }));
      return project;
    },

    update: async (id, input) => {
      const project = await projectsApi.update(id, input);
      set((s) => ({
        items: s.items.map((i) => (i.id === id ? project : i)),
        current: s.current?.id === id ? project : s.current,
      }));
      return project;
    },

    archive: async (id) => {
      await projectsApi.archive(id);
      set((s) => ({
        items: s.items.filter((i) => i.id !== id),
        total: Math.max(0, s.total - 1),
        current: s.current?.id === id ? null : s.current,
      }));
    },

    restore: async (id) => {
      await projectsApi.restore(id);
      const s = get();
      await s.fetch({
        spaceId: s.spaceId,
        page: s.page,
        search: s.search,
        includeArchived: s.includeArchived,
      });
    },

    reset: () => set(initial),
  };
});
