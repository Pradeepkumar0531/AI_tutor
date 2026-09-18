import * as React from "react";
import { BarChart3, Clock, History, LayoutDashboard, TrendingUp } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import { SectionLabel, SectionLoading, SkeletonChart, SkeletonStat } from "@/components/ui";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { useAnalyticsStore } from "@/stores/useAnalyticsStore";
import type { DateRange } from "@/api/analytics";

const CHART_BLUE = "#123B6D";
const CHART_GRID = "#DDE3EA";
const CHART_TICK = "#667085";

function StatCard({
  label,
  value,
  href,
  sub,
}: {
  label: string;
  value: string;
  href?: string;
  sub?: string;
}) {
  const body = (
    <>
      <p className="eyebrow">{label}</p>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight">{value}</p>
      {sub ? <p className="mt-1 text-xs text-muted-foreground">{sub}</p> : null}
    </>
  );
  return (
    <div className="rounded-[10px] border bg-card p-3">
      {href ? (
        <a href={href} className="block underline-offset-4 hover:underline">
          {body}
        </a>
      ) : (
        body
      )}
    </div>
  );
}

function RangeSelect({ projectId, range }: { projectId: string; range: DateRange }) {
  const fetchDashboard = useAnalyticsStore((s) => s.fetchDashboard);
  return (
    <label className="flex items-center gap-2 text-sm">
      Range
      <select
        aria-label="Activity date range"
        value={range}
        onChange={(e) => void fetchDashboard(projectId, e.target.value as DateRange)}
        className="rounded-md border px-2 py-1 text-sm"
      >
        <option value="7d">7 days</option>
        <option value="30d">30 days</option>
        <option value="90d">90 days</option>
        <option value="all">All time</option>
      </select>
    </label>
  );
}

export function DashboardSection({ projectId }: { projectId: string }) {
  const summary = useAnalyticsStore((s) => s.summary);
  const summaryState = useAnalyticsStore((s) => s.summaryState);
  const activity = useAnalyticsStore((s) => s.activity);
  const activityState = useAnalyticsStore((s) => s.activityState);
  const activityByDay = useAnalyticsStore((s) => s.activityByDay);
  const masteryTrend = useAnalyticsStore((s) => s.masteryTrend);
  const trendsState = useAnalyticsStore((s) => s.trendsState);
  const range = useAnalyticsStore((s) => s.range);
  const error = useAnalyticsStore((s) => s.error);
  const fetchDashboard = useAnalyticsStore((s) => s.fetchDashboard);
  const [sectionRef, visible] = useFirstVisible<HTMLElement>();

  React.useEffect(() => {
    if (visible) void fetchDashboard(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, visible]);

  return (
    <section aria-labelledby="project-analytics-heading" ref={sectionRef}>
      <SectionLabel id="project-analytics-heading">Analytics</SectionLabel>
      <Card className="mt-2">
        <CardHeader className="pb-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
              </span>
              Learning Dashboard
            </CardTitle>
            <RangeSelect projectId={projectId} range={range} />
          </div>
        </CardHeader>
        <CardContent className="space-y-6">
          {summaryState === "loading" && !summary ? (
            <SectionLoading label="Loading dashboard">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <SkeletonStat />
                <SkeletonStat />
                <SkeletonStat />
                <SkeletonStat />
              </div>
              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <SkeletonChart />
                <SkeletonChart />
              </div>
            </SectionLoading>
          ) : null}
          {summaryState === "error" ? (
            <ErrorState
              title="Dashboard unavailable"
              description={error ?? undefined}
              onRetry={() => void fetchDashboard(projectId)}
            />
          ) : null}

          {summaryState === "ready" && summary && !summary.hasLearningEvidence ? (
            <EmptyState
              title="No learning evidence yet."
              description="Upload your materials and complete an assessment to establish your learning baseline."
            />
          ) : null}

          {summaryState === "ready" && summary ? (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <StatCard
                  label="Overall Mastery"
                  value={
                    summary.overallMastery != null
                      ? `${Math.round(summary.overallMastery * 100)}%`
                      : "—"
                  }
                  href="../growth"
                  sub={
                    summary.masteryConfidence != null
                      ? `Confidence ${Math.round(summary.masteryConfidence * 100)}%`
                      : undefined
                  }
                />
                <StatCard
                  label="Growth"
                  value={
                    summary.growthStatus === "IMPROVING"
                      ? "Improving"
                      : summary.growthStatus === "REQUIRING_ATTENTION"
                        ? "Needs attention"
                        : summary.growthStatus === "STABLE"
                          ? "Stable"
                          : "—"
                  }
                  href="../growth"
                />
                <StatCard
                  label="Active Recommendations"
                  value={String(summary.activeRecommendations)}
                  href="../overview"
                />
                <StatCard
                  label="Assessments"
                  value={String(summary.assessmentCount)}
                  href="../quiz"
                  sub={`${summary.questionsAnswered} questions answered`}
                />
                <StatCard
                  label="Learning Activity"
                  value={String(summary.tutorMessages)}
                  href="../tutor"
                  sub={`${summary.tutorConversations} conversations`}
                />
                <StatCard
                  label="Materials"
                  value={String(summary.materialsCount)}
                  href="../materials"
                  sub={`${summary.materialsReady} ready`}
                />
                <StatCard
                  label="Concepts"
                  value={String(summary.conceptsCount)}
                  href="../overview"
                />
                <StatCard
                  label="Content"
                  value={`${summary.chunksCount} chunks`}
                  href="../materials"
                  sub={`${summary.imagesCount} images · ${summary.pagesCount} pages`}
                />
              </div>

              {activityState === "error" ? (
                <ErrorState
                  title="Activity unavailable"
                  description={error ?? undefined}
                  onRetry={() => void fetchDashboard(projectId)}
                />
              ) : null}

              {trendsState === "loading" ? (
                <SectionLoading label="Loading trends">
                  <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    <SkeletonChart />
                    <SkeletonChart />
                  </div>
                </SectionLoading>
              ) : null}
              {trendsState === "ready" ? (
                <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
                      <BarChart3 className="h-4 w-4 text-primary" aria-hidden="true" />
                      Learning activity
                    </p>
                    {activityByDay.length === 0 || activityByDay.every((d) => d.count === 0) ? (
                      <p className="text-sm text-muted-foreground">
                        No activity in this range yet.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <BarChart
                          width={520}
                          height={180}
                          data={activityByDay.map((d) => ({
                            date: d.date.slice(5),
                            count: d.count,
                          }))}
                          aria-label="Daily learning activity"
                        >
                          <CartesianGrid
                            stroke={CHART_GRID}
                            strokeDasharray="3 3"
                            vertical={false}
                          />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 11, fill: CHART_TICK }}
                            tickLine={false}
                            axisLine={{ stroke: CHART_GRID }}
                          />
                          <YAxis
                            allowDecimals={false}
                            tick={{ fontSize: 11, fill: CHART_TICK }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip
                            contentStyle={{
                              borderRadius: 8,
                              borderColor: CHART_GRID,
                              fontSize: 12,
                            }}
                          />
                          <Bar
                            dataKey="count"
                            name="Events"
                            fill={CHART_BLUE}
                            radius={[3, 3, 0, 0]}
                            maxBarSize={22}
                          />
                        </BarChart>
                      </div>
                    )}
                  </div>
                  <div>
                    <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
                      <TrendingUp className="h-4 w-4 text-primary" aria-hidden="true" />
                      Mastery trend
                    </p>
                    {masteryTrend.length < 2 ? (
                      <p className="text-sm text-muted-foreground">
                        Complete more assessments to see your mastery trend.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <LineChart
                          width={520}
                          height={180}
                          data={masteryTrend.map((p) => ({
                            date: new Date(p.date).toLocaleDateString(),
                            score: Math.round(p.score * 100),
                          }))}
                          aria-label="Assessment scores over time"
                        >
                          <CartesianGrid
                            stroke={CHART_GRID}
                            strokeDasharray="3 3"
                            vertical={false}
                          />
                          <XAxis
                            dataKey="date"
                            tick={{ fontSize: 11, fill: CHART_TICK }}
                            tickLine={false}
                            axisLine={{ stroke: CHART_GRID }}
                          />
                          <YAxis
                            domain={[0, 100]}
                            tick={{ fontSize: 11, fill: CHART_TICK }}
                            tickLine={false}
                            axisLine={false}
                          />
                          <Tooltip
                            contentStyle={{
                              borderRadius: 8,
                              borderColor: CHART_GRID,
                              fontSize: 12,
                            }}
                          />
                          <Line
                            type="monotone"
                            dataKey="score"
                            name="Score %"
                            dot={false}
                            stroke={CHART_BLUE}
                            strokeWidth={2}
                          />
                        </LineChart>
                      </div>
                    )}
                  </div>
                </div>
              ) : null}
              {trendsState === "error" ? (
                <ErrorState
                  title="Trends unavailable"
                  description={error ?? undefined}
                  onRetry={() => void fetchDashboard(projectId)}
                />
              ) : null}

              <div>
                <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
                  <History className="h-4 w-4 text-primary" aria-hidden="true" />
                  Recent activity
                </p>
                {activityState === "ready" && activity.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No activity in this range yet.</p>
                ) : (
                  <ul className="space-y-1">
                    {activity.map((item) => (
                      <li key={item.id} className="flex items-baseline gap-2 text-sm">
                        <span className="shrink-0 text-xs text-muted-foreground">
                          {new Date(item.createdAt).toLocaleDateString()}
                        </span>
                        <span>{item.summary}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </>
          ) : null}

          {summary?.lastActivityAt ? (
            <p className="font-mono-tech flex items-center gap-1.5 text-[11px] uppercase tracking-[0.08em] text-muted-foreground">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              Last activity {new Date(summary.lastActivityAt).toLocaleString()}
            </p>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
