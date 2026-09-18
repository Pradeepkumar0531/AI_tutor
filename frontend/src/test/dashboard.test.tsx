import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { analyticsApi } from "@/api/analytics";
import { DashboardSection } from "@/features/dashboard/components/DashboardSection";
import { useAnalyticsStore } from "@/stores/useAnalyticsStore";

// Only the HTTP boundary is mocked; mapping, store, and components run for real.
vi.mock("@/api/analytics", () => ({
  analyticsApi: {
    dashboard: vi.fn(),
    activity: vi.fn(),
    activityByDay: vi.fn(),
    masteryTrend: vi.fn(),
  },
}));

const mockDashboard = analyticsApi.dashboard as Mock;
const mockActivity = analyticsApi.activity as Mock;
const mockByDay = analyticsApi.activityByDay as Mock;
const mockTrend = analyticsApi.masteryTrend as Mock;

function reset() {
  useAnalyticsStore.getState().reset();
  vi.clearAllMocks();
}

const summary = {
  projectId: "proj-1",
  projectName: "Algebra",
  materialsCount: 4,
  materialsReady: 4,
  materialsFailed: 0,
  documentsCount: 4,
  pagesCount: 183,
  chunksCount: 421,
  imagesCount: 37,
  conceptsCount: 82,
  assessmentCount: 6,
  questionsAnswered: 71,
  questionsCorrect: 50,
  questionsPartial: 12,
  questionsIncorrect: 9,
  averageAssessmentScore: 0.68,
  overallMastery: 0.68,
  masteryConfidence: 0.61,
  growthStatus: "IMPROVING" as const,
  activeRecommendations: 3,
  tutorConversations: 5,
  tutorMessages: 24,
  lastActivityAt: "2026-09-01T00:00:00Z",
  hasLearningEvidence: true,
};

const activity = [
  {
    id: "e1",
    eventType: "ASSESSMENT_COMPLETED",
    createdAt: "2026-09-01T00:00:00Z",
    resourceId: "a1",
    metadata: { score: 85 },
    summary: "Completed assessment — 85%",
  },
  {
    id: "e2",
    eventType: "MATERIAL_UPLOADED",
    createdAt: "2026-08-30T00:00:00Z",
    resourceId: "m1",
    metadata: { name: "Notes.pdf" },
    summary: "Uploaded — Notes.pdf",
  },
];

const byDay = [
  { date: "2026-08-30", count: 1 },
  { date: "2026-09-01", count: 5 },
];

const trend = [
  { date: "2026-08-25T00:00:00Z", score: 0.4, assessmentId: "a0" },
  { date: "2026-09-01T00:00:00Z", score: 0.68, assessmentId: "a1" },
];

function healthy() {
  mockDashboard.mockResolvedValue(summary);
  mockActivity.mockResolvedValue(activity);
  mockByDay.mockResolvedValue(byDay);
  mockTrend.mockResolvedValue(trend);
}

describe("analytics store", () => {
  beforeEach(reset);

  it("loads all dashboard slices together", async () => {
    healthy();
    await useAnalyticsStore.getState().fetchDashboard("proj-1");
    const s = useAnalyticsStore.getState();
    expect(s.summary?.assessmentCount).toBe(6);
    expect(s.activity).toHaveLength(2);
    expect(s.activityByDay).toHaveLength(2);
    expect(s.masteryTrend).toHaveLength(2);
    expect(s.error).toBeNull();
  });

  it("passes the date range through and isolates failures per section", async () => {
    healthy();
    mockActivity.mockRejectedValueOnce(new Error("feed down"));
    await useAnalyticsStore.getState().fetchDashboard("proj-1", "7d");
    expect(mockActivity).toHaveBeenCalledWith("proj-1", { range: "7d" });
    expect(mockByDay).toHaveBeenCalledWith("proj-1", "7d");
    const s = useAnalyticsStore.getState();
    expect(s.summary?.projectName).toBe("Algebra");
    expect(s.summaryState).toBe("ready");
    expect(s.activityState).toBe("error");
    expect(s.trendsState).toBe("ready");
    expect(s.error).toContain("activity");
  });
});

describe("DashboardSection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(<DashboardSection projectId="proj-1" />);
  }

  it("renders real summary cards with links to existing sections", async () => {
    healthy();
    renderSection();
    await waitFor(() => expect(screen.getByText("68%")).toBeInTheDocument());
    expect(screen.getByText("Improving")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("82")).toBeInTheDocument();
    const masteryLink = screen.getByText("68%").closest("a");
    expect(masteryLink?.getAttribute("href")).toBe("../growth");
  });

  it("renders activity chart, mastery trend, and timeline from real data", async () => {
    healthy();
    renderSection();
    await waitFor(() =>
      expect(screen.getByLabelText("Daily learning activity")).toBeInTheDocument(),
    );
    expect(screen.getByLabelText("Assessment scores over time")).toBeInTheDocument();
    expect(screen.getByText("Completed assessment — 85%")).toBeInTheDocument();
    expect(screen.getByText("Uploaded — Notes.pdf")).toBeInTheDocument();
  });

  it("shows honest cold start without fake zeros", async () => {
    mockDashboard.mockResolvedValue({ ...summary, hasLearningEvidence: false });
    mockActivity.mockResolvedValue([]);
    mockByDay.mockResolvedValue([]);
    mockTrend.mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(screen.getByText("No learning evidence yet.")).toBeInTheDocument());
    expect(document.body.textContent).not.toContain("0%");
  });

  it("shows thin-history guidance instead of a fabricated trend", async () => {
    healthy();
    mockTrend.mockResolvedValue([trend[0]]);
    renderSection();
    await waitFor(() =>
      expect(
        screen.getByText("Complete more assessments to see your mastery trend."),
      ).toBeInTheDocument(),
    );
  });

  it("retries after failure", async () => {
    mockDashboard.mockRejectedValueOnce(new Error("down"));
    mockActivity.mockResolvedValue([]);
    mockByDay.mockResolvedValue([]);
    mockTrend.mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(screen.getByText("Dashboard unavailable")).toBeInTheDocument());
    mockDashboard.mockResolvedValue(summary);
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("68%")).toBeInTheDocument());
  });
});
