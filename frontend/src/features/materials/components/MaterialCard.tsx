import * as React from "react";
import { Link } from "react-router-dom";
import { Clock, FileText, Trash2, TriangleAlert } from "lucide-react";

import { toApiError } from "@/api/client";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from "@/components/ui/toast";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import { MaterialStatusBadge } from "./MaterialStatusBadge";
import type { Material } from "@/types";

function formatBytes(size: number | null): string {
  if (size === null || size === undefined) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function MaterialCard({ material }: { material: Material }) {
  const failed = material.status === "FAILED";
  const processing = material.status === "QUEUED" || material.status === "PROCESSING";
  const archive = useMaterialsStore((s) => s.archive);
  const { push } = useToast();
  const [confirmOpen, setConfirmOpen] = React.useState(false);
  const [deleting, setDeleting] = React.useState(false);

  const bar = failed ? "bg-destructive" : "bg-primary";

  async function handleDelete() {
    setDeleting(true);
    try {
      await archive(material.projectId, material.id);
      push(`Deleted “${material.name}”.`);
    } catch (e) {
      push(`Could not delete material: ${toApiError(e).message}`);
    } finally {
      setDeleting(false);
      setConfirmOpen(false);
    }
  }

  return (
    <>
      <Card variant="light" accent className={`card-lift h-full ${failed ? "border-destructive/30" : ""}`}>
        <div className={`h-1 w-full rounded-t-[10px] ${bar}`} aria-hidden="true" />
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <Link
              to={`/projects/${material.projectId}/materials/${material.id}`}
              className="group min-w-0 flex-1 rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label={`Open material ${material.name}`}
            >
              <span className="flex min-w-0 items-center gap-2">
                <CardTitle className="flex min-w-0 flex-1 items-center gap-2.5 text-[15px] line-clamp-1 transition-colors group-hover:text-primary">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                    <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
                  </span>
                  <span className="truncate">{material.name}</span>
                </CardTitle>
                <MaterialStatusBadge status={material.status} />
              </span>
            </Link>
            <span className="flex shrink-0 items-center gap-1">
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                aria-label={`Delete material ${material.name}`}
                title={`Delete material ${material.name}`}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Trash2 className="h-4 w-4" aria-hidden="true" />
              </button>
            </span>
          </div>
        </CardHeader>
        <CardContent className="pt-0">
          <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className="rounded bg-secondary px-1 py-px text-[10px] font-bold uppercase tracking-wide text-secondary-foreground">
              PDF
            </span>
            <span>
              {formatBytes(material.fileSize)}
              {material.pageCount !== null && material.pageCount !== undefined
                ? ` · ${material.pageCount} ${material.pageCount === 1 ? "page" : "pages"}`
                : null}
              {material.chunkCount !== null && material.chunkCount !== undefined
                ? ` · ${material.chunkCount} ${material.chunkCount === 1 ? "chunk" : "chunks"}`
                : null}
            </span>
          </p>
          {processing ? (
            <div className="mt-2.5" aria-hidden="true">
              <div className="h-1 overflow-hidden rounded-full bg-muted">
                <div className="skel-indeterminate-bar h-full w-1/3 rounded-full bg-primary" />
              </div>
            </div>
          ) : null}
          {material.status === "FAILED" && material.processingError ? (
            <p className="mt-2 flex items-start gap-1.5 line-clamp-2 text-xs text-destructive">
              <TriangleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
              {material.processingError}
            </p>
          ) : null}
          <p className="mt-2 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            Updated {new Date(material.updatedAt).toLocaleDateString()}
          </p>
        </CardContent>
      </Card>
      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title={`Delete “${material.name}”?`}
        description="The material will be removed from this project. The stored file and extracted content are kept, so it can be restored."
        confirmLabel="Delete"
        pending={deleting}
        onConfirm={() => void handleDelete()}
      />
    </>
  );
}
