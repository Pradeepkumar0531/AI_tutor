import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { materialsApi } from "@/api/materials";
import { DocumentImagesSection } from "@/features/materials/components/DocumentImagesSection";
import { useMaterialsStore } from "@/stores/useMaterialsStore";

// Only the HTTP boundary is mocked; mapping, store, and components run for real.
vi.mock("@/api/materials", () => ({
  materialsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    get: vi.fn(),
    chunks: vi.fn(),
    reprocess: vi.fn(),
    archive: vi.fn(),
    images: vi.fn(),
    imageBlob: vi.fn(),
  },
}));

const mockImages = materialsApi.images as Mock;
const mockBlob = materialsApi.imageBlob as Mock;

function reset() {
  useMaterialsStore.getState().reset();
  vi.clearAllMocks();
}

const img1 = {
  id: "img-1",
  documentId: "doc-1",
  pageNumber: 1,
  imageIndex: 0,
  width: 300,
  height: 200,
  mimeType: "image/png",
  fileSize: 14602,
};

const img2 = {
  id: "img-2",
  documentId: "doc-1",
  pageNumber: 2,
  imageIndex: 0,
  width: 250,
  height: 180,
  mimeType: "image/png",
  fileSize: 11230,
};

function renderSection(status = "READY") {
  return render(<DocumentImagesSection projectId="proj-1" materialId="mat-1" status={status} />);
}

describe("materials store images", () => {
  beforeEach(reset);

  it("loads images into state", async () => {
    mockImages.mockResolvedValue([img1, img2]);
    await useMaterialsStore.getState().fetchImages("proj-1", "mat-1");
    const s = useMaterialsStore.getState();
    expect(mockImages).toHaveBeenCalledWith("proj-1", "mat-1");
    expect(s.images).toHaveLength(2);
    expect(s.imagesState).toBe("ready");
  });

  it("records image errors without crashing", async () => {
    mockImages.mockRejectedValue(new Error("down"));
    await useMaterialsStore.getState().fetchImages("proj-1", "mat-1");
    const s = useMaterialsStore.getState();
    expect(s.imagesState).toBe("error");
    expect(s.imagesError).toContain("down");
  });
});

describe("DocumentImagesSection", () => {
  beforeEach(reset);

  it("renders image metadata with page numbers", async () => {
    mockImages.mockResolvedValue([img1, img2]);
    mockBlob.mockResolvedValue(new Blob(["x"], { type: "image/png" }));
    renderSection();
    await waitFor(() => expect(screen.getByText("Page 1 · Image 1")).toBeInTheDocument());
    expect(screen.getByText("Page 2 · Image 1")).toBeInTheDocument();
    expect(document.body.textContent).toContain("300×200");
    expect(document.body.textContent).toContain("image/png");
  });

  it("shows an honest empty state for ready materials without images", async () => {
    mockImages.mockResolvedValue([]);
    renderSection();
    await waitFor(() =>
      expect(screen.getByText("No embedded images were detected.")).toBeInTheDocument(),
    );
  });

  it("never claims no-images while processing is incomplete", async () => {
    mockImages.mockResolvedValue([]);
    renderSection("PROCESSING");
    await waitFor(() => expect(screen.getByText(/images will appear here/)).toBeInTheDocument());
    expect(mockImages).not.toHaveBeenCalled();
    expect(screen.queryByText("No embedded images were detected.")).not.toBeInTheDocument();
  });

  it("shows errors with retry", async () => {
    mockImages.mockRejectedValueOnce(new Error("denied"));
    mockImages.mockResolvedValueOnce([img1]);
    mockBlob.mockResolvedValue(new Blob(["x"], { type: "image/png" }));
    renderSection();
    await waitFor(() => expect(screen.getByText("Could not load images")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("Page 1 · Image 1")).toBeInTheDocument());
  });

  it("handles preview load failure gracefully", async () => {
    mockImages.mockResolvedValue([img1]);
    mockBlob.mockRejectedValue(new Error("gone"));
    renderSection();
    await waitFor(() => expect(screen.getByText("Preview unavailable")).toBeInTheDocument());
  });
});
