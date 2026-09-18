import { CheckCircle2, MinusCircle, Target, Trophy, XCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import type { AssessmentResult } from "@/types";

export function AssessmentResultView({ result }: { result: AssessmentResult }) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Trophy className="h-8 w-8 text-primary" aria-hidden="true" />
        <p className="text-3xl font-bold">{Math.round(result.score)}%</p>
        <p className="text-sm text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <CheckCircle2 className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            {result.correctCount} correct
          </span>{" "}
          ·{" "}
          <span className="inline-flex items-center gap-1">
            <MinusCircle className="h-3.5 w-3.5" aria-hidden="true" />
            {result.partialCount} partial
          </span>{" "}
          ·{" "}
          <span className="inline-flex items-center gap-1">
            <XCircle className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
            {result.incorrectCount} incorrect
          </span>{" "}
          · {result.answeredCount} of {result.totalQuestions} answered
        </p>
      </div>
      {result.conceptResults.length > 0 ? (
        <Card>
          <CardContent className="space-y-2 pt-4">
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Target className="h-4 w-4 text-primary" aria-hidden="true" />
              Concept performance
            </p>
            <ul className="space-y-2">
              {result.conceptResults.map((c) => (
                <li key={c.conceptId} className="rounded-lg border p-2 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium">{c.conceptName}</span>
                    <span className="text-muted-foreground">
                      {Math.round(c.normalizedScore * 100)}% · {c.correctCount}c/
                      {c.partialCount}p/{c.incorrectCount}i of {c.questionsSeen}
                    </span>
                  </div>
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
