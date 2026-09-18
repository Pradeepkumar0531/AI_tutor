import * as React from "react";
import { Check, CheckCircle2, Flag, Tag, XCircle } from "lucide-react";

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
  projectId,
  attemptId,
  question,
  busy,
}: {
  projectId: string;
  attemptId: string;
  question: AttemptQuestion;
  busy: boolean;
}) {
  const answerQuestion = useAssessmentStore((s) => s.answerQuestion);
  const [selected, setSelected] = React.useState("");
  const [text, setText] = React.useState("");
  const answered = question.answer.submitted != null;

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (busy || answered) return;
    const value = question.type === "MCQ" ? selected : text.trim();
    if (!value) return;
    void answerQuestion(projectId, attemptId, question.questionId, value);
    setSelected("");
    setText("");
  };

  return (
    <div className="rounded-[10px] border bg-card p-4">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[15px] font-medium leading-relaxed">
          Q{question.position + 1}. {question.prompt}
        </p>
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
        <form onSubmit={submit} className="mt-2 space-y-2">
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
                    selected === o.id
                      ? "border-primary bg-[hsl(var(--primary)/0.06)]"
                      : "hover:border-primary/40 hover:bg-secondary/50",
                  )}
                >
                  <input
                    type="radio"
                    name={`q-${question.questionId}`}
                    value={o.id}
                    checked={selected === o.id}
                    onChange={() => setSelected(o.id)}
                    disabled={busy}
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
              value={text}
              onChange={(e) => setText(e.target.value)}
              aria-label={`Answer for question ${question.position + 1}`}
              rows={4}
              className="w-full rounded-md border px-2 py-1 text-sm"
              placeholder="Write your answer…"
              disabled={busy}
            />
          )}
          <Button
            type="submit"
            size="sm"
            disabled={busy || (question.type === "MCQ" ? !selected : !text.trim())}
          >
            <Check className="h-4 w-4" aria-hidden="true" />
            {busy ? "Submitting…" : "Submit answer"}
          </Button>
        </form>
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
  const completeAttempt = useAssessmentStore((s) => s.completeAttempt);
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
  const busy = busyState === "working";

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
          projectId={projectId}
          attemptId={attempt.id}
          question={q}
          busy={busy}
        />
      ))}
      {busyState === "error" ? (
        <ErrorState title="Request failed" description={error ?? undefined} />
      ) : null}
      <Button
        type="button"
        disabled={busy || attempt.status !== "IN_PROGRESS"}
        onClick={() => {
          setFinishing(true);
          void completeAttempt(projectId, attempt.id);
        }}
      >
        <Flag className="h-4 w-4" aria-hidden="true" />
        {busy ? "Working…" : "Finish and see results"}
      </Button>
      {finishing && busy ? (
        <SectionLoading label="Analyzing your responses">
          <SkeletonProgress label="Analyzing your responses…" />
        </SectionLoading>
      ) : null}
    </div>
  );
}
