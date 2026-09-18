import { Link } from "react-router-dom";
import { Clock, FileText, TriangleAlert } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
  const bar = failed ? "bg-destructive" : "bg-primary";
  return (
    <Link
      to={`/projects/${material.projectId}/materials/${material.id}`}
      className="group block rounded-[10px] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      aria-label={`Open material ${material.name}`}
    >
      <Card
        className={`h-full transition-colors group-hover:border-primary/40 ${failed ? "border-destructive/30" : ""}`}
      >
        <div className={`h-1 w-full rounded-t-[10px] ${bar}`} aria-hidden="true" />
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px] line-clamp-1">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
              </span>
              <span className="truncate">{material.name}</span>
            </CardTitle>
            <MaterialStatusBadge status={material.status} />
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
    </Link>
  );
}
