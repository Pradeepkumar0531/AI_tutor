import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { recommendationsApi } from "@/api/recommendations";
import { RecommendationsSection } from "@/features/recommendations/components/RecommendationsSection";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useRecommendationsStore } from "@/stores/useRecommendationsStore";

// Only the HTTP boundary is mocked; mapping, stores, and components run for real.
vi.mock("@/api/recommendations", () => ({
  recommendationsApi: {
    list: vi.fn(),
    complete: vi.fn(),
    dismiss: vi.fn(),
  },
}));
vi.mock("@/api/growth", () => ({
  growthApi: {
    get: vi.fn(),
    history: vi.fn(),
  },
}));

const mockList = recommendationsApi.list as Mock;
const mockComplete = recommendationsApi.complete as Mock;
const mockDismiss = recommendationsApi.dismiss as Mock;

function reset() {
  useRecommendationsStore.getState().reset();
  useGrowthStore.getState().reset();
  vi.clearAllMocks();
}

const rec = {
  id: "r-1",
  projectId: "proj-1",
  conceptId: "c-tcp",
  conceptName: "TCP",
  materialId: "m-1",
  materialName: "Networks.pdf",
  type: "REVIEW_CONCEPT" as const,
  title: "Review TCP",
  description: "Revisit TCP.",
  reason: "Recent mistakes; mastery 38%.",
  actions: ["open_material", "practice_quiz"],
  priority: 72,
  status: "ACTIVE" as const,
  sourceAssessmentId: "a-1",
  createdAt: "",
  completedAt: null,
};

describe("recommendations store", () => {
  beforeEach(reset);

  it("loads the active list", async () => {
    mockList.mockResolvedValue([rec]);
    await useRecommendationsStore.getState().fetchList("proj-1");
    expect(useRecommendationsStore.getState().items).toHaveLength(1);
  });

  it("completes then reloads from the server", async () => {
    mockList.mockResolvedValue([rec]);
    mockComplete.mockResolvedValue({ ...rec, status: "COMPLETED" });
    mockList.mockResolvedValue([]);
    await useRecommendationsStore.getState().fetchList("proj-1");
    await useRecommendationsStore.getState().complete("proj-1", "r-1");
    expect(mockComplete).toHaveBeenCalledWith("proj-1", "r-1");
    expect(useRecommendationsStore.getState().items).toHaveLength(0);
  });

  it("records errors without crashing", async () => {
    mockList.mockRejectedValue(new Error("down"));
    await useRecommendationsStore.getState().fetchList("proj-1");
    expect(useRecommendationsStore.getState().listState).toBe("error");
  });
});

describe("RecommendationsSection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(
      <MemoryRouter>
        <RecommendationsSection projectId="proj-1" />
      </MemoryRouter>,
    );
  }

  it("renders cards with reason and backend-confirmed actions only", async () => {
    mockList.mockResolvedValue([rec]);
    renderSection();
    await waitFor(() => expect(screen.getByText("Review TCP")).toBeInTheDocument());
    expect(screen.getByText(/Recent mistakes/)).toBeInTheDocument();
    expect(screen.getByText("Priority 72")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Review Material" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Practice" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask Tutor" })).not.toBeInTheDocument();
  });

  it("shows the caught-up state when evidence exists but nothing is active", async () => {
    mockList.mockResolvedValue([]);
    const { growthApi } = await import("@/api/growth");
    (growthApi.get as Mock).mockResolvedValue({ hasEvidence: true });
    const { useGrowthStore: ugs } = await import("@/stores/useGrowthStore");
    ugs.setState({
      growth: {
        projectId: "proj-1",
        status: "STABLE",
        hasEvidence: true,
        overallMastery: 0.8,
        averageConfidence: 0.7,
        conceptsImproving: 0,
        conceptsStable: 2,
        conceptsRequiringAttention: 0,
        assessedConcepts: 2,
        assessmentCount: 1,
        questionsAnswered: 4,
        updatedAt: "",
        concepts: [],
      },
      growthState: "ready",
    });
    renderSection();
    await waitFor(() => expect(screen.getByText("You're caught up for now.")).toBeInTheDocument());
  });

  it("shows the cold-start state without evidence", async () => {
    mockList.mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
  });

  it("completes and dismisses through the server", async () => {
    mockList.mockResolvedValueOnce([rec]);
    mockList.mockResolvedValue([]);
    mockComplete.mockResolvedValue({ ...rec, status: "COMPLETED" });
    mockDismiss.mockResolvedValue({ ...rec, status: "DISMISSED" });
    renderSection();
    await waitFor(() => expect(screen.getByText("Review TCP")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Mark done" }));
    await waitFor(() => expect(mockComplete).toHaveBeenCalledWith("proj-1", "r-1"));
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
  });
});
