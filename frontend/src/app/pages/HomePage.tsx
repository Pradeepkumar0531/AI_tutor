import { ArrowRight, ArrowUpRight, Bot, ChevronRight, FileText, TriangleAlert } from "lucide-react";
import * as React from "react";
import { Link } from "react-router-dom";

import type { HomeNextAction } from "@/api/home";
import { PageContainer } from "@/components/layout/PageHeader";
import {
  Badge,
  Button,
  Card,
  CardContent,
  EmptyState,
  ErrorState,
  SectionLabel,
  SectionLoading,
  SkeletonHeading,
  SkeletonList,
  SkeletonStat,
  SkeletonText,
  SlowHint,
} from "@/components/ui";
import { useSlowHint } from "@/hooks/useSlowHint";
import { useAuthStore } from "@/stores/useAuthStore";
import { useHomeStore } from "@/stores/useHomeStore";

function greeting(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function firstName(displayName: string | undefined, email: string | undefined): string {
  if (displayName?.trim()) return displayName.trim().split(/\s+/)[0] ?? "there";
  if (email?.includes("@")) return email.split("@")[0] ?? "there";
  return "there";
}

function actionLink(action: HomeNextAction): string {
  if (action.kind === "recommendation" && action.recommendationId) {
    return `/projects/${action.projectId}`;
  }
  if (action.kind === "upload_material") return `/projects/${action.projectId}`;
  return `/projects/${action.projectId}`;
}

export function HomePage() {
  const home = useHomeStore((s) => s.home);
  const state = useHomeStore((s) => s.homeState);
  const error = useHomeStore((s) => s.error);
  const fetchHome = useHomeStore((s) => s.fetchHome);
  const summary = useHomeStore((s) => s.summary);
  const summaryState = useHomeStore((s) => s.summaryState);
  const fetchSummary = useHomeStore((s) => s.fetchSummary);
  const user = useAuthStore((s) => s.user);

  React.useEffect(() => {
    void fetchHome();
  }, [fetchHome]);

  // Partial degradation with real data: if /home fails (e.g. a wake-up
  // spike trips the timeout), fall back to /analytics/summary for the
  // statistics + attention sections instead of failing the whole page.
  // Continue/recent/next-action stay honestly unavailable until retry.
  React.useEffect(() => {
    if (state === "error" && summaryState === "idle") void fetchSummary();
  }, [state, summaryState, fetchSummary]);

  const partial = state === "error" && summaryState === "ready" && summary != null;
  const homeLoading = state === "loading" || state === "idle";
  const slowHome = useSlowHint(homeLoading);

  const name = firstName(user?.displayName, user?.email);

  return (
    <PageContainer>
      <SectionLabel>Learning overview</SectionLabel>
      <h1 className="mt-2 max-w-xl text-[32px] font-semibold leading-[1.15] tracking-tight sm:text-4xl">
        {greeting()}
        <br />
        <span className="text-muted-foreground">Where was I,</span> {name}?
      </h1>

      <div className="mt-6">
        {homeLoading ? (
          <SectionLoading label="Loading your home" className="flex flex-col gap-6">
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <SkeletonStat />
              <SkeletonStat />
              <SkeletonStat />
            </div>
            <div className="overflow-hidden rounded-[10px] bg-primary p-5 sm:p-6">
              <SkeletonHeading className="bg-white/25" />
              <SkeletonText lines={2} className="mt-3 max-w-xl [&>div]:bg-white/25" />
            </div>
            <div className="grid gap-6 md:grid-cols-2">
              <div>
                <SectionLabel>Recent projects</SectionLabel>
                <SkeletonList rows={3} className="mt-2" />
              </div>
              <div>
                <SectionLabel>Areas requiring attention</SectionLabel>
                <SkeletonList rows={2} className="mt-2" />
              </div>
            </div>
            <SlowHint show={slowHome}>Still loading your learning data…</SlowHint>
          </SectionLoading>
        ) : null}
        {state === "error" ? (
          <ErrorState title="Could not load home" description={error ?? ""} onRetry={fetchHome} />
        ) : null}
        {partial && summary ? (
          <div className="mt-4 flex flex-col gap-6" aria-label="Partial home data">
            <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-[10px] border bg-card p-4">
                <dt className="eyebrow">Active projects</dt>
                <dd className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.projects}
                </dd>
                <dd className="mt-1.5 text-xs text-muted-foreground">
                  {summary.materialsReady}/{summary.materials} materials ready
                </dd>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <dt className="eyebrow">Average mastery</dt>
                <dd className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.masteryConcepts > 0 ? `${Math.round(summary.masteryAvg)}%` : "—"}
                </dd>
                <dd className="mt-1.5 text-xs text-muted-foreground">
                  across {summary.masteryConcepts} concepts
                </dd>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <dt className="eyebrow">Study sessions</dt>
                <dd className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {summary.assessments}
                </dd>
                <dd className="mt-1.5 text-xs text-muted-foreground">
                  {summary.questionsAnswered} questions answered
                </dd>
              </div>
            </dl>
            <EmptyState
              title="Continue learning is temporarily unavailable"
              description="Your progress above is live. Retry to restore continue learning, recent projects, and your next action."
            />
            {summary.attention.length > 0 ? (
              <section aria-labelledby="partial-attention-heading">
                <SectionLabel id="partial-attention-heading">
                  Areas requiring attention
                </SectionLabel>
                <Card className="mt-2">
                  <CardContent className="flex flex-col gap-1 p-2">
                    {summary.attention.map((a) => (
                      <Link
                        key={`${a.projectId}-${a.concept}`}
                        to={`/projects/${a.projectId}`}
                        className="group flex items-center justify-between gap-2 rounded-lg px-3 py-2.5 transition-colors hover:bg-secondary"
                      >
                        <span className="flex min-w-0 items-center gap-2">
                          <TriangleAlert
                            className="h-3.5 w-3.5 shrink-0 text-primary"
                            aria-hidden="true"
                          />
                          <span className="truncate text-sm font-medium">{a.concept}</span>
                        </span>
                        <ChevronRight
                          className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary"
                          aria-hidden="true"
                        />
                      </Link>
                    ))}
                  </CardContent>
                </Card>
              </section>
            ) : null}
          </div>
        ) : null}
        {state === "ready" && home ? (
          <div className="flex flex-col gap-6">
            <dl className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="rounded-[10px] border bg-card p-4">
                <dt className="eyebrow">Active projects</dt>
                <dd className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {home.progress.projects}
                </dd>
                <dd className="mt-1.5 text-xs text-muted-foreground">
                  {home.progress.materialsReady}/{home.progress.materials} materials ready
                </dd>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <dt className="eyebrow">Average mastery</dt>
                <dd className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {home.progress.masteryConcepts > 0
                    ? `${Math.round(home.progress.masteryAvg)}%`
                    : "—"}
                </dd>
                <dd className="mt-1.5 text-xs text-muted-foreground">
                  across {home.progress.masteryConcepts} concepts
                </dd>
              </div>
              <div className="rounded-[10px] border bg-card p-4">
                <dt className="eyebrow">Study sessions</dt>
                <dd className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                  {home.progress.assessments}
                </dd>
                <dd className="mt-1.5 text-xs text-muted-foreground">
                  {home.progress.questionsAnswered} questions answered
                </dd>
              </div>
            </dl>

            {home.continueLearning ? (
              <section
                aria-labelledby="continue-heading"
                className="overflow-hidden rounded-[10px] bg-primary text-primary-foreground"
              >
                <div className="flex flex-col gap-4 p-5 sm:p-6">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p
                      id="continue-heading"
                      className="font-mono-tech text-[11px] font-semibold uppercase tracking-[0.14em] opacity-80"
                    >
                      Continue learning
                    </p>
                    <Badge className="border-0 bg-white/15 text-white">
                      <span className="inline-flex items-center gap-1">
                        <FileText className="h-3 w-3" aria-hidden="true" />
                        {home.continueLearning.materials} materials
                      </span>
                    </Badge>
                  </div>
                  <div>
                    <Link
                      to={`/projects/${home.continueLearning.projectId}`}
                      className="text-xl font-semibold tracking-tight hover:underline"
                    >
                      {home.continueLearning.projectName}
                    </Link>
                    <p className="mt-1 max-w-xl text-sm leading-relaxed opacity-85">
                      Next: {home.continueLearning.nextAction.title} —{" "}
                      {home.continueLearning.nextAction.reason}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link to={`/projects/${home.continueLearning.projectId}/tutor`}>
                      <Button className="bg-white text-primary hover:bg-white/90">
                        <Bot className="h-4 w-4" aria-hidden="true" />
                        Open Tutor
                      </Button>
                    </Link>
                    <Link to={`/projects/${home.continueLearning.projectId}/quiz`}>
                      <Button
                        variant="outline"
                        className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white"
                      >
                        Take Quiz
                        <ArrowRight className="h-4 w-4" aria-hidden="true" />
                      </Button>
                    </Link>
                  </div>
                </div>
              </section>
            ) : (
              <EmptyState
                title="Nothing to continue yet"
                description="Create a space and a project, then upload your first material to start learning."
              />
            )}

            <div className="grid gap-6 md:grid-cols-2">
              <section aria-labelledby="recent-heading">
                <SectionLabel id="recent-heading">Recent projects</SectionLabel>
                <Card className="mt-2">
                  <CardContent className="flex flex-col gap-1 p-2">
                    {home.recentProjects.length === 0 ? (
                      <div className="flex items-center gap-2 p-3">
                        <p className="text-sm text-muted-foreground">No projects yet.</p>
                        <Link
                          to="/projects"
                          className="text-sm font-medium text-primary hover:underline"
                        >
                          Browse projects
                        </Link>
                      </div>
                    ) : (
                      home.recentProjects.map((p) => (
                        <Link
                          key={p.id}
                          to={`/projects/${p.id}`}
                          className="group flex items-center justify-between gap-2 rounded-lg px-3 py-2.5 transition-colors hover:bg-secondary"
                        >
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-medium">{p.name}</span>
                            {p.updatedAt ? (
                              <span className="font-mono-tech block text-[11px] text-muted-foreground">
                                {new Date(p.updatedAt).toLocaleDateString()}
                              </span>
                            ) : null}
                          </span>
                          <ArrowUpRight
                            className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary"
                            aria-hidden="true"
                          />
                        </Link>
                      ))
                    )}
                  </CardContent>
                </Card>
              </section>

              <section aria-labelledby="attention-heading">
                <SectionLabel id="attention-heading">Areas requiring attention</SectionLabel>
                <Card className="mt-2">
                  <CardContent className="flex flex-col gap-1 p-2">
                    {home.attention.length === 0 ? (
                      <p className="p-3 text-sm text-muted-foreground">
                        Nothing needs attention right now.
                      </p>
                    ) : (
                      home.attention.map((a) => (
                        <Link
                          key={`${a.projectId}-${a.concept}`}
                          to={`/projects/${a.projectId}`}
                          className="group flex items-center justify-between gap-2 rounded-lg px-3 py-2.5 transition-colors hover:bg-secondary"
                        >
                          <span className="flex min-w-0 items-center gap-2">
                            <TriangleAlert
                              className="h-3.5 w-3.5 shrink-0 text-primary"
                              aria-hidden="true"
                            />
                            <span className="truncate text-sm font-medium">{a.concept}</span>
                          </span>
                          <ChevronRight
                            className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-primary"
                            aria-hidden="true"
                          />
                        </Link>
                      ))
                    )}
                  </CardContent>
                </Card>
              </section>
            </div>

            {home.recommendedAction ? (
              <section aria-labelledby="next-heading">
                <SectionLabel id="next-heading">Recommended next action</SectionLabel>
                <Card className="mt-2 border-primary/25">
                  <CardContent className="flex flex-col gap-2 p-5">
                    <p className="text-[15px] font-semibold tracking-tight">
                      What should I do next?
                    </p>
                    <p className="font-medium">{home.recommendedAction.title}</p>
                    <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      {home.recommendedAction.reason}
                    </p>
                    <div>
                      <Link to={actionLink(home.recommendedAction)}>
                        <Button>
                          Continue
                          <ArrowRight className="h-4 w-4" aria-hidden="true" />
                        </Button>
                      </Link>
                    </div>
                  </CardContent>
                </Card>
              </section>
            ) : null}
          </div>
        ) : null}
      </div>
    </PageContainer>
  );
}
