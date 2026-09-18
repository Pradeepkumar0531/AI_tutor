import { cn } from "@/lib/utils";

/**
 * StudyAI skeleton system — presentational placeholders shown ONLY while a
 * real request is pending (request state === loading). They never carry data,
 * never fake progress, and unmount the moment loading settles. Screen readers
 * get exactly one announcement per loading region via SectionLoading.
 */

function Bar({ className, shimmer = true }: { className?: string; shimmer?: boolean }) {
  return <div aria-hidden="true" className={cn("skel", shimmer && "skel-shimmer", className)} />;
}

/** Single live region for a loading area: one polite announcement, shapes hidden. */
export function SectionLoading({
  label,
  children,
  className,
}: {
  label: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div role="status" aria-busy="true" aria-label={label} className={className}>
      <span className="sr-only">{label}</span>
      {children}
    </div>
  );
}

/** Optional contextual hint shown only after a slow threshold (real waiting). */
export function SlowHint({ show, children }: { show: boolean; children: React.ReactNode }) {
  if (!show) return null;
  return <p className="mt-2 text-xs text-muted-foreground">{children}</p>;
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  const widths = ["w-full", "w-11/12", "w-4/5", "w-3/5", "w-2/3"];
  return (
    <div className={cn("flex flex-col gap-2", className)} aria-hidden="true">
      {Array.from({ length: lines }).map((_, i) => (
        <Bar key={i} className={cn("h-3.5", widths[i % widths.length])} />
      ))}
    </div>
  );
}

export function SkeletonHeading({ className }: { className?: string }) {
  return <Bar className={cn("h-7 w-2/3", className)} />;
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn("rounded-[10px] border bg-card p-5", className)}>
      <Bar className="h-5 w-1/3" />
      <div className="mt-3 flex flex-col gap-2">
        <Bar className="h-3.5 w-full" />
        <Bar className="h-3.5 w-5/6" />
      </div>
    </div>
  );
}

/** Space/project card shape: icon tile + title + badges, description, meta row. */
export function SkeletonEntryCards({ count = 3 }: { count?: number }) {
  return (
    <div aria-hidden="true" className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-[10px] border bg-card">
          <div className="flex items-start justify-between gap-2 p-4 pb-3">
            <div className="flex min-w-0 items-center gap-2.5">
              <Bar className="h-8 w-8 shrink-0 rounded-lg" shimmer={false} />
              <Bar className="h-4 w-28" />
            </div>
            <Bar className="h-5 w-16 shrink-0 rounded-full" shimmer={false} />
          </div>
          <div className="px-4 pb-4">
            <Bar className="h-3.5 w-full" />
            <Bar className="mt-2 h-3.5 w-2/3" shimmer={false} />
            <Bar className="mt-3 h-3 w-28" shimmer={false} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonStat({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cn("rounded-[10px] border bg-card p-4", className)}>
      <Bar className="h-3 w-20" shimmer={false} />
      <Bar className="mt-2 h-7 w-16" />
    </div>
  );
}

export function SkeletonList({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div aria-hidden="true" className={cn("flex flex-col gap-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3 rounded-[10px] border bg-card px-3 py-2.5">
          <Bar className="h-8 w-8 shrink-0 rounded-lg" shimmer={false} />
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <Bar className="h-3.5 w-2/3" />
            <Bar className="h-3 w-1/3" shimmer={false} />
          </div>
        </div>
      ))}
    </div>
  );
}

export function SkeletonTable({
  rows = 4,
  cols = 4,
  className,
}: {
  rows?: number;
  cols?: number;
  className?: string;
}) {
  return (
    <div
      aria-hidden="true"
      className={cn("overflow-hidden rounded-[10px] border bg-card", className)}
    >
      <div className="flex gap-3 border-b bg-secondary/50 px-3 py-2.5">
        {Array.from({ length: cols }).map((_, i) => (
          <Bar key={i} className="h-3 flex-1" shimmer={false} />
        ))}
      </div>
      <div className="flex flex-col gap-px">
        {Array.from({ length: rows }).map((_, r) => (
          <div key={r} className="flex gap-3 px-3 py-2.5">
            {Array.from({ length: cols }).map((_, c) => (
              <Bar key={c} className="h-3.5 flex-1" shimmer={r === 0} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonChart({ className }: { className?: string }) {
  const heights = ["35%", "55%", "40%", "70%", "52%", "80%", "62%", "45%"];
  return (
    <div aria-hidden="true" className={cn("rounded-[10px] border bg-card p-4", className)}>
      <Bar className="h-4 w-32" shimmer={false} />
      <div className="mt-3 flex h-36 items-end gap-2">
        {heights.map((h, i) => (
          <div
            key={i}
            className="skel w-full rounded-sm"
            style={{ height: h, animationDelay: `${(i % 4) * 0.12}s` }}
          />
        ))}
      </div>
    </div>
  );
}

export function SkeletonAvatar({ className }: { className?: string }) {
  return <Bar className={cn("h-8 w-8 shrink-0 rounded-full", className)} shimmer={false} />;
}

/** Indeterminate progress — honest "working, no percentage" indicator. */
export function SkeletonProgress({ label, className }: { label?: string; className?: string }) {
  return (
    <div className={className}>
      {label ? <p className="mb-1.5 text-xs text-muted-foreground">{label}</p> : null}
      <div
        className="h-1.5 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-label={label ?? "Working"}
      >
        <div className="skel-indeterminate-bar h-full w-1/3 rounded-full bg-primary" />
      </div>
    </div>
  );
}

export function SkeletonTimeline({ items = 3 }: { items?: number }) {
  return (
    <ul aria-hidden="true" className="flex flex-col gap-3">
      {Array.from({ length: items }).map((_, i) => (
        <li key={i} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className="skel h-2.5 w-2.5 rounded-full" />
            {i < items - 1 ? <div className="skel mt-1 w-px flex-1" /> : null}
          </div>
          <div className="flex-1 pb-1">
            <Bar className="h-3.5 w-1/2" />
            <Bar className="mt-1.5 h-3 w-1/4" shimmer={false} />
          </div>
        </li>
      ))}
    </ul>
  );
}

export function SkeletonTutorMessage({ thinking = false }: { thinking?: boolean }) {
  return (
    <div className="flex flex-col gap-3" aria-hidden="true">
      <div className="flex justify-end">
        <div className="skel h-10 w-2/3 rounded-[10px] rounded-br-sm" />
      </div>
      <div className="flex justify-start">
        <div className="w-3/4 rounded-[10px] rounded-bl-sm border bg-card px-3.5 py-3">
          {thinking ? (
            <span className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
              <span className="flex gap-1" aria-hidden="true">
                <span className="skel-dot h-1.5 w-1.5 rounded-full bg-primary" />
                <span className="skel-dot h-1.5 w-1.5 rounded-full bg-primary" />
                <span className="skel-dot h-1.5 w-1.5 rounded-full bg-primary" />
              </span>
              Thinking about your project…
            </span>
          ) : null}
          <Bar className="h-3.5 w-full" />
          <Bar className="mt-2 h-3.5 w-11/12" />
          <Bar className="mt-2 h-3.5 w-3/5" shimmer={false} />
        </div>
      </div>
    </div>
  );
}

export function SkeletonQuizQuestion({ options = 4 }: { options?: number }) {
  return (
    <div aria-hidden="true" className="rounded-[10px] border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <Bar className="h-4 w-11/12" />
          <Bar className="mt-2 h-4 w-2/3" />
        </div>
        <Bar className="h-5 w-14 shrink-0 rounded-full" shimmer={false} />
      </div>
      <div className="mt-3 flex flex-col gap-1.5">
        {Array.from({ length: options }).map((_, i) => (
          <div key={i} className="flex items-center gap-2.5 rounded-lg border px-3 py-2.5">
            <div className="skel h-4 w-4 shrink-0 rounded-full" />
            <Bar className="h-3.5 flex-1" shimmer={i === 0} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonConceptRows({ rows = 3 }: { rows?: number }) {
  return (
    <ul aria-hidden="true" className="flex flex-col gap-2">
      {Array.from({ length: rows }).map((_, i) => (
        <li key={i} className="rounded-[10px] border bg-card p-3.5">
          <div className="flex items-center justify-between gap-2">
            <Bar className="h-4 w-1/2" />
            <Bar className="h-5 w-20 shrink-0 rounded-full" shimmer={false} />
          </div>
          <Bar className="mt-2.5 h-1.5 w-full rounded-full" />
          <Bar className="mt-1.5 h-3 w-2/3" shimmer={false} />
        </li>
      ))}
    </ul>
  );
}
