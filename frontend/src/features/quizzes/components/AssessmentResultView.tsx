import { CheckCircle2, MinusCircle, Target, Trophy, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { AssessmentResult } from "@/types";

export function AssessmentResultView({ result }: { result: AssessmentResult }) {
  const score = Math.round(result.score);
  return (
    <div className="space-y-4">
      {/* Hero score panel */}
      <div className="card-hero rounded-[10px] border p-5">
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-[0_4px_14px_-4px_hsl(var(--primary)/0.5)]">
            <Trophy className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="eyebrow">Your score</p>
            <p className="text-4xl font-bold tracking-tight">{score}%</p>
          </div>
          <dl className="ml-auto grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs text-muted-foreground">Correct</dt>
              <dd className="inline-flex items-center gap-1 font-semibold">
                <CheckCircle2 className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                {result.correctCount}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Partial</dt>
              <dd className="inline-flex items-center gap-1 font-semibold">
                <MinusCircle className="h-3.5 w-3.5" aria-hidden="true" />
                {result.partialCount}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Incorrect</dt>
              <dd className="inline-flex items-center gap-1 font-semibold">
                <XCircle className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
                {result.incorrectCount}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Answered</dt>
              <dd className="font-semibold">
                {result.answeredCount} of {result.totalQuestions}
              </dd>
            </div>
          </dl>
        </div>
      </div>
      {result.conceptResults.length > 0 ? (
        <Card accent>
          <CardContent className="space-y-2 pt-4">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Target className="h-4 w-4 text-primary" aria-hidden="true" />
              Concept performance
            </p>
            <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {result.conceptResults.map((c) => (
                <li key={c.conceptId} className="rounded-lg border bg-card p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{c.conceptName}</span>
                    <span className="font-mono-tech font-semibold text-primary">
                      {Math.round(c.normalizedScore * 100)}%
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {c.correctCount}c/{c.partialCount}p/{c.incorrectCount}i of {c.questionsSeen}
                  </p>
                  {c.recent.length > 0 ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      Recent: {c.recent.join(" · ")}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
