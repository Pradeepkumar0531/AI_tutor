import * as React from "react";
import { useNavigate } from "react-router-dom";
import { BookOpen, Bot, Check, Flag, Lightbulb, Play, Tag, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLabel, SectionLoading, SkeletonCard } from "@/components/ui";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useRecommendationsStore } from "@/stores/useRecommendationsStore";
import type { Recommendation } from "@/api/recommendations";

function ActionButtons({
  projectId,
  rec,
  disabled,
}: {
  projectId: string;
  rec: Recommendation;
  disabled: boolean;
}) {
  const navigate = useNavigate();
  const practiceConcept = useAssessmentStore((s) => s.practiceConcept);

  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {rec.actions.includes("open_material") && rec.materialId ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => navigate(`/projects/${projectId}/materials/${rec.materialId}`)}
        >
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          {rec.type === "REVIEW_CONCEPT" ? "Review Material" : "Read Material"}
        </Button>
      ) : null}
      {rec.actions.includes("practice_quiz") && rec.conceptId ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
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
          variant="outline"
          size="sm"
          disabled={disabled}
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

function RecommendationCard({ projectId, rec }: { projectId: string; rec: Recommendation }) {
  const complete = useRecommendationsStore((s) => s.complete);
  const dismiss = useRecommendationsStore((s) => s.dismiss);
  const busyId = useRecommendationsStore((s) => s.busyId);
  const busy = busyId === rec.id;

  return (
    <li className="rounded-lg border p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="font-medium">{rec.title}</p>
        <Badge tone="default">
          <span className="inline-flex items-center gap-1">
            <Flag className="h-3 w-3" aria-hidden="true" />
            Priority {rec.priority}
          </span>
        </Badge>
      </div>
      {rec.reason ? <p className="mt-1 text-sm text-muted-foreground">{rec.reason}</p> : null}
      {rec.conceptName ? (
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Tag className="h-3.5 w-3.5" aria-hidden="true" />
          Concept: {rec.conceptName}
        </p>
      ) : null}
      <ActionButtons projectId={projectId} rec={rec} disabled={busy} />
      <div className="mt-2 flex gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => void complete(projectId, rec.id)}
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
        >
          <X className="h-3.5 w-3.5" aria-hidden="true" />
          Dismiss
        </Button>
      </div>
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

  React.useEffect(() => {
    if (visible) void fetchList(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, visible]);

  return (
    <section
      aria-labelledby="recommendations-heading"
      id="section-recommendations"
      ref={sectionRef}
      className="scroll-mt-24"
    >
      <SectionLabel id="recommendations-heading">Next action</SectionLabel>
      <Card className="mt-2 border-primary/25">
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
          <ul className="space-y-2">
            {items.map((rec) => (
              <RecommendationCard key={rec.id} projectId={projectId} rec={rec} />
            ))}
          </ul>
        </CardContent>
      </Card>
    </section>
  );
}
