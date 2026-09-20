import { MemoryRouter, Route, Routes } from "react-router-dom";
import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { MaterialDetailPage } from "@/app/pages/MaterialDetailPage";
import { TutorSection } from "@/features/tutor/components/TutorSection";
import { KnowledgeReadinessBanner } from "@/features/knowledge/components/KnowledgeReadinessBanner";
import { useKnowledgeReadiness } from "@/features/knowledge/hooks/useKnowledgeReadiness";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useTutorStore } from "@/stores/useTutorStore";

// Only HTTP boundaries are mocked; mapping, stores, and components run for real.
vi.mock("@/api/knowledge", () => ({
  knowledgeApi: {
    status: vi.fn(),
    concepts: vi.fn(),
    concept: vi.fn(),
    search: vi.fn(),
    reprocess: vi.fn(),
  },
}));
vi.mock("@/api/tutor", () => ({
  tutorApi: {
    conversations: vi.fn(),
    createConversation: vi.fn(),
    messages: vi.fn(),
    send: vi.fn(),
  },
}));
vi.mock("@/api/materials", () => ({
  // Mirrors materials.test.tsx: images/pdf endpoints are absent so image
  // loading degrades through the store's caught-error path, as in prod.
  materialsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    get: vi.fn(),
    chunks: vi.fn(),
    reprocess: vi.fn(),
    archive: vi.fn(),
  },
}));
vi.mock("@/api/projects", () => ({
  projectsApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
  },
}));

import { knowledgeApi } from "@/api/knowledge";
import { materialsApi } from "@/api/materials";
import { projectsApi } from "@/api/projects";
import { tutorApi } from "@/api/tutor";

const mockStatus = knowledgeApi.status as Mock;
const mockReprocessKnowledge = knowledgeApi.reprocess as Mock;
const mockGet = materialsApi.get as Mock;
const mockChunks = materialsApi.chunks as Mock;

function reset() {
  useKnowledgeStore.getState().reset();
  useTutorStore.getState().reset();
  useMaterialsStore.getState().reset();
  vi.clearAllMocks();
  vi.useRealTimers();
}

function processingStatus() {
  return {
    project_id: "proj-1",
    status: "PROCESSING",
    totals: { chunks_total: 4, chunks_embedded: 1, concepts: 0, materials_ready: 1 },
  };
}

function readyStatus() {
  return {
    project_id: "proj-1",
    status: "READY",
    totals: { chunks_total: 4, chunks_embedded: 4, concepts: 2, materials_ready: 1 },
  };
}

function renderBanner() {
  return render(
    <MemoryRouter>
      <KnowledgeReadinessBanner projectId="proj-1" />
    </MemoryRouter>,
  );
}

describe("KnowledgeReadinessBanner", () => {
  beforeEach(reset);

  it("shows the preparing message with real progress while PROCESSING", async () => {
    mockStatus.mockResolvedValue(processingStatus());
    renderBanner();
    await waitFor(() =>
      expect(screen.getByText(/still preparing it for Tutor search/)).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/Your material is ready, but we're still preparing it/),
    ).toBeInTheDocument();
    expect(screen.getByText(/1\/4 chunks embedded/)).toBeInTheDocument();
    // Non-error: announced politely, never an alert.
    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders nothing once READY — the normal Tutor experience", async () => {
    mockStatus.mockResolvedValue(readyStatus());
    const { container } = renderBanner();
    await waitFor(() => expect(mockStatus).toHaveBeenCalledWith("proj-1"));
    await waitFor(() => expect(useKnowledgeStore.getState().status).toBe("READY"));
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByText(/preparing it for Tutor search/)).not.toBeInTheDocument();
  });

  it("shows a FAILED state with a recovery link to materials", async () => {
    mockStatus.mockResolvedValue({
      project_id: "proj-1",
      status: "FAILED",
      totals: { chunks_total: 4, chunks_embedded: 1, concepts: 0, materials_ready: 1 },
    });
    renderBanner();
    await waitFor(() => expect(screen.getByText(/preparation failed/)).toBeInTheDocument());
    expect(screen.getByRole("alert")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: /retry preparation/i });
    expect(link.getAttribute("href")).toBe("/projects/proj-1/materials");
  });
});

describe("useKnowledgeReadiness polling", () => {
  beforeEach(reset);

  it("polls while PROCESSING and stops after READY", async () => {
    vi.useFakeTimers();
    mockStatus.mockResolvedValue(processingStatus());
    renderHook(() => useKnowledgeReadiness("proj-1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockStatus).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    expect(mockStatus).toHaveBeenCalledTimes(2);

    // Knowledge settles: the next tick observes READY, then polling stops.
    mockStatus.mockResolvedValue(readyStatus());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(4000);
    });
    const callsAfterReady = mockStatus.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(mockStatus.mock.calls.length).toBe(callsAfterReady);
    expect(useKnowledgeStore.getState().status).toBe("READY");
  });

  it("never polls a FAILED status", async () => {
    vi.useFakeTimers();
    mockStatus.mockResolvedValue({
      project_id: "proj-1",
      status: "FAILED",
      totals: { chunks_total: 4, chunks_embedded: 1, concepts: 0, materials_ready: 1 },
    });
    renderHook(() => useKnowledgeReadiness("proj-1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mockStatus).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(mockStatus).toHaveBeenCalledTimes(1);
  });
});

describe("TutorSection with knowledge readiness", () => {
  beforeEach(reset);

  const conv = {
    id: "conv-1",
    projectId: "proj-1",
    title: "Untitled conversation",
    createdAt: "",
    updatedAt: "",
  };

  function renderTutor() {
    return render(
      <MemoryRouter>
        <TutorSection projectId="proj-1" />
      </MemoryRouter>,
    );
  }

  it("keeps the composer enabled while knowledge is PROCESSING", async () => {
    mockStatus.mockResolvedValue(processingStatus());
    (tutorApi.conversations as Mock).mockResolvedValue([conv]);
    (tutorApi.messages as Mock).mockResolvedValue([]);
    renderTutor();
    await waitFor(() =>
      expect(screen.getByText(/still preparing it for Tutor search/)).toBeInTheDocument(),
    );
    // Not blocked: the learner can still type and send (general questions
    // work; grounded ones keep server-side enforcement).
    await waitFor(() => expect(screen.getByLabelText("Ask the tutor")).toBeEnabled());
  });

  it("shows the normal experience with no banner once READY", async () => {
    mockStatus.mockResolvedValue(readyStatus());
    (tutorApi.conversations as Mock).mockResolvedValue([conv]);
    (tutorApi.messages as Mock).mockResolvedValue([]);
    renderTutor();
    await waitFor(() => expect(screen.getByLabelText("Ask the tutor")).toBeEnabled());
    expect(screen.queryByText(/preparing it for Tutor search/)).not.toBeInTheDocument();
    expect(screen.queryByText(/preparation failed/)).not.toBeInTheDocument();
  });
});

describe("MaterialDetailPage knowledge states", () => {
  beforeEach(reset);

  function renderDetail() {
    return render(
      <MemoryRouter initialEntries={["/projects/proj-1/materials/mat-1"]}>
        <Routes>
          <Route
            path="/projects/:projectId/materials/:materialId"
            element={<MaterialDetailPage />}
          />
        </Routes>
      </MemoryRouter>,
    );
  }

  const base = {
    id: "mat-1",
    projectId: "proj-1",
    name: "Notes.pdf",
    type: "PDF",
    status: "READY",
    originalFilename: "notes.pdf",
    mimeType: "application/pdf",
    fileSize: 1024,
    processingError: null,
    retryCount: 0,
    pageCount: 2,
    chunkCount: 2,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    imageCount: 0,
    document: {
      id: "doc-1",
      materialId: "mat-1",
      projectId: "proj-1",
      pageCount: 2,
      extractionMethod: "TEXT",
      language: null,
      chunkCount: 2,
    },
  };

  function stubProject() {
    useProjectsStore.setState({
      current: {
        id: "proj-1",
        spaceId: "s",
        name: "P",
        description: null,
        learningGoal: null,
        archivedAt: null,
        createdAt: "",
        updatedAt: "",
      } as never,
    });
    (projectsApi.get as Mock).mockResolvedValue(useProjectsStore.getState().current);
  }

  it("shows the preparing message while knowledge is PROCESSING", async () => {
    stubProject();
    mockGet.mockResolvedValue({
      ...base,
      knowledge: {
        status: "PROCESSING",
        embedded: 1,
        total: 2,
        image_count: 0,
        images_by_page: {},
      },
    });
    mockChunks.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    renderDetail();
    await waitFor(() => expect(screen.getByText("Preparing for Tutor search")).toBeInTheDocument());
    expect(screen.getByText(/still preparing it for Tutor search/)).toBeInTheDocument();
    expect(screen.getByText(/1\/2 chunks embedded/)).toBeInTheDocument();
  });

  it("shows FAILED with a working Retry Tutor search prep action", async () => {
    stubProject();
    mockGet.mockResolvedValue({
      ...base,
      knowledge: { status: "FAILED", embedded: 1, total: 2, image_count: 0, images_by_page: {} },
    });
    mockChunks.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    mockReprocessKnowledge.mockResolvedValue({
      material_id: "mat-1",
      job_status: "QUEUED",
      reset: 1,
    });
    renderDetail();
    await waitFor(() =>
      expect(screen.getByText("Tutor search preparation failed")).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Retry Tutor search prep" }));
    await waitFor(() => expect(mockReprocessKnowledge).toHaveBeenCalledWith("proj-1", "mat-1"));
    // The detail re-reads real state after the retry.
    await waitFor(() => expect(mockGet.mock.calls.length).toBeGreaterThan(1));
  });

  it("marks READY knowledge as ready for Tutor search", async () => {
    stubProject();
    mockGet.mockResolvedValue({
      ...base,
      knowledge: { status: "READY", embedded: 2, total: 2, image_count: 0, images_by_page: {} },
    });
    mockChunks.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 10 });
    renderDetail();
    await waitFor(() => expect(screen.getByText(/Ready for Tutor search/)).toBeInTheDocument());
    expect(screen.queryByText("Preparing for Tutor search")).not.toBeInTheDocument();
    expect(screen.queryByText("Tutor search preparation failed")).not.toBeInTheDocument();
  });
});
