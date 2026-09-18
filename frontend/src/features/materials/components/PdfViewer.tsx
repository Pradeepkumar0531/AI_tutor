import * as React from "react";
import { Download, Expand, FileText, Loader2, Printer, ZoomIn, ZoomOut } from "lucide-react";

import { materialsApi } from "@/api/materials";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLoading } from "@/components/ui";
import { useToast } from "@/components/ui/toast";

type ViewerPhase = "loading" | "ready" | "error" | "idle";

const ZOOM_STEPS = [50, 75, 100, 125, 150, 175, 200];
const MIN_ZOOM = 50;
const MAX_ZOOM = 200;

export function PdfViewer({
  projectId,
  materialId,
  status,
  title,
  pageCount,
}: {
  projectId: string;
  materialId: string;
  status: string;
  title: string;
  pageCount?: number | null;
}) {
  const { push } = useToast();
  const containerRef = React.useRef<HTMLDivElement>(null);
  const iframeRef = React.useRef<HTMLIFrameElement>(null);
  const [phase, setPhase] = React.useState<ViewerPhase>("idle");
  const [url, setUrl] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [zoom, setZoom] = React.useState(100);
  const [fitWidth, setFitWidth] = React.useState(true);
  const [reloadKey, setReloadKey] = React.useState(0);

  const previewable = status !== "FAILED";

  const load = React.useCallback(async () => {
    const loader = (materialsApi as { pdfBlob?: typeof materialsApi.pdfBlob }).pdfBlob;
    if (typeof loader !== "function") {
      setPhase("error");
      setError("PDF preview is unavailable in this build.");
      return;
    }
    setPhase("loading");
    setError(null);
    try {
      const blob = await loader.call(materialsApi, projectId, materialId);
      const objectUrl = URL.createObjectURL(
        blob.type === "application/pdf" ? blob : new Blob([blob], { type: "application/pdf" }),
      );
      setUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return objectUrl;
      });
      setPhase("ready");
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Could not load the PDF preview.");
    }
  }, [projectId, materialId]);

  React.useEffect(() => {
    if (!previewable) {
      setPhase("idle");
      return;
    }
    void load();
  }, [previewable, load, reloadKey]);

  React.useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );

  function stepZoom(dir: 1 | -1) {
    setZoom((z) => {
      let best = 0;
      for (let i = 1; i < ZOOM_STEPS.length; i++) {
        const cur = ZOOM_STEPS[i] ?? z;
        const prevBest = ZOOM_STEPS[best] ?? z;
        if (Math.abs(cur - z) < Math.abs(prevBest - z)) best = i;
      }
      const next = ZOOM_STEPS[Math.min(ZOOM_STEPS.length - 1, Math.max(0, best + dir))] ?? z;
      return next;
    });
  }

  function handleDownload() {
    if (!url) return;
    const a = document.createElement("a");
    a.href = url;
    a.download = title.toLowerCase().endsWith(".pdf") ? title : `${title}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function handlePrint() {
    try {
      iframeRef.current?.contentWindow?.print();
    } catch {
      push("Printing is blocked by the browser for this preview. Use Download instead.");
    }
  }

  function handleFullscreen() {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      void document.exitFullscreen().catch(() => {});
      return;
    }
    if (el.requestFullscreen) {
      void el.requestFullscreen().catch(() => push("Fullscreen was blocked by the browser."));
    }
  }

  function handleOpenNewTab() {
    if (url) window.open(url, "_blank", "noopener,noreferrer");
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b bg-card pb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <CardTitle className="flex min-w-0 items-center gap-2 text-[15px]">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
              <FileText className="h-4 w-4" aria-hidden="true" />
            </span>
            <span className="truncate">{title}</span>
            <span className="rounded-md bg-primary px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-primary-foreground">
              PDF
            </span>
            {pageCount != null ? (
              <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
                PDF · {pageCount} {pageCount === 1 ? "page" : "pages"}
              </span>
            ) : null}
          </CardTitle>
          {phase === "ready" ? (
            <div
              className="flex flex-wrap items-center gap-1.5"
              role="toolbar"
              aria-label="PDF controls"
            >
              <Button
                variant="outline"
                size="sm"
                onClick={() => stepZoom(-1)}
                disabled={zoom <= MIN_ZOOM}
                aria-label="Zoom out"
              >
                <ZoomOut className="h-4 w-4" aria-hidden="true" />
              </Button>
              <span
                className="min-w-14 text-center text-xs font-semibold tabular-nums"
                aria-live="polite"
              >
                {zoom}%
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => stepZoom(1)}
                disabled={zoom >= MAX_ZOOM}
                aria-label="Zoom in"
              >
                <ZoomIn className="h-4 w-4" aria-hidden="true" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setFitWidth((v) => !v)}
                title={fitWidth ? "Show actual size" : "Fit to width"}
              >
                {fitWidth ? "Actual size" : "Fit width"}
              </Button>
              <Button variant="outline" size="sm" onClick={handlePrint} aria-label="Print PDF">
                <Printer className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Print</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDownload}
                aria-label="Download PDF"
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                <span className="hidden sm:inline">Download</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleFullscreen}
                aria-label="Toggle fullscreen"
              >
                <Expand className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {!previewable ? (
          <div className="p-6">
            <EmptyState
              title="Preview unavailable."
              description="Processing failed, so the original PDF cannot be shown."
            />
          </div>
        ) : phase === "loading" || phase === "idle" ? (
          <div className="p-6">
            <SectionLoading label="Loading PDF preview">
              <div aria-hidden="true" className="overflow-hidden rounded-lg border bg-muted/40">
                <div className="skel-shimmer skel h-10 rounded-none" />
                <div className="skel mx-3 my-3 h-[380px] sm:mx-4" />
              </div>
            </SectionLoading>
          </div>
        ) : phase === "error" ? (
          <div className="p-6">
            <ErrorState
              title="Could not load PDF preview"
              description={error ?? undefined}
              onRetry={() => setReloadKey((k) => k + 1)}
            />
          </div>
        ) : url ? (
          <div ref={containerRef} className="bg-muted/40">
            <div className="flex items-center justify-between gap-2 border-b px-4 py-1.5 text-xs text-muted-foreground">
              <span className="truncate">
                Original document · rendered in-browser · {status.toLowerCase()}
                {status !== "READY" ? " — extracted text unlocks when processing finishes" : ""}
              </span>
              <button
                type="button"
                onClick={handleOpenNewTab}
                className="shrink-0 font-medium text-primary hover:underline"
              >
                Open in new tab
              </button>
            </div>
            <div className="overflow-auto p-3 sm:p-4" style={{ maxHeight: "78vh" }}>
              <div
                className="mx-auto overflow-hidden rounded-lg border bg-white shadow-sm"
                style={{
                  maxWidth: fitWidth ? "100%" : `${zoom * 8}px`,
                  transform: fitWidth ? undefined : `scale(${zoom / 100})`,
                  transformOrigin: "top left",
                  width: fitWidth ? "100%" : "100%",
                }}
              >
                {phase === "ready" && zoom < 100 && !fitWidth ? (
                  <p className="flex items-center justify-center gap-2 border-b bg-muted/50 py-1 text-[11px] text-muted-foreground">
                    <Loader2 className="hidden" aria-hidden="true" />
                    Zoom {zoom}% — switch to Fit for full-width reading
                  </p>
                ) : null}
                <iframe
                  ref={iframeRef}
                  key={url}
                  title={`PDF preview of ${title}`}
                  src={url}
                  className="block w-full bg-white"
                  style={{ height: "72vh", minHeight: 480 }}
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
