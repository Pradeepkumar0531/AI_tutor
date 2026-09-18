import * as React from "react";

import { TERMINAL_MATERIAL_STATUSES, useMaterialsStore } from "@/stores/useMaterialsStore";

const POLL_MS = 3000;

/** Poll non-terminal materials until they settle. Server remains authoritative:
 * each tick re-reads status from the API; hidden tabs pause automatically and
 * timers are cleaned up on unmount. No fake progress is ever synthesized. */
export function useMaterialPolling(projectId: string | null) {
  const items = useMaterialsStore((s) => s.items);

  const pendingSignature = items
    .filter((m) => !TERMINAL_MATERIAL_STATUSES.includes(m.status))
    .map((m) => `${m.id}:${m.status}`)
    .sort()
    .join(",");

  React.useEffect(() => {
    if (!projectId || !pendingSignature) return;
    const ids = pendingSignature.split(",").map((s) => s.split(":")[0]);
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      const { refreshOne } = useMaterialsStore.getState();
      for (const id of ids) void refreshOne(projectId, id as string);
    };
    const timer = setInterval(tick, POLL_MS);
    return () => clearInterval(timer);
  }, [projectId, pendingSignature]);
}
