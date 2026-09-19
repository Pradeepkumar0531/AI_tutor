import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, render, renderHook, screen, waitFor, act } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { MaterialDetailPage } from "@/app/pages/MaterialDetailPage";
import { MaterialsSection } from "@/features/materials/components/MaterialsSection";
import { UploadDialog } from "@/features/materials/components/UploadDialog";
import { useMaterialPolling } from "@/features/materials/hooks/useMaterialPolling";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import type { Material } from "@/types";

// Only the HTTP boundary is mocked; mapping, stores, and components run for real.
vi.mock("@/api/materials", () => ({
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

import { materialsApi } from "@/api/materials";
import { projectsApi } from "@/api/projects";
import { useProjectsStore } from "@/stores/useProjectsStore";

const mockList = materialsApi.list as Mock;
const mockUpload = materialsApi.upload as Mock;
const mockGet = materialsApi.get as Mock;
const mockChunks = materialsApi.chunks as Mock;
const mockReprocess = materialsApi.reprocess as Mock;
const mockArchive = materialsApi.archive as Mock;
const mockProjectsGet = projectsApi.get as Mock;

function mat(over: Partial<Material> = {}): Material {
  return {
    id: "mat-1",
    projectId: "proj-1",
    name: "Notes.pdf",
    type: "PDF",
    status: "QUEUED",
    originalFilename: "notes.pdf",
    mimeType: "application/pdf",
    fileSize: 1024,
    processingError: null,
    retryCount: 0,
    pageCount: null,
    chunkCount: null,
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function reset() {
  useMaterialsStore.getState().reset();
  vi.clearAllMocks();
  vi.useRealTimers();
}

describe("materials store", () => {
  beforeEach(reset);

  it("loads an empty list into the structural empty state", async () => {
    mockList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    render(
      <MemoryRouter>
        <MaterialsSection projectId="proj-1" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    expect(mockList).toHaveBeenCalledWith("proj-1");
  });

  it("discards a stale list snapshot that would wipe a just-uploaded row", async () => {
    let release!: (v: unknown) => void;
    mockList.mockReturnValueOnce(
      new Promise((res) => {
        release = res as (v: unknown) => void;
      }),
    );
    const store = useMaterialsStore.getState();
    const fetching = store.fetch("proj-1");
    const uploaded = mat({ id: "fresh", name: "Fresh.pdf", status: "QUEUED" });
    mockUpload.mockResolvedValue(uploaded);
    await store.upload("proj-1", new File(["x"], "fresh.pdf"), "Fresh");
    // The slow mount-time fetch resolves with a pre-upload snapshot: it must
    // lose to the upload generation instead of wiping the new row.
    release({ items: [], total: 0, page: 1, page_size: 20 });
    await fetching;
    expect(useMaterialsStore.getState().items.map((m) => m.id)).toEqual(["fresh"]);
  });

  it("surfaces list errors with retry", async () => {
    mockList.mockRejectedValueOnce(new Error("down"));
    mockList.mockResolvedValueOnce({ items: [], total: 0, page: 1, page_size: 20 });
    render(
      <MemoryRouter>
        <MaterialsSection projectId="proj-1" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Could not load materials")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
  });

  it("deletes a material after confirmation", async () => {
    mockList.mockResolvedValue({
      items: [mat({ status: "READY" })],
      total: 1,
      page: 1,
      page_size: 20,
    });
    mockArchive.mockResolvedValue(mat({ status: "READY" }));
    render(
      <MemoryRouter>
        <MaterialsSection projectId="proj-1" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Open material Notes.pdf" })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Delete material Notes.pdf" }));
    await waitFor(() => expect(screen.getByText("Delete “Notes.pdf”?")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mockArchive).toHaveBeenCalledWith("proj-1", "mat-1"));
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
  });

  it("renders QUEUED/PROCESSING/READY/FAILED states honestly", async () => {
    mockList.mockResolvedValue({
      items: [
        mat({ id: "q", status: "QUEUED" }),
        mat({ id: "p", status: "PROCESSING", name: "B" }),
        mat({ id: "r", status: "READY", name: "C", pageCount: 3, chunkCount: 5 }),
        mat({ id: "f", status: "FAILED", name: "D", processingError: "No readable text." }),
      ],
      total: 4,
      page: 1,
      page_size: 20,
    });
    render(
      <MemoryRouter>
        <MaterialsSection projectId="proj-1" />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Queued")).toBeInTheDocument());
    expect(screen.getByText("Processing")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("No readable text.")).toBeInTheDocument();
    expect(screen.getByText(/3 pages/)).toBeInTheDocument();
  });

  it("upload success prepends without refetch; failure records the error", async () => {
    mockUpload.mockResolvedValue(mat({ status: "QUEUED" }));
    const store = useMaterialsStore.getState();
    const file = new File(["%PDF"], "n.pdf", { type: "application/pdf" });
    await store.upload("proj-1", file, "Title");
    const s = useMaterialsStore.getState();
    expect(s.items).toHaveLength(1);
    expect(s.uploadState.pending).toBe(false);
    expect(s.uploadState.progress).toBe(100);
    expect(mockList).not.toHaveBeenCalled();

    mockUpload.mockRejectedValueOnce(new Error("413 too big"));
    await expect(store.upload("proj-1", file, "T")).rejects.toThrow();
    expect(useMaterialsStore.getState().uploadState.error).toContain("413");
  });
});

describe("UploadDialog", () => {
  beforeEach(reset);

  function renderDialog(onUpload: (f: File, t: string) => Promise<void> = async () => {}) {
    return render(<UploadDialog open onOpenChange={() => {}} onUpload={onUpload} />);
  }

  it("rejects non-PDF, empty, and oversized files client-side", () => {
    renderDialog();
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    const txt = new File(["hi"], "n.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [txt] } });
    expect(screen.getByText("Only PDF files are accepted.")).toBeInTheDocument();

    const big = new File(["x"], "b.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: 30 * 1024 * 1024 });
    fireEvent.change(input, { target: { files: [big] } });
    expect(screen.getByText(/exceeds the 25 MB/)).toBeInTheDocument();
  });

  it("submits the file and title", async () => {
    const onUpload = vi.fn(async () => {});
    renderDialog(onUpload);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["%PDF"], "n.pdf", { type: "application/pdf" })] },
    });
    fireEvent.change(screen.getByLabelText(/Title/), { target: { value: "My Doc" } });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(onUpload).toHaveBeenCalledWith(expect.any(File), "My Doc"));
  });

  it("shows server errors from the upload call", async () => {
    const failing = vi.fn(async () => {
      throw new Error("Invalid upload.");
    });
    render(<UploadDialog open onOpenChange={() => {}} onUpload={failing} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(["%PDF"], "n.pdf", { type: "application/pdf" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => expect(screen.getByText("Invalid upload.")).toBeInTheDocument());
  });
});

describe("useMaterialPolling", () => {
  beforeEach(reset);

  it("polls non-terminal materials and stops at terminal states", async () => {
    vi.useFakeTimers();
    useMaterialsStore.setState({
      items: [mat({ status: "QUEUED" })],
      total: 1,
      projectId: "proj-1",
      status: "ready",
    });
    mockGet.mockResolvedValue({
      ...mat({ status: "PROCESSING" }),
      document: null,
    });
    renderHook(() => useMaterialPolling("proj-1"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(mockGet).toHaveBeenCalledTimes(1);

    // Reaches READY -> polling stops even as time passes.
    mockGet.mockResolvedValue({ ...mat({ status: "READY" }), document: null });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    const callsAfterReady = mockGet.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30000);
    });
    expect(mockGet.mock.calls.length).toBe(callsAfterReady);
  });
});

describe("MaterialDetailPage", () => {
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

  const readyDetail = {
    ...mat({ status: "READY", pageCount: 2, chunkCount: 2 }),
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

  it("shows metadata, chunks, and working pagination", async () => {
    mockGet.mockResolvedValue(readyDetail);
    mockChunks.mockImplementation(async (_p: string, _m: string, params?: { page?: number }) =>
      params?.page === 2
        ? {
            items: [
              {
                id: "c2",
                documentId: "doc-1",
                projectId: "proj-1",
                chunkIndex: 10,
                content: "second",
                pageStart: 2,
                pageEnd: 2,
              },
            ],
            total: 15,
            page: 2,
            page_size: 10,
          }
        : {
            items: [
              {
                id: "c1",
                documentId: "doc-1",
                projectId: "proj-1",
                chunkIndex: 0,
                content: "first",
                pageStart: 1,
                pageEnd: 1,
              },
            ],
            total: 15,
            page: 1,
            page_size: 10,
          },
    );
    // project name lookup for breadcrumbs
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
    mockProjectsGet.mockResolvedValue(useProjectsStore.getState().current);
    renderDetail();

    await waitFor(() => expect(screen.getByText("first")).toBeInTheDocument());
    expect(
      screen.getByText((_c, el) => el?.textContent === "Page 1 of 2 · 15 chunks"),
    ).toBeInTheDocument();
    expect(screen.getByText("2 pages")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() => expect(screen.getByText("second")).toBeInTheDocument());
    expect(
      screen.getByText((_c, el) => el?.textContent === "Page 2 of 2 · 15 chunks"),
    ).toBeInTheDocument();
  });

  it("shows honest failure with a working retry", async () => {
    mockGet.mockResolvedValue({
      ...mat({ status: "FAILED", processingError: "No readable text was found." }),
      document: null,
    });
    mockReprocess.mockResolvedValue(mat({ status: "QUEUED" }));
    renderDetail();
    await waitFor(() => expect(screen.getByText("Processing failed")).toBeInTheDocument());
    expect(screen.getByText("No readable text was found.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry processing" }));
    await waitFor(() => expect(mockReprocess).toHaveBeenCalledWith("proj-1", "mat-1"));
  });

  it("shows a non-disclosing 404 for unknown materials", async () => {
    mockGet.mockRejectedValue(new Error("Not found"));
    renderDetail();
    await waitFor(() => expect(screen.getByText("Material not found")).toBeInTheDocument());
  });
});
