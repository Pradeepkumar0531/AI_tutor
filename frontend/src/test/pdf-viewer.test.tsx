import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { materialsApi } from "@/api/materials";
import { PdfViewer } from "@/features/materials/components/PdfViewer";

vi.mock("@/api/materials", () => ({
  materialsApi: {
    pdfBlob: vi.fn(),
  },
}));

const mockPdf = materialsApi.pdfBlob as Mock;

function reset() {
  vi.clearAllMocks();
}

beforeEach(() => {
  reset();
  Object.defineProperty(URL, "createObjectURL", {
    value: vi.fn(() => "blob:pdf"),
    writable: true,
    configurable: true,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    value: vi.fn(),
    writable: true,
    configurable: true,
  });
});

describe("PdfViewer", () => {
  it("renders the PDF in an iframe with toolbar controls", async () => {
    mockPdf.mockResolvedValue(new Blob(["%PDF"], { type: "application/pdf" }));
    render(
      <PdfViewer projectId="p" materialId="m" status="READY" title="notes.pdf" pageCount={4} />,
    );
    await waitFor(() => expect(screen.getByTitle("PDF preview of notes.pdf")).toBeInTheDocument());
    expect(screen.getByText("PDF · 4 pages")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download PDF" })).toBeInTheDocument();
    expect(screen.getByText("Open in new tab")).toBeInTheDocument();
  });

  it("zooms in and out and toggles fit", async () => {
    mockPdf.mockResolvedValue(new Blob(["%PDF"], { type: "application/pdf" }));
    render(<PdfViewer projectId="p" materialId="m" status="READY" title="a.pdf" />);
    await waitFor(() => expect(screen.getByText("100%")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    await waitFor(() => expect(screen.getByText("125%")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Zoom out" }));
    await waitFor(() => expect(screen.getByText("100%")).toBeInTheDocument());
  });

  it("shows an error with retry when loading fails", async () => {
    mockPdf.mockRejectedValueOnce(new Error("gone"));
    mockPdf.mockResolvedValueOnce(new Blob(["%PDF"], { type: "application/pdf" }));
    render(<PdfViewer projectId="p" materialId="m" status="READY" title="a.pdf" />);
    await waitFor(() => expect(screen.getByText("Could not load PDF preview")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByTitle("PDF preview of a.pdf")).toBeInTheDocument());
  });

  it("never tries to load when processing failed", async () => {
    render(<PdfViewer projectId="p" materialId="m" status="FAILED" title="a.pdf" />);
    await waitFor(() => expect(screen.getByText("Preview unavailable.")).toBeInTheDocument());
    expect(mockPdf).not.toHaveBeenCalled();
  });
});
