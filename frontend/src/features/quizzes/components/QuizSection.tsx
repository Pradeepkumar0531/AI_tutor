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
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
      <label className="text-sm">
        Questions
        <Input
          type="number"
          min={1}
          max={20}
          value={count}
          onChange={(e) => setCount(e.target.value)}
          aria-label="Number of questions"
          className="mt-1 w-24"
          disabled={working}
        />
      </label>
      <label className="text-sm">
        Difficulty
        <select
          value={difficulty}
          onChange={(e) => setDifficulty(e.target.value)}
          aria-label="Target difficulty"
          disabled={working}
          className="mt-1 rounded-md border px-2 py-2 text-sm"
        >
          <option value="">Adaptive</option>
          <option value="EASY">Easy</option>
          <option value="MEDIUM">Medium</option>
          <option value="HARD">Hard</option>
        </select>
      </label>
      <label className="flex items-center gap-1 text-sm">
        <input
          type="checkbox"
          checked={mcq}
          onChange={(e) => setMcq(e.target.checked)}
          disabled={working}
        />
        Multiple choice
      </label>
      <label className="flex items-center gap-1 text-sm">
        <input
          type="checkbox"
          checked={openEnded}
          onChange={(e) => setOpenEnded(e.target.checked)}
          disabled={working}
        />
        Open-ended
      </label>
      <Button type="submit" disabled={working}>
        <Sparkles className="h-4 w-4" aria-hidden="true" />
        {working ? "Generating…" : "Generate quiz"}
      </Button>
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
      <div className="mt-2">
        <h3 className="text-xl font-semibold tracking-tight">Adaptive Assessment</h3>
        <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
          Quizzes are generated from this project&apos;s concepts and adapt to what needs work.
          Every question cites its source material.
        </p>
        {focusConcepts.length > 0 ? (
          <div className="mt-3 rounded-[10px] border bg-card p-4">
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
      <Card className="mt-3">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2.5 text-[15px]">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[hsl(var(--primary)/0.08)] text-primary">
                <ClipboardList className="h-4 w-4" aria-hidden="true" />
              </span>
              Quizzes
            </CardTitle>
            {activeQuiz ? (
              <Button type="button" variant="outline" size="sm" onClick={backToList}>
                <List className="h-4 w-4" aria-hidden="true" />
                All quizzes
              </Button>
            ) : null}
          </div>
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
              <SkeletonProgress label="Generating questions from your concepts…" className="mt-3" />
            </SectionLoading>
          ) : null}

          {activeQuiz ? (
            <div className="rounded-lg border p-3">
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
                className="mt-2"
                onClick={() => void startAttempt(projectId, activeQuiz.quiz.id)}
              >
                <Play className="h-4 w-4" aria-hidden="true" />
                Start attempt
              </Button>
            </div>
          ) : quizzesState === "ready" && quizzes.length === 0 ? (
            <EmptyState
              title="No quizzes yet."
              description="Generate a quiz grounded in this project's concepts. Questions cite their source material."
              icon={ClipboardList}
            />
          ) : (
            <ul className="space-y-2">
              {quizzes.map((q) => (
                <li key={q.id} className="rounded-lg border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <button
                      type="button"
                      className="text-left font-medium underline-offset-4 hover:underline"
                      onClick={() => void selectQuiz(projectId, q.id)}
                    >
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
            <div>
              <p className="mb-1 flex items-center gap-1.5 text-sm font-medium">
                <History className="h-4 w-4 text-primary" aria-hidden="true" />
                Past results
              </p>
              <ul className="space-y-1">
                {summaries.map((s) => (
                  <li key={s.id}>
                    <button
                      type="button"
                      className="text-sm underline-offset-4 hover:underline"
                      onClick={() => void openAssessment(projectId, s.id)}
                    >
                      {s.score != null ? `${Math.round(s.score)}%` : "In progress"}
                      {s.completedAt ? ` · ${new Date(s.completedAt).toLocaleDateString()}` : ""}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </section>
  );
}
