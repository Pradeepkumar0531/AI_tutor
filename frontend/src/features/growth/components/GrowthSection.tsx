import * as React from "react";
import { Info, TrendingDown, TrendingUp } from "lucide-react";
import { CartesianGrid, Line, LineChart, Tooltip, XAxis, YAxis } from "recharts";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  SectionLabel,
  SectionLoading,
  SkeletonChart,
  SkeletonConceptRows,
  SkeletonStat,
  SlowHint,
} from "@/components/ui";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { useSlowHint } from "@/hooks/useSlowHint";
import { useGrowthStore } from "@/stores/useGrowthStore";
import type { GrowthStatus } from "@/api/growth";

function statusLabel(status: GrowthStatus): string {
  if (status === "IMPROVING") return "Improving";
  if (status === "REQUIRING_ATTENTION") return "Requiring Attention";
  return "Stable";
}

function GrowthChart() {
  const history = useGrowthStore((s) => s.history);
  const historyState = useGrowthStore((s) => s.historyState);

  if (historyState === "loading")
    return (
      <SectionLoading label="Loading growth history">
        <SkeletonChart />
      </SectionLoading>
    );
  if (history.length < 2) {
    return (
      <p className="text-sm text-muted-foreground">
        Complete more assessments to see your growth over time.
      </p>
    );
  }
  const data = history.map((p) => ({
    date: new Date(p.date).toLocaleDateString(),
    mastery: Math.round(p.score * 100),
  }));
  return (
    <div className="overflow-x-auto">
      <LineChart
        width={520}
        height={180}
        data={data}
        aria-label="Overall mastery over time"
        margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
      >
        <CartesianGrid stroke="#DDE3EA" strokeDasharray="3 3" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#667085" }}
          tickLine={false}
          axisLine={{ stroke: "#DDE3EA" }}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fontSize: 11, fill: "#667085" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip contentStyle={{ borderRadius: 8, borderColor: "#DDE3EA", fontSize: 12 }} />
        <Line
          type="monotone"
          dataKey="mastery"
          name="Overall mastery %"
          dot={false}
          stroke="#123B6D"
          strokeWidth={2}
        />
      </LineChart>
    </div>
  );
}

export function GrowthSection({ projectId }: { projectId: string }) {
  const growth = useGrowthStore((s) => s.growth);
  const growthState = useGrowthStore((s) => s.growthState);
  const error = useGrowthStore((s) => s.error);
  const fetchGrowth = useGrowthStore((s) => s.fetchGrowth);
  const [sectionRef, visible] = useFirstVisible<HTMLElement>();

  React.useEffect(() => {
    if (visible) void fetchGrowth(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, visible]);

  return (
    <section aria-labelledby="growth-heading" ref={sectionRef}>
      <SectionLabel id="growth-heading">Concept Intelligence</SectionLabel>
      <Card className="mt-2">
        <CardHeader className="pb-3">
          <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
              <TrendingUp className="h-4 w-4" aria-hidden="true" />
            </span>
            Mastery &amp; Growth
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {growthState === "loading" && !growth ? <GrowthSectionSkeleton /> : null}
          {growthState === "error" ? (
            <ErrorState
              title="Could not load growth"
              description={error ?? undefined}
              onRetry={() => void fetchGrowth(projectId)}
            />
          ) : null}
          {growthState === "ready" && growth && !growth.hasEvidence ? (
            <EmptyState
              title="Growth will appear after you complete your first assessment."
              description="Complete an assessment to establish your learning baseline."
            />
          ) : null}
          {growthState === "ready" && growth && growth.hasEvidence ? (
            <>
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <div className="rounded-[10px] border bg-card p-4">
                  <p className="eyebrow">Avg mastery</p>
                  <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                    {Math.round(growth.overallMastery * 100)}%
                  </p>
                  <p className="mt-1.5">
                    <Badge
                      tone={
                        growth.status === "IMPROVING"
                          ? "success"
                          : growth.status === "REQUIRING_ATTENTION"
                            ? "danger"
                            : "default"
                      }
                    >
                      <span className="inline-flex items-center gap-1">
                        {growth.status === "IMPROVING" ? (
                          <TrendingUp className="h-3 w-3" aria-hidden="true" />
                        ) : growth.status === "REQUIRING_ATTENTION" ? (
                          <TrendingDown className="h-3 w-3" aria-hidden="true" />
                        ) : null}
                        {statusLabel(growth.status)}
                      </span>
                    </Badge>
                  </p>
                </div>
                <div className="rounded-[10px] border bg-card p-4">
                  <p className="eyebrow">Improving</p>
                  <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                    {growth.conceptsImproving}
                  </p>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {growth.assessmentCount}{" "}
                    {growth.assessmentCount === 1 ? "assessment" : "assessments"} ·{" "}
                    {growth.questionsAnswered} questions
                  </p>
                </div>
                <div className="rounded-[10px] border bg-card p-4">
                  <p className="eyebrow">Requiring Attention</p>
                  <p className="mt-2 text-[26px] font-semibold leading-none tracking-tight">
                    {growth.conceptsRequiringAttention}
                  </p>
                  <p className="mt-1.5 text-xs text-muted-foreground">
                    {growth.conceptsStable} stable
                  </p>
                </div>
              </div>
              <p className="flex items-start gap-1.5 text-xs leading-relaxed text-muted-foreground">
                <Info className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                Confidence {Math.round(growth.averageConfidence * 100)}% reflects evidence volume
                and reliability — not correctness itself.
              </p>
              <GrowthChart />
            </>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}

function GrowthSectionSkeleton() {
  const slow = useSlowHint(true);
  return (
    <SectionLoading label="Loading growth">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SkeletonStat />
        <SkeletonStat />
        <SkeletonStat />
      </div>
      <SkeletonChart />
      <SkeletonConceptRows rows={2} />
      <SlowHint show={slow}>Still loading growth trends…</SlowHint>
    </SectionLoading>
  );
}
