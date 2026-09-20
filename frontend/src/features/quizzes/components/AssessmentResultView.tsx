import * as React from "react";
import { CheckCircle2, ChevronDown, Eye, Target, Trophy, XCircle } from "lucide-react";

import { assessmentApi } from "@/api/assessment";
import { toApiError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/states";
import { SectionLoading, SkeletonText } from "@/components/ui";
import type { AssessmentResult, AttemptQuestion } from "@/types";

function outcomeLine(index: number, q: AttemptQuestion): { ok: boolean | null; text: string } {
  const label = `Q${index + 1}`;
  if (q.answer.submitted == null || q.answer.submitted === "") {
    return { ok: null, text: `${label} — Not answered.` };
  }
  const feedback = (q.answer.feedback ?? "").trim();
  if (q.answer.isCorrect == null) {
    return { ok: null, text: feedback ? `${label} — ${feedback}` : `${label} — Answered.` };
  }
  const verdict = q.answer.isCorrect ? "Correct" : "Incorrect";
  return {
    ok: q.answer.isCorrect,
    text: feedback ? `${label} — ${feedback}` : `${label} — ${verdict}.`,
  };
}

function ReviewCard({ question, index }: { question: AttemptQuestion; index: number }) {
  const mine = question.answer.submitted?.trim();
  return (
    <li className="rounded-lg border bg-card p-3 text-sm">
      <p className="font-medium">
        Q{index + 1}. {question.prompt}
      </p>
      <p className="mt-1.5 text-muted-foreground">
        Your answer: <span className="font-medium text-foreground">{mine ? mine : "—"}</span>
      </p>
      {question.type === "MCQ" && question.answer.correctOptionId ? (
        <p className="mt-0.5 text-muted-foreground">
          Correct answer:{" "}
          <span className="font-medium text-foreground">{question.answer.correctOptionId}</span>
          {mine ? ` · you chose ${mine}` : ""}
        </p>
      ) : null}
      {question.answer.feedback ? <p className="mt-1.5">{question.answer.feedback}</p> : null}
    </li>
  );
}

export function AssessmentResultView({
  result,
  projectId,
  onBack,
}: {
  result: AssessmentResult;
  projectId: string;
  onBack: () => void;
}) {
  const [reviewOpen, setReviewOpen] = React.useState(false);
  const [questions, setQuestions] = React.useState<AttemptQuestion[] | null>(null);
  const [loadError, setLoadError] = React.useState<string | null>(null);
  const score = Math.round(result.score);
  // Unmount-safe loader: "Back to quizzes" (or a route change) can unmount
  // this view while the attempt re-read is in flight — late settles must not
  // touch state after unmount.
  const aliveRef = React.useRef(true);
  React.useEffect(() => {
    aliveRef.current = true;
    return () => {
      aliveRef.current = false;
    };
  }, []);
  const loadQuestions = React.useCallback(() => {
    setLoadError(null);
    setQuestions(null);
    assessmentApi
      .attempt(projectId, result.quizAttemptId)
      .then((detail) => {
        if (aliveRef.current) setQuestions(detail.questions);
      })
      .catch((e) => {
        if (aliveRef.current) setLoadError(toApiError(e).message);
      });
  }, [projectId, result.quizAttemptId]);

  // Per-question outcomes come from the persisted attempt (real answers +
  // server feedback), fetched once for this result.
  React.useEffect(() => {
    loadQuestions();
  }, [loadQuestions]);

  return (
    <div className="space-y-4">
      {/* Hero score panel */}
      <div className="card-dark rounded-[10px] border p-5">
        <div className="flex flex-wrap items-center gap-4">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-white/15 text-primary-foreground">
            <Trophy className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="eyebrow">Quiz complete</p>
            <p className="text-4xl font-bold tracking-tight">{score}%</p>
            <p className="mt-0.5 text-sm text-primary-foreground/75">
              {result.correctCount} of {result.totalQuestions} correct
            </p>
          </div>
          <dl className="ml-auto grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            <div>
              <dt className="text-xs text-primary-foreground/65">Correct</dt>
              <dd className="inline-flex items-center gap-1 font-semibold">
                <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                {result.correctCount}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-primary-foreground/65">Incorrect</dt>
              <dd className="inline-flex items-center gap-1 font-semibold">
                <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
                {result.incorrectCount}
              </dd>
            </div>
          </dl>
        </div>
      </div>

      {/* One concise line per question */}
      <Card variant="light">
        <CardContent className="space-y-2 pt-4">
          {questions === null && loadError === null ? (
            <SectionLoading label="Loading per-question results">
              <SkeletonText lines={3} />
            </SectionLoading>
          ) : null}
          {loadError !== null ? (
            <p className="text-sm text-muted-foreground">
              Could not load per-question results: {loadError}{" "}
              <button
                type="button"
                onClick={loadQuestions}
                className="font-medium text-primary underline-offset-2 hover:underline"
              >
                Retry
              </button>
            </p>
          ) : null}
          {questions !== null && questions.length > 0 ? (
            <ul className="space-y-1.5">
              {questions.map((q, i) => {
                const line = outcomeLine(i, q);
                return (
                  <li
                    key={q.questionId}
                    className="flex items-start gap-2 rounded-lg border bg-secondary/40 px-2.5 py-2 text-sm leading-relaxed"
                  >
                    {line.ok == null ? null : line.ok ? (
                      <CheckCircle2
                        className="mt-0.5 h-4 w-4 shrink-0 text-primary"
                        aria-hidden="true"
                      />
                    ) : (
                      <XCircle
                        className="mt-0.5 h-4 w-4 shrink-0 text-destructive"
                        aria-hidden="true"
                      />
                    )}
                    <span className="line-clamp-2">{line.text}</span>
                  </li>
                );
              })}
            </ul>
          ) : questions !== null ? (
            <EmptyState title="No questions recorded for this attempt." />
          ) : null}
          <div className="flex flex-wrap gap-2 pt-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={questions === null}
              onClick={() => setReviewOpen((v) => !v)}
              aria-expanded={reviewOpen}
            >
              <Eye className="h-4 w-4" aria-hidden="true" />
              {reviewOpen ? "Hide review" : "Review answers"}
              <ChevronDown
                className={`h-3.5 w-3.5 transition-transform ${reviewOpen ? "rotate-180" : ""}`}
                aria-hidden="true"
              />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={onBack}>
              Back to quizzes
            </Button>
          </div>
          {reviewOpen && questions !== null && questions.length > 0 ? (
            <ul className="space-y-2 pt-1">
              {questions.map((q, i) => (
                <ReviewCard key={q.questionId} question={q} index={i} />
              ))}
            </ul>
          ) : null}
        </CardContent>
      </Card>

      {result.conceptResults.length > 0 ? (
        <Card variant="light" accent>
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
