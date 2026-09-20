import * as React from "react";
import { CheckCircle2, Flag, Tag, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ErrorState } from "@/components/ui/states";
import {
  ProgressBar,
  SectionLoading,
  SkeletonProgress,
  SkeletonQuizQuestion,
} from "@/components/ui";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { cn } from "@/lib/utils";
import type { AttemptQuestion } from "@/types";

function QuestionCard({
  question,
  total,
  draft,
  onDraft,
  disabled,
}: {
  question: AttemptQuestion;
  total: number;
  draft: string;
  onDraft: (value: string) => void;
  disabled: boolean;
}) {
  const answered = question.answer.submitted != null;

  return (
    <div className="card-hero rounded-[10px] border bg-card p-4 sm:p-5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="eyebrow">
            Question {question.position + 1} of {total}
          </p>
          <p className="mt-1 text-[15px] font-medium leading-relaxed">{question.prompt}</p>
        </div>
        {question.answer.isCorrect == null ? null : question.answer.isCorrect ? (
          <Badge tone="success">
            <span className="inline-flex items-center gap-1">
              <CheckCircle2 className="h-3 w-3" aria-hidden="true" />
              Correct
            </span>
          </Badge>
        ) : (
          <Badge tone="danger">
            <span className="inline-flex items-center gap-1">
              <XCircle className="h-3 w-3" aria-hidden="true" />
              Review
            </span>
          </Badge>
        )}
      </div>
      {question.concepts.length > 0 ? (
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          <Tag className="h-3.5 w-3.5" aria-hidden="true" />
          Concepts: {question.concepts.map((c) => c.name).join(", ")}
        </p>
      ) : null}

      {!answered ? (
        <div className="mt-3 space-y-2">
          {question.type === "MCQ" ? (
            <div
              role="radiogroup"
              aria-label={`Options for question ${question.position + 1}`}
              className="space-y-1.5"
            >
              {question.options.map((o) => (
                <label
                  key={o.id}
                  className={cn(
                    "flex cursor-pointer items-start gap-2.5 rounded-lg border px-3 py-2.5 text-sm transition-colors",
                    draft === o.id
                      ? "border-primary bg-[hsl(var(--primary)/0.06)]"
                      : "hover:border-primary/40 hover:bg-secondary/50",
                  )}
                >
                  <input
                    type="radio"
                    name={`q-${question.questionId}`}
                    value={o.id}
                    checked={draft === o.id}
                    onChange={() => onDraft(o.id)}
                    disabled={disabled}
                    className="mt-1 h-4 w-4 shrink-0 accent-primary"
                  />
                  <span>
                    <span className="font-mono-tech font-medium">{o.id}.</span> {o.text}
                  </span>
                </label>
              ))}
            </div>
          ) : (
            <textarea
              value={draft}
              onChange={(e) => onDraft(e.target.value)}
              aria-label={`Answer for question ${question.position + 1}`}
              rows={4}
              className="w-full rounded-md border px-2 py-1 text-sm"
              placeholder="Write your answer…"
              disabled={disabled}
            />
          )}
        </div>
      ) : (
        <div className="mt-2 text-sm">
          {question.type === "MCQ" && question.answer.correctOptionId ? (
            <p>
              Correct answer: <span className="font-medium">{question.answer.correctOptionId}</span>
              {question.answer.submitted ? ` · you chose ${question.answer.submitted}` : ""}
            </p>
          ) : null}
          {question.answer.feedback ? (
            <p className="mt-1 text-muted-foreground">{question.answer.feedback}</p>
          ) : null}
        </div>
      )}
    </div>
  );
}

export function AttemptView({ projectId }: { projectId: string }) {
  const activeAttempt = useAssessmentStore((s) => s.activeAttempt);
  const busyState = useAssessmentStore((s) => s.busyState);
  const error = useAssessmentStore((s) => s.error);
  const answerQuestion = useAssessmentStore((s) => s.answerQuestion);
  const completeAttempt = useAssessmentStore((s) => s.completeAttempt);
  // Local drafts: the quiz is ONE assessment with ONE final submission. The
  // backend still requires per-question answer rows, so the single Submit
  // action below persists each drafted answer through the existing endpoint
  // (in order, stopping on the first failure) and then completes — no
  // duplicate submissions, no state lost on error.
  const [drafts, setDrafts] = React.useState<Record<string, string>>({});
  const [submitting, setSubmitting] = React.useState(false);
  const [submitProgress, setSubmitProgress] = React.useState("");
  const [finishing, setFinishing] = React.useState(false);
  // Completion is a long server operation (evaluate + persist + refresh
  // mastery/growth/recommendations). Track it locally so the UI can show an
  // honest analyzing state; any settle clears it.
  React.useEffect(() => {
    if (busyState !== "working") setFinishing(false);
  }, [busyState]);

  if (!activeAttempt)
    return (
      <SectionLoading label="Loading attempt">
        <SkeletonQuizQuestion />
      </SectionLoading>
    );
  const { attempt, questions } = activeAttempt;
  const answered = questions.filter((q) => q.answer.submitted != null).length;
  const busy = busyState === "working" || submitting;

  async function submitQuiz() {
    if (submitting || busyState === "working" || attempt.status !== "IN_PROGRESS") return;
    const targets = questions.filter(
      (q) => q.answer.submitted == null && (drafts[q.questionId] ?? "").trim(),
    );
    setSubmitting(true);
    try {
      for (let i = 0; i < targets.length; i++) {
        const q = targets[i] as AttemptQuestion;
        setSubmitProgress(`Submitting ${i + 1} of ${targets.length}…`);
        await answerQuestion(
          projectId,
          attempt.id,
          q.questionId,
          (drafts[q.questionId] ?? "").trim(),
        );
        const state = useAssessmentStore.getState();
        if (state.projectId !== projectId) return;
        if (state.busyState === "error") return;
      }
      setFinishing(true);
      await completeAttempt(projectId, attempt.id);
    } finally {
      setSubmitting(false);
      setSubmitProgress("");
    }
  }

  return (
    <div className="mx-auto w-full max-w-3xl space-y-4">
      <ProgressBar
        value={answered}
        max={Math.max(1, questions.length)}
        label={`Answered ${answered} of ${questions.length}`}
      />
      {questions.map((q) => (
        <QuestionCard
          key={q.questionId}
          question={q}
          total={questions.length}
          draft={drafts[q.questionId] ?? ""}
          onDraft={(value) => setDrafts((d) => ({ ...d, [q.questionId]: value }))}
          disabled={busy || attempt.status !== "IN_PROGRESS"}
        />
      ))}
      {busyState === "error" ? (
        <ErrorState title="Request failed" description={error ?? undefined} />
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          disabled={busy || attempt.status !== "IN_PROGRESS"}
          onClick={() => void submitQuiz()}
        >
          <Flag className="h-4 w-4" aria-hidden="true" />
          {submitting && submitProgress ? submitProgress : busy ? "Working…" : "Submit Quiz"}
        </Button>
        <p className="text-xs text-muted-foreground">
          Answer every question above, then submit once to see your results.
        </p>
      </div>
      {finishing && busy ? (
        <SectionLoading label="Analyzing your responses">
          <SkeletonProgress label="Analyzing your responses…" />
        </SectionLoading>
      ) : null}
    </div>
  );
}
