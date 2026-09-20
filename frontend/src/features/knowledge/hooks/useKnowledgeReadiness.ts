import * as React from "react";

import { useKnowledgeStore } from "@/stores/useKnowledgeStore";

const POLL_MS = 4000;

/**
 * Project-level knowledge readiness for advisory banners (Tutor, materials).
 *
 * The backend remains the source of truth: one status fetch on mount and
 * whenever the project changes, then polling ONLY while the status is
 * non-terminal (PENDING/PROCESSING). READY and FAILED never poll. Hidden
 * tabs pause automatically; timers are cleaned up on unmount. No fake
 * progress is ever synthesized, and nothing on the Tutor send path waits
 * for this — it is display-only, so Tutor calls are never slowed down.
 */
export function useKnowledgeReadiness(projectId: string | null) {
  const status = useKnowledgeStore((s) => s.status);
  const totals = useKnowledgeStore((s) => s.totals);
  const statusState = useKnowledgeStore((s) => s.statusState);
  const error = useKnowledgeStore((s) => s.error);
  const fetchStatus = useKnowledgeStore((s) => s.fetchStatus);

  React.useEffect(() => {
    if (!projectId) return;
    void fetchStatus(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const active = status === "PENDING" || status === "PROCESSING";
  React.useEffect(() => {
    if (!projectId || !active) return;
    const timer = setInterval(() => {
      if (document.visibilityState !== "hidden") void fetchStatus(projectId);
    }, POLL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, active]);

  return { status, totals, statusState, error };
}
