import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { MemoryRouter } from "react-router-dom";

import { homeApi } from "@/api/home";
import { AnalyticsPage } from "@/app/pages/AnalyticsPage";
import { HomePage } from "@/app/pages/HomePage";
import { useHomeStore } from "@/stores/useHomeStore";

vi.mock("@/api/home", () => ({
  homeApi: { home: vi.fn(), summary: vi.fn() },
}));

const mockHome = homeApi.home as Mock;
const mockSummary = homeApi.summary as Mock;

function reset() {
  useHomeStore.getState().reset();
  vi.clearAllMocks();
}

const homeData = {
  continueLearning: {
    projectId: "p-1",
    projectName: "Algebra",
    spaceId: "s-1",
    materials: 2,
    nextAction: {
      kind: "recommendation",
      title: "Practice equations",
      reason: "Weak concept.",
      projectId: "p-1",
      recommendationId: "r-1",
    },
  },
  recentProjects: [{ id: "p-1", name: "Algebra", spaceId: "s-1", updatedAt: null }],
  progress: {
    projects: 1,
    materials: 2,
    materialsReady: 2,
    assessments: 1,
    questionsAnswered: 5,
    masteryAvg: 62.5,
    masteryConcepts: 4,
  },
  attention: [{ projectId: "p-1", concept: "Fractions", change: -12 }],
  recommendedAction: {
    kind: "recommendation",
    title: "Practice equations",
    reason: "Weak concept.",
    projectId: "p-1",
    recommendationId: "r-1",
  },
};

const emptyHome = {
  continueLearning: null,
  recentProjects: [],
  progress: {
    projects: 0,
    materials: 0,
    materialsReady: 0,
    assessments: 0,
    questionsAnswered: 0,
    masteryAvg: 0,
    masteryConcepts: 0,
  },
  attention: [],
  recommendedAction: null,
};

describe("HomePage", () => {
  beforeEach(reset);

  it("answers where/app/how/next with real navigation targets", async () => {
    mockHome.mockResolvedValue(homeData);
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getAllByText("Algebra").length).toBeGreaterThan(0));
    expect(screen.getByText("What should I do next?")).toBeInTheDocument();
    expect(screen.getByText("Practice equations")).toBeInTheDocument();
    expect(screen.getByText("Fractions")).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links.some((l) => l.getAttribute("href") === "/projects/p-1")).toBe(true);
  });

  it("shows honest empty states for cold-start users", async () => {
    mockHome.mockResolvedValue(emptyHome);
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Nothing to continue yet")).toBeInTheDocument());
    expect(screen.getByText("No projects yet.")).toBeInTheDocument();
  });

  it("shows the error state with retry", async () => {
    mockHome.mockRejectedValue(new Error("down"));
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Could not load home")).toBeInTheDocument());
  });

  it("degrades to live summary stats when home fails but summary succeeds", async () => {
    mockHome.mockRejectedValue(new Error("timeout"));
    mockSummary.mockResolvedValue({
      projects: 2,
      materials: 5,
      materialsReady: 4,
      assessments: 3,
      questionsAnswered: 20,
      tutorMessages: 11,
      masteryAvg: 70,
      masteryConcepts: 6,
      attention: [{ projectId: "p-1", concept: "Fractions", change: -5 }],
      activeRecommendations: 2,
      recentProjectIds: ["p-1"],
      lastActivityAt: null,
    });
    render(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    );
    // Error banner with retry stays visible…
    await waitFor(() => expect(screen.getByText("Could not load home")).toBeInTheDocument());
    // …but real summary stats still render instead of a blank page.
    await waitFor(() => expect(screen.getByLabelText("Partial home data")).toBeInTheDocument());
    expect(screen.getByText("Fractions")).toBeInTheDocument();
    expect(screen.getByText("Continue learning is temporarily unavailable")).toBeInTheDocument();
  });
});

describe("AnalyticsPage", () => {
  beforeEach(reset);

  it("renders global aggregates", async () => {
    mockSummary.mockResolvedValue({
      projects: 2,
      materials: 5,
      materialsReady: 4,
      assessments: 3,
      questionsAnswered: 20,
      tutorMessages: 11,
      masteryAvg: 70,
      masteryConcepts: 6,
      attention: [{ projectId: "p-1", concept: "Fractions", change: -5 }],
      activeRecommendations: 2,
      recentProjectIds: ["p-1"],
      lastActivityAt: null,
    });
    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Fractions")).toBeInTheDocument());
    expect(screen.getByText("Global analytics")).toBeInTheDocument();
  });

  it("shows an honest empty state with no projects", async () => {
    mockSummary.mockResolvedValue({
      projects: 0,
      materials: 0,
      materialsReady: 0,
      assessments: 0,
      questionsAnswered: 0,
      tutorMessages: 0,
      masteryAvg: 0,
      masteryConcepts: 0,
      attention: [],
      activeRecommendations: 0,
      recentProjectIds: [],
      lastActivityAt: null,
    });
    render(
      <MemoryRouter>
        <AnalyticsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("No learning data yet")).toBeInTheDocument());
  });
});
