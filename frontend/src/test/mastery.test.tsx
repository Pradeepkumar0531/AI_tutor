import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { masteryApi } from "@/api/mastery";
import { MasterySection } from "@/features/mastery/components/MasterySection";
import { useMasteryStore } from "@/stores/useMasteryStore";

// Only the HTTP boundary is mocked; mapping, store, and components run for real.
vi.mock("@/api/mastery", () => ({
  masteryApi: {
    list: vi.fn(),
    detail: vi.fn(),
    history: vi.fn(),
  },
}));

const mockList = masteryApi.list as Mock;
const mockDetail = masteryApi.detail as Mock;
const mockHistory = masteryApi.history as Mock;

function reset() {
  useMasteryStore.getState().reset();
  vi.clearAllMocks();
}

const tcp = {
  conceptId: "c-tcp",
  conceptName: "TCP",
  masteryScore: 0.69,
  confidence: 0.78,
  trend: "IMPROVING" as const,
  evidenceCount: 4,
  recentPerformance: ["C", "C", "P"],
  hasEvidence: true,
  updatedAt: "",
};

const udp = {
  conceptId: "c-udp",
  conceptName: "UDP",
  masteryScore: 0.34,
  confidence: 0.5,
  trend: "DECLINING" as const,
  evidenceCount: 2,
  recentPerformance: ["I", "I"],
  hasEvidence: true,
  updatedAt: "",
};

const cold = {
  conceptId: "c-cold",
  conceptName: "Cold",
  masteryScore: 0.5,
  confidence: 0.2,
  trend: "STABLE" as const,
  evidenceCount: 0,
  recentPerformance: [],
  hasEvidence: false,
  updatedAt: null,
};

describe("mastery store", () => {
  beforeEach(reset);

  it("loads the list with sort", async () => {
    mockList.mockResolvedValue({ items: [udp, tcp], total: 2 });
    await useMasteryStore.getState().fetchList("proj-1");
    expect(mockList).toHaveBeenCalledWith("proj-1", { sort: "lowest" });
    expect(useMasteryStore.getState().items).toHaveLength(2);
    await useMasteryStore.getState().fetchList("proj-1", "name");
    expect(mockList).toHaveBeenLastCalledWith("proj-1", { sort: "name" });
  });

  it("opens detail plus history", async () => {
    mockList.mockResolvedValue({ items: [tcp], total: 1 });
    mockDetail.mockResolvedValue({ ...tcp, evidenceQuestions: 5, contributingAssessments: ["a1"] });
    mockHistory.mockResolvedValue([
      {
        id: "h1",
        assessmentId: "a1",
        previousScore: 0.5,
        newScore: 0.69,
        confidence: 0.78,
        createdAt: "",
      },
    ]);
    await useMasteryStore.getState().fetchList("proj-1");
    await useMasteryStore.getState().openDetail("proj-1", "c-tcp");
    const s = useMasteryStore.getState();
    expect(s.detail?.conceptName).toBe("TCP");
    expect(s.history).toHaveLength(1);
  });

  it("records list errors without crashing", async () => {
    mockList.mockRejectedValue(new Error("down"));
    await useMasteryStore.getState().fetchList("proj-1");
    const s = useMasteryStore.getState();
    expect(s.listState).toBe("error");
    expect(s.error).toContain("down");
  });
});

describe("MasterySection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(<MasterySection projectId="proj-1" />);
  }

  it("renders scores, confidence, trend, and recent performance", async () => {
    mockList.mockResolvedValue({ items: [udp, tcp], total: 2 });
    renderSection();
    await waitFor(() => expect(screen.getByText("TCP")).toBeInTheDocument());
    expect(screen.getByText("UDP")).toBeInTheDocument();
    expect(document.body.textContent).toContain("69%");
    expect(document.body.textContent).toContain("Recent: C C P");
    expect(screen.getByText("Improving")).toBeInTheDocument();
    expect(screen.getByText("Declining")).toBeInTheDocument();
  });

  it("never shows 0% for unevidenced concepts", async () => {
    mockList.mockResolvedValue({ items: [cold], total: 1 });
    renderSection();
    await waitFor(() => expect(screen.getByText("Cold")).toBeInTheDocument());
    expect(screen.getByText(/Not yet established/)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("0%");
  });

  it("shows an honest empty state with no mastery", async () => {
    mockList.mockResolvedValue({ items: [], total: 0 });
    renderSection();
    await waitFor(() => expect(screen.getByText("No mastery yet.")).toBeInTheDocument());
  });

  it("opens detail with history and evidence counts", async () => {
    mockList.mockResolvedValue({ items: [tcp], total: 1 });
    mockDetail.mockResolvedValue({ ...tcp, evidenceQuestions: 4, contributingAssessments: ["a1"] });
    mockHistory.mockResolvedValue([
      {
        id: "h1",
        assessmentId: "a1",
        previousScore: 0.5,
        newScore: 0.69,
        confidence: 0.78,
        createdAt: "",
      },
    ]);
    renderSection();
    await waitFor(() => expect(screen.getByText("TCP")).toBeInTheDocument());
    fireEvent.click(screen.getByText("TCP"));
    await waitFor(() => expect(screen.getByText("Concept: TCP")).toBeInTheDocument());
    expect(document.body.textContent).toContain("69%");
    expect(document.body.textContent).toContain("50% →");
    fireEvent.click(screen.getByText("All concepts"));
    await waitFor(() => expect(screen.queryByText("Concept: TCP")).not.toBeInTheDocument());
  });

  it("sorts by name on selection", async () => {
    mockList.mockResolvedValue({ items: [tcp], total: 1 });
    renderSection();
    await waitFor(() => expect(screen.getByText("TCP")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Sort"), { target: { value: "name" } });
    await waitFor(() => expect(mockList).toHaveBeenLastCalledWith("proj-1", { sort: "name" }));
  });
});
