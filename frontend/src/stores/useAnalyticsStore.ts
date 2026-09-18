import { create } from "zustand";

import {
  analyticsApi,
  type ActivityDay,
  type ActivityItem,
  type DashboardSummary,
  type DateRange,
  type MasteryTrendPoint,
} from "@/api/analytics";
import type { LoadStatus } from "./useSpacesStore";

interface AnalyticsState {
  summary: DashboardSummary | null;
  summaryState: LoadStatus;
  activity: ActivityItem[];
  activityState: LoadStatus;
  activityByDay: ActivityDay[];
  masteryTrend: MasteryTrendPoint[];
  trendsState: LoadStatus;
  range: DateRange;
  error: string | null;
  fetchDashboard: (projectId: string, range?: DateRange) => Promise<void>;
  reset: () => void;
}

const initial = {
  summary: null as DashboardSummary | null,
  summaryState: "idle" as LoadStatus,
  activity: [] as ActivityItem[],
  activityState: "idle" as LoadStatus,
  activityByDay: [] as ActivityDay[],
  masteryTrend: [] as MasteryTrendPoint[],
  trendsState: "idle" as LoadStatus,
  range: "30d" as DateRange,
  error: null as string | null,
};

export const useAnalyticsStore = create<AnalyticsState>((set, get) => ({
  ...initial,

  fetchDashboard: async (projectId, range) => {
    const nextRange = range ?? get().range;
    set({
      summaryState: "loading",
      activityState: "loading",
      trendsState: "loading",
      range: nextRange,
      error: null,
    });
    const [summary, activity, activityByDay, masteryTrend] = await Promise.allSettled([
      analyticsApi.dashboard(projectId),
      analyticsApi.activity(projectId, { range: nextRange }),
      analyticsApi.activityByDay(projectId, nextRange),
      analyticsApi.masteryTrend(projectId),
    ]);
    // Graceful partial rendering: each section stands on its own result, so
    // one failed query never blanks the whole dashboard.
    const failures: string[] = [];
    if (summary.status === "fulfilled") {
      set({ summary: summary.value, summaryState: "ready" });
    } else {
      failures.push("summary");
      set({ summaryState: "error" });
    }
    if (activity.status === "fulfilled") {
      set({ activity: activity.value, activityState: "ready" });
    } else {
      failures.push("activity");
      set({ activityState: "error" });
    }
    if (activityByDay.status === "fulfilled" && masteryTrend.status === "fulfilled") {
      set({
        activityByDay: activityByDay.value,
        masteryTrend: masteryTrend.value,
        trendsState: "ready",
      });
    } else {
      failures.push("trends");
      set({ trendsState: "error" });
    }
    set({
      error:
        failures.length > 0
          ? `Some dashboard sections failed to load (${failures.join(", ")}).`
          : null,
    });
  },

  reset: () => set(initial),
}));
