import { cn } from "@/lib/utils";

export function SectionLabel({
  children,
  className,
  ...props
}: React.HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p className={cn("eyebrow", className)} {...props}>
      {children}
    </p>
  );
}

export function StatCard({
  label,
  value,
  sub,
  icon,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  icon?: React.ReactNode;
}) {
  return (
    <div className="card-accent rounded-[10px] border bg-card p-4">
      <div className="flex items-center justify-between gap-2">
        <p className="eyebrow">{label}</p>
        {icon ? (
          <span className="text-primary" aria-hidden="true">
            {icon}
          </span>
        ) : null}
      </div>
      <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">{value}</p>
      {sub ? <div className="mt-1.5 text-xs text-muted-foreground">{sub}</div> : null}
    </div>
  );
}

export function ProgressBar({
  value,
  max = 100,
  label,
  tone = "primary",
}: {
  value: number;
  max?: number;
  label?: string;
  tone?: "primary" | "success" | "warning" | "danger";
}) {
  const pct = Math.min(100, Math.max(0, max > 0 ? (value / max) * 100 : 0));
  const fill =
    tone === "danger"
      ? "bg-destructive"
      : tone === "warning"
        ? "bg-muted-foreground"
        : "bg-primary";
  return (
    <div>
      {label ? (
        <div className="mb-1 flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <span>{label}</span>
          <span className="font-mono-tech tabular-nums">{Math.round(pct)}%</span>
        </div>
      ) : null}
      <div
        className="h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={Math.round(pct)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? "Progress"}
      >
        <div
          className={cn("h-full rounded-full transition-all", fill)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
