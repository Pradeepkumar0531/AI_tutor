import { MemoryRouter } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { KnowledgeSection } from "@/features/knowledge/components/KnowledgeSection";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";

// Only the HTTP boundary is mocked; mapping, stores, and components run for real.
vi.mock("@/api/knowledge", () => ({
  knowledgeApi: {
    status: vi.fn(),
    concepts: vi.fn(),
    concept: vi.fn(),
    search: vi.fn(),
    reprocess: vi.fn(),
  },
}));

import { knowledgeApi } from "@/api/knowledge";

const mockStatus = knowledgeApi.status as Mock;
const mockConcepts = knowledgeApi.concepts as Mock;
const mockSearch = knowledgeApi.search as Mock;

function reset() {
  useKnowledgeStore.getState().reset();
  vi.clearAllMocks();
}

const readyStatus = {
  project_id: "proj-1",
  status: "READY",
  totals: { chunks_total: 4, chunks_embedded: 4, concepts: 2, materials_ready: 1 },
};

const conceptList = {
  items: [
    {
      id: "c1",
      projectId: "proj-1",
      name: "Mitosis",
      description: "Cell division.",
      createdAt: "",
      updatedAt: "",
    },
  ],
  total: 1,
  page: 1,
  page_size: 20,
};

describe("knowledge store", () => {
  beforeEach(reset);

  it("loads status and concepts", async () => {
    mockStatus.mockResolvedValue(readyStatus);
    mockConcepts.mockResolvedValue(conceptList);
    const store = useKnowledgeStore.getState();
    await store.fetchStatus("proj-1");
    await store.fetchConcepts("proj-1");
    const s = useKnowledgeStore.getState();
    expect(s.status).toBe("READY");
    expect(s.totals?.concepts).toBe(2);
    expect(s.concepts).toHaveLength(1);
  });

  it("records search errors without crashing", async () => {
    mockSearch.mockRejectedValue(new Error("down"));
    await useKnowledgeStore.getState().runSearch("proj-1", "mitosis");
    const s = useKnowledgeStore.getState();
    expect(s.searchState).toBe("error");
    expect(s.error).toContain("down");
  });
});

describe("KnowledgeSection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(
      <MemoryRouter>
        <KnowledgeSection projectId="proj-1" />
      </MemoryRouter>,
    );
  }

  it("renders status, counts, and concepts", async () => {
    mockStatus.mockResolvedValue(readyStatus);
    mockConcepts.mockResolvedValue(conceptList);
    renderSection();
    await waitFor(() => expect(screen.getByText("Mitosis")).toBeInTheDocument());
    expect(screen.getByText("READY")).toBeInTheDocument();
    expect(screen.getByText(/4\/4 chunks embedded/)).toBeInTheDocument();
  });

  it("shows an honest empty state with no concepts", async () => {
    mockStatus.mockResolvedValue({
      ...readyStatus,
      status: "PENDING",
      totals: { chunks_total: 0, chunks_embedded: 0, concepts: 0, materials_ready: 0 },
    });
    mockConcepts.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    renderSection();
    await waitFor(() => expect(screen.getByText("No concepts yet.")).toBeInTheDocument());
  });

  it("shows search results with citations", async () => {
    mockStatus.mockResolvedValue(readyStatus);
    mockConcepts.mockResolvedValue(conceptList);
    mockSearch.mockResolvedValue({
      query: "mitosis",
      results: [
        {
          chunk_id: "ch1",
          document_id: "d1",
          material_id: "m1",
          material_name: "Cell Notes",
          text: "Mitosis divides the cell.",
          page_start: 3,
          page_end: 3,
          similarity: 0.92,
        },
      ],
      citations: [
        {
          chunk_id: "ch1",
          document_id: "d1",
          material_id: "m1",
          material_name: "Cell Notes",
          page_start: 3,
          page_end: 3,
          label: "Cell Notes — Page 3",
        },
      ],
      context: "ctx",
      insufficient_evidence: false,
    });
    renderSection();
    fireEvent.change(screen.getByLabelText("Search project knowledge"), {
      target: { value: "mitosis" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText("Mitosis divides the cell.")).toBeInTheDocument());
    expect(screen.getByText("Cell Notes — Page 3")).toBeInTheDocument();
    expect(screen.getByText(/92% match/)).toBeInTheDocument();
  });

  it("shows insufficient evidence explicitly", async () => {
    mockStatus.mockResolvedValue(readyStatus);
    mockConcepts.mockResolvedValue(conceptList);
    mockSearch.mockResolvedValue({
      query: "zzz",
      results: [],
      citations: [],
      context: "",
      insufficient_evidence: true,
    });
    renderSection();
    fireEvent.change(screen.getByLabelText("Search project knowledge"), {
      target: { value: "zzz" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText("Not enough evidence.")).toBeInTheDocument());
    expect(
      screen.getByText(/couldn't find enough evidence in this project's materials/),
    ).toBeInTheDocument();
  });

  it("expands concept provenance via the detail endpoint", async () => {
    mockStatus.mockResolvedValue(readyStatus);
    // List carries names only (real API contract: ConceptRead has no materials).
    mockConcepts.mockResolvedValue(conceptList);
    (knowledgeApi.concept as Mock).mockResolvedValue({
      ...conceptList.items[0],
      materials: [{ id: "m1", name: "Cell Notes" }],
      chunkCount: 2,
      pages: [3],
    });
    renderSection();
    await waitFor(() => expect(screen.getByText("Mitosis")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Mitosis/ }));
    await waitFor(() => expect(knowledgeApi.concept).toHaveBeenCalledWith("proj-1", "c1"));
    await waitFor(() => expect(screen.getByText("Cell Notes")).toBeInTheDocument());
    expect(screen.getByText("Pages: 3")).toBeInTheDocument();
    expect(screen.getByText("Supporting chunks: 2")).toBeInTheDocument();
  });

  it("provenance expand shows retry on detail failure", async () => {
    mockStatus.mockResolvedValue(readyStatus);
    mockConcepts.mockResolvedValue(conceptList);
    (knowledgeApi.concept as Mock).mockRejectedValue(new Error("boom"));
    renderSection();
    await waitFor(() => expect(screen.getByText("Mitosis")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Mitosis/ }));
    await waitFor(() => expect(screen.getByText(/Could not load provenance/)).toBeInTheDocument());
    (knowledgeApi.concept as Mock).mockResolvedValue({
      ...conceptList.items[0],
      materials: [{ id: "m1", name: "Cell Notes" }],
    });
    fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    await waitFor(() => expect(screen.getByText("Cell Notes")).toBeInTheDocument());
  });
});
