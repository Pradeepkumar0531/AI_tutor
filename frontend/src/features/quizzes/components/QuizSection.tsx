import { ArrowLeft, ClipboardList, History, List, Play, Sparkles, X } from "lucide-react";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState } from "@/components/ui/states";
import {
  SectionLabel,
  SectionLoading,
  SkeletonList,
  SkeletonProgress,
  SkeletonQuizQuestion,
} from "@/components/ui";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useMasteryStore } from "@/stores/useMasteryStore";
import { AssessmentResultView } from "./AssessmentResultView";
import { AttemptView } from "./AttemptView";

function CreateQuizForm({ projectId }: { projectId: string }) {
  const busyState = useAssessmentStore((s) => s.busyState);
  const createQuiz = useAssessmentStore((s) => s.createQuiz);
  const [count, setCount] = React.useState("5");
  const [difficulty, setDifficulty] = React.useState("");
  const [mcq, setMcq] = React.useState(true);
  const [openEnded, setOpenEnded] = React.useState(true);
  const working = busyState === "working";

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (working) return;
    void createQuiz(projectId, {
      questionCount: Number(count),
      difficulty: difficulty || null,
      mcq,
      openEnded,
    });
  };

  return (
    <form onSubmit={submit} className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <label className="text-sm font-medium">
        Questions
        <Input
          type="number"
          min={1}
          max={20}
          value={count}
          onChange={(e) => setCount(e.target.value)}
          aria-label="Number of questions"
          className="mt-1.5 w-full"
          disabled={working}
        />
      </label>
      <label className="text-sm font-medium">
        Difficulty
        <select
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value)}
          aria-label="Target difficulty"
          disabled={working}
          className="mt-1.5 w-full rounded-md border bg-background px-2 py-2 text-sm"
        >
          <option value="">Adaptive</option>
          <option value="EASY">Easy</option>
          <option value="MEDIUM">Medium</option>
          <option value="HARD">Hard</option>
        </select>
      </label>
      <div className="flex items-end gap-4 pb-2">
        <label className="flex cursor-pointer items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={mcq}
            onChange={(e) => setMcq(e.target.checked)}
            disabled={working}
            className="h-4 w-4 accent-primary"
          />
          Multiple choice
        </label>
        <label className="flex cursor-pointer items-center gap-1.5 text-sm">
          <input
            type="checkbox"
            checked={openEnded}
            onChange={(e) => setOpenEnded(e.target.checked)}
            disabled={working}
            className="h-4 w-4 accent-primary"
          />
          Open-ended
        </label>
      </div>
      <div className="col-span-2 flex items-end sm:col-span-3 lg:col-span-1">
        <Button type="submit" disabled={working} className="w-full">
          <Sparkles className="h-4 w-4" aria-hidden="true" />
          {working ? "Generating…" : "Generate quiz"}
        </Button>
      </div>
    </form>
  );
}

export function QuizSection({ projectId }: { projectId: string }) {
  const quizzes = useAssessmentStore((s) => s.quizzes);
  const quizzesState = useAssessmentStore((s) => s.quizzesState);
  const summaries = useAssessmentStore((s) => s.summaries);
  const activeQuiz = useAssessmentStore((s) => s.activeQuiz);
  const activeAttempt = useAssessmentStore((s) => s.activeAttempt);
  const result = useAssessmentStore((s) => s.result);
  const error = useAssessmentStore((s) => s.error);
  const fetchQuizzes = useAssessmentStore((s) => s.fetchQuizzes);
  const selectQuiz = useAssessmentStore((s) => s.selectQuiz);
  const startAttempt = useAssessmentStore((s) => s.startAttempt);
  const openAssessment = useAssessmentStore((s) => s.openAssessment);
  const backToList = useAssessmentStore((s) => s.backToList);
  const generating = useAssessmentStore(
    (s) =>
      s.busyState === "working" &&
      s.activeAttempt === null &&
      s.activeQuiz === null &&
      s.result === null,
  );
  const masteryItems = useMasteryStore((s) => s.items);

  const focusConcepts = React.useMemo(
    () => [...masteryItems].sort((a, b) => a.masteryScore - b.masteryScore).slice(0, 3),
    [masteryItems],
  );

  React.useEffect(() => {
    void fetchQuizzes(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  if (result) {
    return (
      <section aria-labelledby="quiz-heading">
        <SectionLabel id="quiz-heading">Quiz</SectionLabel>
        <Card className="mt-2">
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2">
                <ClipboardList className="h-5 w-5 text-primary" aria-hidden="true" />
                Assessment result
              </CardTitle>
              <Button type="button" variant="outline" size="sm" onClick={backToList}>
                <ArrowLeft className="h-4 w-4" aria-hidden="true" />
                Back to quizzes
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <AssessmentResultView result={result} />
          </CardContent>
        </Card>
      </section>
    );
  }

  if (activeAttempt) {
    return (
      <section aria-labelledby="quiz-heading">
        <SectionLabel id="quiz-heading">Quiz</SectionLabel>
        <Card className="mt-2">
          <CardHeader>
            <div className="flex items-center justify-between gap-2">
              <CardTitle className="flex items-center gap-2">
                <ClipboardList className="h-5 w-5 text-primary" aria-hidden="true" />
                Taking quiz
              </CardTitle>
              <Button type="button" variant="outline" size="sm" onClick={backToList}>
                <X className="h-4 w-4" aria-hidden="true" />
                Leave attempt
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <AttemptView projectId={projectId} />
          </CardContent>
        </Card>
      </section>
    );
  }

  return (
    <section aria-labelledby="quiz-heading">
      <SectionLabel id="quiz-heading">Quiz</SectionLabel>

      {/* Hero: what this tab does + current focus */}
      <div className="card-hero mt-2 rounded-[10px] border p-5">
        <h3 className="text-xl font-semibold tracking-tight">Adaptive Assessment</h3>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Quizzes are generated from this project&apos;s concepts and adapt to what needs work.
          Every question cites its source material.
        </p>
        {focusConcepts.length > 0 ? (
          <div className="mt-3">
            <p className="eyebrow">This session will focus on</p>
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {focusConcepts.map((c) => (
                <li key={c.conceptId}>
                  <Badge tone="info">
                    {c.conceptName} · {Math.round(c.masteryScore * 100)}%
                  </Badge>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="mt-4 space-y-4">
        {/* Step 1 — create */}
        <Card accent>
          <CardHeader className="pb-3">
            <p className="eyebrow">Step 1 · Create</p>
            <CardTitle className="mt-1 flex min-w-0 items-center gap-2.5 text-[15px]">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <Sparkles className="h-4 w-4" aria-hidden="true" />
              </span>
              New quiz
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {quizzesState === "loading" && quizzes.length === 0 ? (
              <SectionLoading label="Loading quizzes">
                <SkeletonList rows={2} />
              </SectionLoading>
            ) : null}
            {quizzesState === "error" ? (
              <ErrorState
                title="Could not load quizzes"
                description={error ?? undefined}
                onRetry={() => void fetchQuizzes(projectId)}
              />
            ) : null}

            <CreateQuizForm projectId={projectId} />

            {generating ? (
              <SectionLoading label="Generating quiz">
                <SkeletonQuizQuestion />
                <SkeletonProgress
                  label="Generating questions from your concepts…"
                  className="mt-3"
                />
              </SectionLoading>
            ) : null}

            {activeQuiz ? (
              <div className="card-hero rounded-lg border p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium">{activeQuiz.quiz.title}</p>
                  <Badge tone={activeQuiz.quiz.status === "READY" ? "success" : "default"}>
                    {activeQuiz.quiz.status}
                  </Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {activeQuiz.questions.length} questions
                  {activeQuiz.quiz.difficulty ? ` · ${activeQuiz.quiz.difficulty}` : ""}
                </p>
                <Button
                  type="button"
                  className="mt-3"
                  onClick={() => void startAttempt(projectId, activeQuiz.quiz.id)}
                >
                  <Play className="h-4 w-4" aria-hidden="true" />
                  Start attempt
                </Button>
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Step 2 — pick a quiz */}
        <Card>
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between gap-2">
              <div>
                <p className="eyebrow">Step 2 · Review</p>
                <CardTitle className="mt-1 flex min-w-0 items-center gap-2.5 text-[15px]">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                    <ClipboardList className="h-4 w-4" aria-hidden="true" />
                  </span>
                  Quizzes
                </CardTitle>
              </div>
              {activeQuiz ? (
                <Button type="button" variant="outline" size="sm" onClick={backToList}>
                  <List className="h-4 w-4" aria-hidden="true" />
                  All quizzes
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {activeQuiz || generating ? null : quizzesState === "ready" && quizzes.length === 0 ? (
              <EmptyState
                title="No quizzes yet."
                description="Generate a quiz grounded in this project's concepts. Questions cite their source material."
                icon={ClipboardList}
              />
            ) : (
              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {quizzes.map((q, i) => (
                  <li
                    key={q.id}
                    className="rounded-lg border bg-card p-3 transition-colors hover:border-primary/40"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        type="button"
                        className="text-left font-medium underline-offset-4 hover:text-primary hover:underline"
                        onClick={() => void selectQuiz(projectId, q.id)}
                      >
                        <span className="font-mono-tech mr-1.5 text-xs text-muted-foreground">
                          {String(i + 1).padStart(2, "0")}
                        </span>
                        {q.title}
                      </button>
                      <Badge tone={q.status === "READY" ? "success" : "default"}>{q.status}</Badge>
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {q.questionCount} questions{q.difficulty ? ` · ${q.difficulty}` : ""}
                    </p>
                  </li>
                ))}
              </ul>
            )}

            {summaries.length > 0 ? (
              <div className="border-t pt-4">
                <p className="eyebrow">Step 3 · History</p>
                <p className="mb-2 mt-1 flex items-center gap-1.5 text-sm font-medium">
                  <History className="h-4 w-4 text-primary" aria-hidden="true" />
                  Past results
                </p>
                <ul className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  {summaries.map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        className="w-full rounded-lg border px-3 py-2 text-left text-sm transition-colors hover:border-primary/40 hover:bg-secondary/50"
                        onClick={() => void openAssessment(projectId, s.id)}
                      >
                        <span className="font-semibold">
                          {s.score != null ? `${Math.round(s.score)}%` : "In progress"}
                        </span>
                        {s.completedAt ? (
                          <span className="text-muted-foreground">
                            {" "}
                            · {new Date(s.completedAt).toLocaleDateString()}
                          </span>
                        ) : (
                          ""
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
