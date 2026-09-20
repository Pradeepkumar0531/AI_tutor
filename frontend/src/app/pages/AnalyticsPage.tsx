import { Activity, BarChart3, TriangleAlert } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import { PageContainer, PageHeader } from "@/components/layout/PageHeader";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  EmptyState,
  ErrorState,
  SectionLoading,
  SkeletonChart,
  SkeletonList,
  SkeletonStat,
} from "@/components/ui";
import { useHomeStore } from "@/stores/useHomeStore";

export function AnalyticsPage() {
  const summary = useHomeStore((s) => s.summary);
  const state = useHomeStore((s) => s.summaryState);
  const error = useHomeStore((s) => s.error);
  const fetchSummary = useHomeStore((s) => s.fetchSummary);

  React.useEffect(() => {
    void fetchSummary();
  }, [fetchSummary]);

  return (
    <PageContainer>
      <PageHeader
        title="Global analytics"
        description="Learning activity aggregated across all your spaces and projects. Only your data — never another learner's."
        eyebrow="Analytics"
        icon={BarChart3}
        crumbs={[{ label: "Analytics" }]}
      />
      {state === "loading" || state === "idle" ? (
        <SectionLoading label="Loading global analytics" className="flex flex-col gap-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <SkeletonStat />
            <SkeletonStat />
            <SkeletonStat />
            <SkeletonStat />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <SkeletonList rows={3} />
            <SkeletonChart />
          </div>
        </SectionLoading>
      ) : null}
      {state === "error" ? (
        <ErrorState
          title="Could not load analytics"
          description={error ?? ""}
          onRetry={fetchSummary}
        />
      ) : null}
      {state === "ready" && summary ? (
        summary.projects === 0 ? (
          <EmptyState
            title="No learning data yet"
            description="Global analytics appear after your first space, project, and material."
          />
        ) : (
          <div className="flex flex-col gap-6">
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-[10px] border bg-card p-4">
                <p className="eyebrow">Tutor sessions</p>
                <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.tutorMessages}
                </p>
                <p className="mt-1.5 text-xs text-muted-foreground">messages</p>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <p className="eyebrow">Quizzes taken</p>
                <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.assessments}
                </p>
                <p className="mt-1.5 text-xs text-muted-foreground">assessments</p>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <p className="eyebrow">Questions answered</p>
                <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.questionsAnswered}
                </p>
                <p className="mt-1.5 text-xs text-muted-foreground">across all quizzes</p>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <p className="eyebrow">Materials</p>
                <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.materialsReady}
                  <span className="text-sm font-normal text-muted-foreground">
                    /{summary.materials}
                  </span>
                </p>
                <p className="mt-1.5 text-xs text-muted-foreground">ready / total</p>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <p className="eyebrow">Projects</p>
                <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.projects}
                </p>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <p className="eyebrow">Mastery (avg)</p>
                <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.masteryConcepts > 0 ? `${Math.round(summary.masteryAvg)}%` : "—"}
                </p>
                <p className="mt-1.5 text-xs text-muted-foreground">
                  {summary.masteryConcepts} concepts
                </p>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <Card variant="light">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <TriangleAlert className="h-5 w-5 text-primary" aria-hidden="true" />
                    Concepts requiring attention
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  {summary.attention.length === 0 ? (
                    <p className="text-sm text-muted-foreground">Nothing needs attention.</p>
                  ) : (
                    <ul className="flex flex-col gap-1 text-sm">
                      {summary.attention.map((a) => (
                        <li key={`${a.projectId}-${a.concept}`}>
                          <Link to={`/projects/${a.projectId}`} className="underline">
                            {a.concept}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </CardContent>
              </Card>
              <Card variant="light">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Activity className="h-5 w-5 text-primary" aria-hidden="true" />
                    Engagement
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <dl className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <dt className="text-muted-foreground">Active recommendations</dt>
                      <dd className="font-medium">{summary.activeRecommendations}</dd>
                    </div>
                    <div>
                      <dt className="text-muted-foreground">Last activity</dt>
                      <dd className="font-medium">
                        {summary.lastActivityAt
                          ? new Date(summary.lastActivityAt).toLocaleString()
                          : "—"}
                      </dd>
                    </div>
                  </dl>
                </CardContent>
              </Card>
            </div>
          </div>
        )
      ) : null}
    </PageContainer>
  );
}
