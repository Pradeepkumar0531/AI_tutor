import { Loader2, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";

import { useKnowledgeReadiness } from "@/features/knowledge/hooks/useKnowledgeReadiness";

/**
 * Advisory knowledge-readiness banner for the Tutor tab.
 *
 * Display-only: it never blocks the composer or the send path (general
 * questions still work; project-grounded questions keep server-enforced
 * grounding). Renders nothing once knowledge is READY — the normal Tutor
 * experience — and nothing while the status is still unknown.
 */
export function KnowledgeReadinessBanner({ projectId }: { projectId: string }) {
  const { status, totals } = useKnowledgeReadiness(projectId);

  if (status === "PROCESSING" || status === "PENDING") {
    const progress =
      totals && totals.chunks_total > 0
        ? ` ${totals.chunks_embedded}/${totals.chunks_total} chunks embedded.`
        : "";
    return (
      <div
        role="status"
        className="mt-2 flex items-start gap-2 rounded-lg border bg-secondary/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground"
      >
        <Loader2 className="mt-0.5 h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden="true" />
        <p>
          Your material is ready, but we&apos;re still preparing it for Tutor search.{progress}{" "}
          Answers may say evidence is missing until preparation finishes.
        </p>
      </div>
    );
  }

  if (status === "FAILED") {
    return (
      <div
        role="alert"
        className="mt-2 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs leading-relaxed"
      >
        <TriangleAlert
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive"
          aria-hidden="true"
        />
        <p>
          Tutor search preparation failed for this project, so answers may be missing evidence.{" "}
          <Link
            to={`/projects/${projectId}/materials`}
            className="font-medium text-primary underline-offset-2 hover:underline"
          >
            View materials to retry preparation.
          </Link>
        </p>
      </div>
    );
  }

  return null;
}
