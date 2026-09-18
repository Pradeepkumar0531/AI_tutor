import { FileText, FileUp, Search, Upload } from "lucide-react";
import * as React from "react";

import { toApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLabel, SectionLoading } from "@/components/ui";
import { useToast } from "@/components/ui/toast";
import { MaterialCard } from "@/features/materials/components/MaterialCard";
import { UploadDialog } from "@/features/materials/components/UploadDialog";
import { useMaterialPolling } from "@/features/materials/hooks/useMaterialPolling";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { useMaterialsStore } from "@/stores/useMaterialsStore";

export function MaterialsSection({ projectId }: { projectId: string }) {
  const items = useMaterialsStore((s) => s.items);
  const total = useMaterialsStore((s) => s.total);
  const status = useMaterialsStore((s) => s.status);
  const error = useMaterialsStore((s) => s.error);
  const fetchMaterials = useMaterialsStore((s) => s.fetch);
  const uploadMaterial = useMaterialsStore((s) => s.upload);
  const resetUpload = useMaterialsStore((s) => s.resetUpload);
  const concepts = useKnowledgeStore((s) => s.concepts);
  const { push } = useToast();

  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [query, setQuery] = React.useState("");

  React.useEffect(() => {
    void fetchMaterials(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useMaterialPolling(projectId);

  const visible = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (m) =>
        m.name.toLowerCase().includes(q) || (m.originalFilename ?? "").toLowerCase().includes(q),
    );
  }, [items, query]);

  async function handleUpload(file: File, title: string) {
    try {
      await uploadMaterial(projectId, file, title);
      setDialogOpen(false);
      resetUpload();
      push("Upload complete. Processing has started.");
    } catch (e) {
      push(`Upload failed: ${toApiError(e).message}`);
      throw e;
    }
  }

  const readyCount = items.filter((m) => m.status === "READY").length;

  return (
    <section aria-labelledby="materials-heading">
      <SectionLabel id="materials-heading">Materials</SectionLabel>
      <div className="mb-4 mt-2 grid grid-cols-3 gap-3">
        <div className="rounded-[10px] border bg-card p-3 sm:p-4">
          <p className="eyebrow">Materials</p>
          <p className="mt-1.5 text-xl font-semibold leading-none tracking-tight sm:text-2xl">
            {total}
          </p>
        </div>
        <div className="rounded-[10px] border bg-card p-3 sm:p-4">
          <p className="eyebrow">Ready materials</p>
          <p className="mt-1.5 text-xl font-semibold leading-none tracking-tight sm:text-2xl">
            {readyCount}
          </p>
        </div>
        <div className="rounded-[10px] border bg-card p-3 sm:p-4">
          <p className="eyebrow">Concepts</p>
          <p className="mt-1.5 text-xl font-semibold leading-none tracking-tight sm:text-2xl">
            {concepts.length}
          </p>
        </div>
      </div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="flex items-center gap-2 text-[15px] font-semibold">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
            <FileText className="h-3.5 w-3.5" aria-hidden="true" />
          </span>
          Library{" "}
          <span className="font-normal text-muted-foreground">
            ({total} {total === 1 ? "file" : "files"})
          </span>
        </h3>
        <div className="flex items-center gap-2">
          {items.length > 0 ? (
            <div className="relative">
              <Search
                className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden="true"
              />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search PDFs…"
                aria-label="Search materials"
                className="h-8 w-44 pl-8 sm:w-52"
              />
            </div>
          ) : null}
          <Button size="sm" onClick={() => setDialogOpen(true)}>
            <Upload className="h-4 w-4" aria-hidden="true" />
            Upload PDF
          </Button>
        </div>
      </div>

      {status === "loading" && items.length === 0 ? (
        <SectionLoading label="Loading materials">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2" aria-hidden="true">
            {[0, 1].map((i) => (
              <div key={i} className="rounded-[10px] border bg-card">
                <div className="skel h-1 w-full rounded-t-[10px]" />
                <div className="flex items-start justify-between gap-2 p-4 pb-3">
                  <div className="flex min-w-0 items-center gap-2.5">
                    <div className="skel h-8 w-8 shrink-0 rounded-lg" />
                    <div className="skel h-4 w-32" />
                  </div>
                  <div className="skel h-5 w-16 shrink-0 rounded-full" />
                </div>
                <div className="px-4 pb-4">
                  <div className="skel h-3 w-40" />
                  <div className="skel mt-2 h-3 w-24" />
                </div>
              </div>
            ))}
          </div>
        </SectionLoading>
      ) : null}

      {status === "error" ? (
        <ErrorState
          title="Could not load materials"
          description={error ?? undefined}
          onRetry={() => void fetchMaterials(projectId)}
        />
      ) : null}

      {status === "ready" && total === 0 ? (
        <EmptyState
          title="No materials yet."
          description="Upload your first PDF to ground tutoring, quizzes, and recommendations in it."
          icon={FileUp}
        />
      ) : null}

      {items.length > 0 && visible.length === 0 ? (
        <EmptyState
          title="No PDFs match your search."
          description={`Nothing matches "${query.trim()}". Clear the search to see all ${items.length} files.`}
          icon={Search}
        />
      ) : null}

      {visible.length > 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {visible.map((m) => (
            <MaterialCard key={m.id} material={m} />
          ))}
        </div>
      ) : null}

      <UploadDialog open={dialogOpen} onOpenChange={setDialogOpen} onUpload={handleUpload} />
    </section>
  );
}
