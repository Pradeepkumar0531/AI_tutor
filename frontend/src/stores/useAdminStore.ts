import { create } from "zustand";

import {
  adminApi,
  type ActivityFilters,
  type AdminAiSummaryItem,
  type AdminEvaluationRun,
  type AdminEvaluationSummary,
  type AdminEvent,
  type AdminHealth,
  type AdminJob,
  type AdminOverview,
  type AdminUser,
  type Page,
} from "@/api/admin";
import { toApiError } from "@/api/client";
import type { LoadStatus } from "./useSpacesStore";

interface AdminState {
  overview: AdminOverview | null;
  overviewState: LoadStatus;
  users: Page<AdminUser> | null;
  usersState: LoadStatus;
  journey: unknown | null;
  journeyState: LoadStatus;
  journeyId: string | null;
  activity: Page<AdminEvent> | null;
  activityState: LoadStatus;
  jobs: Page<AdminJob> | null;
  jobsState: LoadStatus;
  health: AdminHealth | null;
  healthState: LoadStatus;
  aiSummary: AdminAiSummaryItem[];
  aiState: LoadStatus;
  evalSummary: AdminEvaluationSummary | null;
  evalState: LoadStatus;
  evalRuns: AdminEvaluationRun[];
  running: boolean;
  error: string | null;
  fetchOverview: () => Promise<void>;
  fetchUsers: (search?: string, offset?: number) => Promise<void>;
  fetchJourney: (userId: string) => Promise<void>;
  fetchActivity: (filters?: ActivityFilters, offset?: number) => Promise<void>;
  fetchJobs: (status?: string, offset?: number) => Promise<void>;
  fetchHealth: () => Promise<void>;
  fetchAi: (userId?: string) => Promise<void>;
  fetchEval: () => Promise<void>;
  runEval: () => Promise<void>;
  reset: () => void;
}

const initial = {
  overview: null as AdminOverview | null,
  overviewState: "idle" as LoadStatus,
  users: null as Page<AdminUser> | null,
  usersState: "idle" as LoadStatus,
  journey: null as unknown | null,
  journeyState: "idle" as LoadStatus,
  journeyId: null as string | null,
  activity: null as Page<AdminEvent> | null,
  activityState: "idle" as LoadStatus,
  jobs: null as Page<AdminJob> | null,
  jobsState: "idle" as LoadStatus,
  health: null as AdminHealth | null,
  healthState: "idle" as LoadStatus,
  aiSummary: [] as AdminAiSummaryItem[],
  aiState: "idle" as LoadStatus,
  evalSummary: null as AdminEvaluationSummary | null,
  evalState: "idle" as LoadStatus,
  evalRuns: [] as AdminEvaluationRun[],
  running: false,
  error: null as string | null,
};

async function load<T>(setState: (s: LoadStatus, v?: T, e?: string) => void, fn: () => Promise<T>) {
  setState("loading");
  try {
    setState("ready", await fn());
  } catch (e) {
    setState("error", undefined, toApiError(e).message);
  }
}

export const useAdminStore = create<AdminState>((set) => ({
  ...initial,

  fetchOverview: async () =>
    load<AdminOverview>(
      (s, v, e) => set({ overviewState: s, overview: v ?? null, error: e ?? null }),
      () => adminApi.overview(),
    ),

  fetchUsers: async (search = "", offset = 0) =>
    load<Page<AdminUser>>(
      (s, v, e) => set({ usersState: s, users: v ?? null, error: e ?? null }),
      () => adminApi.users(25, offset, search),
    ),

  fetchJourney: async (userId: string) =>
    load<unknown>(
      (s, v, e) =>
        set({ journeyState: s, journey: v ?? null, journeyId: userId, error: e ?? null }),
      () => adminApi.userJourney(userId),
    ),

  fetchActivity: async (filters = {}, offset = 0) =>
    load<Page<AdminEvent>>(
      (s, v, e) => set({ activityState: s, activity: v ?? null, error: e ?? null }),
      () => adminApi.activity({ ...filters, offset }),
    ),

  fetchJobs: async (status, offset = 0) =>
    load<Page<AdminJob>>(
      (s, v, e) => set({ jobsState: s, jobs: v ?? null, error: e ?? null }),
      () => adminApi.jobs(status, 25, offset),
    ),

  fetchHealth: async () =>
    load<AdminHealth>(
      (s, v, e) => set({ healthState: s, health: v ?? null, error: e ?? null }),
      () => adminApi.health(),
    ),

  fetchAi: async (userId?: string) =>
    load<AdminAiSummaryItem[]>(
      (s, v, e) => set({ aiState: s, aiSummary: v ?? [], error: e ?? null }),
      () => adminApi.aiSummary(userId),
    ),

  fetchEval: async () => {
    set({ evalState: "loading", error: null });
    try {
      const [evalSummary, evalRuns] = await Promise.all([
        adminApi.evaluationSummary(),
        adminApi.evaluationRuns(),
      ]);
      set({ evalSummary, evalRuns, evalState: "ready" });
    } catch (e) {
      set({ evalState: "error", error: toApiError(e).message });
    }
  },

  runEval: async () => {
    set({ running: true, error: null });
    try {
      await adminApi.runEvaluations();
      const [evalSummary, evalRuns] = await Promise.all([
        adminApi.evaluationSummary(),
        adminApi.evaluationRuns(),
      ]);
      set({ evalSummary, evalRuns, evalState: "ready", running: false });
    } catch (e) {
      set({ running: false, error: toApiError(e).message });
    }
  },

  reset: () => set(initial),
}));
