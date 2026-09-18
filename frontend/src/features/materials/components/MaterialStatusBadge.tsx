import { CheckCircle2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { MaterialStatus } from "@/types";

const TONE: Record<MaterialStatus, "info" | "success" | "danger" | "default" | "warning"> = {
  QUEUED: "info",
  PROCESSING: "info",
  READY: "success",
  FAILED: "danger",
};

const LABEL: Record<MaterialStatus, string> = {
  QUEUED: "Queued",
  PROCESSING: "Processing",
  READY: "Ready",
  FAILED: "Failed",
};

export function MaterialStatusBadge({ status }: { status: MaterialStatus }) {
  const processing = status === "QUEUED" || status === "PROCESSING";
  return (
    <span className="inline-flex items-center gap-1.5">
      {processing ? (
        <span
          className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground border-t-transparent"
          aria-hidden="true"
        />
      ) : null}
      {status === "READY" ? (
        <CheckCircle2 className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
      ) : null}
      {status === "FAILED" ? (
        <XCircle className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
      ) : null}
      <Badge tone={TONE[status]}>{LABEL[status]}</Badge>
    </span>
  );
}
