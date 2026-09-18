import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { growthApi } from "@/api/growth";
import { GrowthSection } from "@/features/growth/components/GrowthSection";
import { useGrowthStore } from "@/stores/useGrowthStore";

// Only the HTTP boundary is mocked; mapping, store, and components run for real.
vi.mock("@/api/growth", () => ({
  growthApi: {
    get: vi.fn(),
    history: vi.fn(),
  },
}));

const mockGet = growthApi.get as Mock;
const mockHistory = growthApi.history as Mock;

function reset() {
  useGrowthStore.getState().reset();
  vi.clearAllMocks();
}

const growth = {
  projectId: "proj-1",
  status: "IMPROVING" as const,
  hasEvidence: true,
  overallMastery: 0.71,
  averageConfidence: 0.63,
  conceptsImproving: 2,
  conceptsStable: 1,
  conceptsRequiringAttention: 1,
  assessedConcepts: 4,
  assessmentCount: 3,
  questionsAnswered: 12,
  updatedAt: "",
  concepts: [],
};

const history = [
  { date: "2026-01-01T00:00:00Z", score: 0.4, assessmentId: "a1" },
  { date: "2026-01-05T00:00:00Z", score: 0.71, assessmentId: "a2" },
];

describe("growth store", () => {
  beforeEach(reset);

  it("loads growth and history together", async () => {
    mockGet.mockResolvedValue(growth);
    mockHistory.mockResolvedValue(history);
    await useGrowthStore.getState().fetchGrowth("proj-1");
    const s = useGrowthStore.getState();
    expect(s.growth?.status).toBe("IMPROVING");
    expect(s.history).toHaveLength(2);
  });

  it("records errors without crashing", async () => {
    mockGet.mockRejectedValue(new Error("down"));
    mockHistory.mockResolvedValue([]);
    await useGrowthStore.getState().fetchGrowth("proj-1");
    const s = useGrowthStore.getState();
    expect(s.growthState).toBe("error");
    expect(s.error).toContain("down");
  });
});

describe("GrowthSection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(<GrowthSection projectId="proj-1" />);
  }

  it("renders overall mastery, status, distribution, and chart", async () => {
    mockGet.mockResolvedValue(growth);
    mockHistory.mockResolvedValue(history);
    renderSection();
    await waitFor(() => expect(screen.getByText("71%")).toBeInTheDocument());
    expect(screen.getAllByText("Improving")).toHaveLength(2); // badge + distribution
    expect(document.body.textContent).toContain("Requiring Attention");
    expect(document.body.textContent).toContain("assessments");
    expect(document.body.textContent).toContain("Confidence 63%");
    expect(document.body.textContent).toContain("evidence");
    await waitFor(() =>
      expect(screen.getByLabelText("Overall mastery over time")).toBeInTheDocument(),
    );
  });

  it("shows an honest cold-start empty state", async () => {
    mockGet.mockResolvedValue({ ...growth, hasEvidence: false, assessedConcepts: 0 });
    mockHistory.mockResolvedValue([]);
    renderSection();
    await waitFor(() =>
      expect(
        screen.getByText("Growth will appear after you complete your first assessment."),
      ).toBeInTheDocument(),
    );
    expect(document.body.textContent).not.toContain("0%");
  });

  it("asks for more assessments when history is thin", async () => {
    mockGet.mockResolvedValue(growth);
    mockHistory.mockResolvedValue([history[0]]);
    renderSection();
    await waitFor(() =>
      expect(
        screen.getByText("Complete more assessments to see your growth over time."),
      ).toBeInTheDocument(),
    );
  });
});
