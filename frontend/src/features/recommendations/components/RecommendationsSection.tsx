import * as React from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, Bot, Check, Lightbulb, Play, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLabel, SectionLoading, SkeletonCard } from "@/components/ui";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useRecommendationsStore } from "@/stores/useRecommendationsStore";
import { cn } from "@/lib/utils";
import type { Recommendation } from "@/api/recommendations";

/** The single most actionable step, in backend-confirmed priority order. */
function primaryAction(
  rec: Recommendation,
): "practice_quiz" | "open_material" | "ask_tutor" | null {
  if (rec.actions.includes("practice_quiz") && rec.conceptId) return "practice_quiz";
  if (rec.actions.includes("open_material") && rec.materialId) return "open_material";
  if (rec.actions.includes("ask_tutor") && rec.conceptId) return "ask_tutor";
  return null;
}

function ActionButtons({
  projectId,
  rec,
  disabled,
  dark = false,
}: {
  projectId: string;
  rec: Recommendation;
  disabled: boolean;
  dark?: boolean;
}) {
  const navigate = useNavigate();
  const practiceConcept = useAssessmentStore((s) => s.practiceConcept);
  const primary = primaryAction(rec);
  const ghostOnDark =
    "border-white/20 text-primary-foreground hover:bg-white/10 hover:text-primary-foreground";

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {rec.actions.includes("open_material") && rec.materialId ? (
        <Button
          type="button"
          variant={primary === "open_material" ? (dark ? "secondary" : "default") : "outline"}
          size="sm"
          disabled={disabled}
          className={cn(dark && primary !== "open_material" && ghostOnDark)}
          onClick={() => navigate(`/projects/${projectId}/materials/${rec.materialId}`)}
        >
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          {rec.type === "REVIEW_CONCEPT" ? "Review Material" : "Read Material"}
        </Button>
      ) : null}
      {rec.actions.includes("practice_quiz") && rec.conceptId ? (
        <Button
          type="button"
          variant={primary === "practice_quiz" ? (dark ? "secondary" : "default") : "outline"}
          size="sm"
          disabled={disabled}
          className={cn(dark && primary !== "practice_quiz" && ghostOnDark)}
          onClick={() => {
            // The quiz workspace lives on its own tab: take the learner there
            // once the practice attempt exists.
            void practiceConcept(projectId, rec.conceptId as string)
              .then(() => navigate(`/projects/${projectId}/quiz`))
              .catch(() => {});
          }}
        >
          <Play className="h-3.5 w-3.5" aria-hidden="true" />
          Practice
        </Button>
      ) : null}
      {rec.actions.includes("ask_tutor") && rec.conceptId ? (
        <Button
          type="button"
          variant={primary === "ask_tutor" ? (dark ? "secondary" : "default") : "outline"}
          size="sm"
          disabled={disabled}
          className={cn(dark && primary !== "ask_tutor" && ghostOnDark)}
          onClick={() =>
            navigate(`/projects/${projectId}/tutor?tutor=${encodeURIComponent(rec.conceptName)}`)
          }
        >
          <Bot className="h-3.5 w-3.5" aria-hidden="true" />
          Ask Tutor
        </Button>
      ) : null}
    </div>
  );
}

function DoneButtons({
  projectId,
  rec,
  dark = false,
}: {
  projectId: string;
  rec: Recommendation;
  dark?: boolean;
}) {
  const complete = useRecommendationsStore((s) => s.complete);
  const dismiss = useRecommendationsStore((s) => s.dismiss);
  const busyId = useRecommendationsStore((s) => s.busyId);
  const busy = busyId === rec.id;

  return (
    <div className="mt-2 flex gap-2">
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => void complete(projectId, rec.id)}
        className={cn(
          dark
            ? "text-primary-foreground/75 hover:bg-white/10 hover:text-primary-foreground"
            : "text-muted-foreground",
        )}
      >
        <Check className="h-3.5 w-3.5" aria-hidden="true" />
        {busy ? "Working…" : "Mark done"}
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        disabled={busy}
        onClick={() => void dismiss(projectId, rec.id)}
        className={cn(
          dark
            ? "text-primary-foreground/75 hover:bg-white/10 hover:text-primary-foreground"
            : "text-muted-foreground",
        )}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
        Dismiss
      </Button>
    </div>
  );
}

function PrimaryCard({ projectId, rec }: { projectId: string; rec: Recommendation }) {
  const busyId = useRecommendationsStore((s) => s.busyId);
  const busy = busyId === rec.id;
  const reason = rec.reason?.trim() || rec.description?.trim() || null;

  return (
    <li className="card-dark rounded-[10px] border p-4 sm:p-5">
      <p className="eyebrow">Recommended next</p>
      <p className="mt-1.5 text-lg font-semibold leading-snug tracking-tight">{rec.title}</p>
      {reason ? (
        <p className="mt-1 max-w-xl text-sm leading-relaxed text-primary-foreground/75">{reason}</p>
      ) : null}
      <ActionButtons projectId={projectId} rec={rec} disabled={busy} dark />
      <div className="mt-1 flex items-center justify-between gap-2">
        <span className="text-[11px] text-primary-foreground/55">Priority {rec.priority}</span>
        <DoneButtons projectId={projectId} rec={rec} dark />
      </div>
    </li>
  );
}

function SecondaryCard({ projectId, rec }: { projectId: string; rec: Recommendation }) {
  const busyId = useRecommendationsStore((s) => s.busyId);
  const busy = busyId === rec.id;
  const reason = rec.reason?.trim() || rec.description?.trim() || null;

  return (
    <li className="rounded-lg border bg-card p-3">
      <div className="flex items-baseline justify-between gap-2">
        <p className="font-medium">{rec.title}</p>
        <span className="shrink-0 text-[11px] text-muted-foreground">Priority {rec.priority}</span>
      </div>
      {reason ? (
        <p className="mt-0.5 line-clamp-2 text-sm text-muted-foreground">{reason}</p>
      ) : null}
      <ActionButtons projectId={projectId} rec={rec} disabled={busy} />
      <DoneButtons projectId={projectId} rec={rec} />
    </li>
  );
}

export function RecommendationsSection({ projectId }: { projectId: string }) {
  const items = useRecommendationsStore((s) => s.items);
  const listState = useRecommendationsStore((s) => s.listState);
  const error = useRecommendationsStore((s) => s.error);
  const fetchList = useRecommendationsStore((s) => s.fetchList);
  const growth = useGrowthStore((s) => s.growth);
  const [sectionRef, visible] = useFirstVisible<HTMLElement>();
  const [showAll, setShowAll] = React.useState(false);

  React.useEffect(() => {
    if (visible) void fetchList(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, visible]);

  // Highest priority first; one primary action plus up to two compact
  // follow-ups, with the rest one click away (real data, never dropped).
  const ordered = React.useMemo(() => [...items].sort((a, b) => a.priority - b.priority), [items]);
  const [primary, ...rest] = ordered;
  const secondary = showAll ? rest : rest.slice(0, 2);

  return (
    <section
      aria-labelledby="recommendations-heading"
      id="section-recommendations"
      ref={sectionRef}
      className="scroll-mt-24"
    >
      <SectionLabel id="recommendations-heading">Next action</SectionLabel>
      <Card variant="light" className="mt-2 border-primary/25">
        <CardHeader className="pb-3">
          <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
              <Lightbulb className="h-4 w-4" aria-hidden="true" />
            </span>
            Recommended next action
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {listState === "loading" && items.length === 0 ? (
            <SectionLoading label="Loading recommendations">
              <div className="flex flex-col gap-2">
                <SkeletonCard />
                <SkeletonCard />
              </div>
            </SectionLoading>
          ) : null}
          {listState === "error" ? (
            <ErrorState
              title="Could not load recommendations"
              description={error ?? undefined}
              onRetry={() => void fetchList(projectId)}
            />
          ) : null}
          {listState === "ready" && items.length === 0 ? (
            growth && growth.hasEvidence ? (
              <EmptyState
                title="You're caught up for now."
                description="Continue learning or take another assessment to update your progress."
              />
            ) : (
              <EmptyState
                title="No recommendations yet."
                description="Complete an assessment to establish your learning baseline."
              />
            )
          ) : null}
          {primary ? (
            <>
              <ul className="space-y-2">
                <PrimaryCard key={primary.id} projectId={projectId} rec={primary} />
              </ul>
              {secondary.length > 0 ? (
                <>
                  <p className="eyebrow pt-2">Also worth reviewing</p>
                  <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {secondary.map((rec) => (
                      <SecondaryCard key={rec.id} projectId={projectId} rec={rec} />
                    ))}
                  </ul>
                </>
              ) : null}
              {rest.length > 2 && !showAll ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowAll(true)}
                  className="text-muted-foreground"
                >
                  Show all {ordered.length} recommendations
                </Button>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
