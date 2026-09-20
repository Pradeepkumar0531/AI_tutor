import * as React from "react";
import { GraduationCap, History, Minus, Target, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  ProgressBar,
  SectionLabel,
  SectionLoading,
  SkeletonConceptRows,
  SkeletonStat,
  SkeletonText,
  SlowHint,
} from "@/components/ui";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { useSlowHint } from "@/hooks/useSlowHint";
import { useMasteryStore } from "@/stores/useMasteryStore";
import type { MasteryItem } from "@/api/mastery";

function trendLabel(trend: MasteryItem["trend"]): string {
  if (trend === "IMPROVING") return "Improving";
  if (trend === "DECLINING") return "Declining";
  return "Stable";
}

function MasteryRow({ item, onOpen }: { item: MasteryItem; onOpen: () => void }) {
  return (
    <li className="rounded-[10px] border bg-card p-3.5">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          className="text-left text-sm font-medium underline-offset-4 hover:underline"
          onClick={onOpen}
        >
          {item.conceptName}
        </button>
        <Badge
          tone={
            item.trend === "IMPROVING"
              ? "success"
              : item.trend === "DECLINING"
                ? "danger"
                : "default"
          }
        >
          <span className="inline-flex items-center gap-1">
            {item.trend === "IMPROVING" ? (
              <TrendingUp className="h-3 w-3" aria-hidden="true" />
            ) : item.trend === "DECLINING" ? (
              <TrendingDown className="h-3 w-3" aria-hidden="true" />
            ) : (
              <Minus className="h-3 w-3" aria-hidden="true" />
            )}
            {trendLabel(item.trend)}
          </span>
        </Badge>
      </div>
      {item.hasEvidence ? (
        <div className="mt-2.5">
          <ProgressBar
            value={item.masteryScore * 100}
            label={`Mastery ${Math.round(item.masteryScore * 100)}%`}
          />
          <p className="font-mono-tech mt-1.5 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
            Confidence {Math.round(item.confidence * 100)}% · {item.evidenceCount}{" "}
            {item.evidenceCount === 1 ? "assessment" : "assessments"}
            {item.recentPerformance.length > 0
              ? ` · Recent: ${item.recentPerformance.join(" ")}`
              : ""}
          </p>
        </div>
      ) : (
        <p className="mt-1.5 text-sm text-muted-foreground">
          Not yet established — no assessed evidence for this concept.
        </p>
      )}
    </li>
  );
}

function MasteryDetail() {
  const detail = useMasteryStore((s) => s.detail);
  const detailState = useMasteryStore((s) => s.detailState);
  const history = useMasteryStore((s) => s.history);
  const historyState = useMasteryStore((s) => s.historyState);
  const error = useMasteryStore((s) => s.error);
  const backToList = useMasteryStore((s) => s.backToList);

  if (detailState === "loading")
    return (
      <SectionLoading label="Loading mastery detail">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <SkeletonStat />
          <SkeletonStat />
          <SkeletonStat />
          <SkeletonStat />
        </div>
        <SkeletonText lines={2} className="mt-3" />
      </SectionLoading>
    );
  if (detailState === "error" || !detail) {
    return <ErrorState title="Could not load mastery" description={error ?? undefined} />;
  }
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <h4 className="flex items-center gap-2 text-lg font-semibold">
          <Target className="h-5 w-5 text-primary" aria-hidden="true" />
          Concept: {detail.conceptName}
        </h4>
        <Button type="button" variant="outline" size="sm" onClick={backToList}>
          All concepts
        </Button>
      </div>
      <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
        <div className="rounded-lg border p-2">
          <p className="text-xs text-muted-foreground">Mastery</p>
          <p className="text-xl font-bold">
            {detail.hasEvidence ? `${Math.round(detail.masteryScore * 100)}%` : "—"}
          </p>
        </div>
        <div className="rounded-lg border p-2">
          <p className="text-xs text-muted-foreground">Confidence</p>
          <p className="text-xl font-bold">{Math.round(detail.confidence * 100)}%</p>
        </div>
        <div className="rounded-lg border p-2">
          <p className="text-xs text-muted-foreground">Trend</p>
          <p className="text-xl font-bold">{trendLabel(detail.trend)}</p>
        </div>
        <div className="rounded-lg border p-2">
          <p className="text-xs text-muted-foreground">Evidence</p>
          <p className="text-xl font-bold">
            {detail.evidenceCount} / {detail.evidenceQuestions}
          </p>
          <p className="text-xs text-muted-foreground">assessments / questions</p>
        </div>
      </div>
      {detail.recentPerformance.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          Recent performance: {detail.recentPerformance.join(" ")}
        </p>
      ) : null}
      {!detail.hasEvidence ? (
        <p className="text-sm text-muted-foreground">
          Mastery is not yet established for this concept — complete a quiz that covers it to build
          evidence.
        </p>
      ) : null}
      <div>
        <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
          <History className="h-4 w-4 text-primary" aria-hidden="true" />
          History
        </p>
        {historyState === "loading" ? (
          <SectionLoading label="Loading mastery history">
            <SkeletonText lines={2} />
          </SectionLoading>
        ) : null}
        {history.length === 0 && historyState === "ready" ? (
          <EmptyState
            title="No history yet."
            description="Mastery changes will appear here after assessed quizzes."
          />
        ) : null}
        <ul className="space-y-1">
          {history.map((h) => (
            <li key={h.id} className="rounded-lg border p-2 text-sm">
              {h.previousScore != null ? `${Math.round(h.previousScore * 100)}% → ` : ""}
              <span className="font-medium">{Math.round(h.newScore * 100)}%</span>
              {" · "}
              <span className="text-muted-foreground">
                {new Date(h.createdAt).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function MasterySection({ projectId }: { projectId: string }) {
  const items = useMasteryStore((s) => s.items);
  const total = useMasteryStore((s) => s.total);
  const listState = useMasteryStore((s) => s.listState);
  const sort = useMasteryStore((s) => s.sort);
  const detail = useMasteryStore((s) => s.detail);
  const error = useMasteryStore((s) => s.error);
  const fetchList = useMasteryStore((s) => s.fetchList);
  const openDetail = useMasteryStore((s) => s.openDetail);
  const [sectionRef, visible] = useFirstVisible<HTMLElement>();
  const masteryLoading = listState === "loading" && !detail && items.length === 0;
  const slowMastery = useSlowHint(masteryLoading);

  React.useEffect(() => {
    if (visible) void fetchList(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, visible]);

  return (
    <section
      aria-labelledby="mastery-heading"
      id="section-mastery"
      ref={sectionRef}
      className="scroll-mt-24"
    >
      <SectionLabel id="mastery-heading">Mastery</SectionLabel>
      <Card variant="light" className="mt-2">
        <CardHeader className="pb-3">
          <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
              <GraduationCap className="h-4 w-4" aria-hidden="true" />
            </span>
            Concept mastery
            {total > 0 ? (
              <span className="font-mono-tech text-[11px] font-normal text-muted-foreground">
                {total} tracked
              </span>
            ) : null}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {detail ? (
            <MasteryDetail />
          ) : (
            <>
              <div className="flex items-center gap-2 text-sm">
                <label htmlFor="mastery-sort">Sort</label>
                <select
                  id="mastery-sort"
                  value={sort}
                  onChange={(e) => void fetchList(projectId, e.target.value)}
                  className="rounded-md border px-2 py-1 text-sm"
                >
                  <option value="lowest">Lowest mastery</option>
                  <option value="recent">Recently updated</option>
                  <option value="name">Concept name</option>
                </select>
                {total > 0 ? (
                  <span className="text-muted-foreground">
                    {total} tracked concept{total === 1 ? "" : "s"}
                  </span>
                ) : null}
              </div>
              {masteryLoading ? (
                <SectionLoading label="Loading mastery">
                  <SkeletonConceptRows rows={3} />
                  <SlowHint show={slowMastery}>Still loading mastery estimates…</SlowHint>
                </SectionLoading>
              ) : null}
              {listState === "error" ? (
                <ErrorState
                  title="Could not load mastery"
                  description={error ?? undefined}
                  onRetry={() => void fetchList(projectId)}
                />
              ) : null}
              {listState === "ready" && items.length === 0 ? (
                <EmptyState
                  title="No mastery yet."
                  description="Complete a quiz to build per-concept mastery estimates. Estimates appear here — never as zero knowledge without evidence."
                  icon={GraduationCap}
                />
              ) : null}
              <ul className="space-y-2">
                {items.map((item) => (
                  <MasteryRow
                    key={item.conceptId}
                    item={item}
                    onOpen={() => void openDetail(projectId, item.conceptId)}
                  />
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
