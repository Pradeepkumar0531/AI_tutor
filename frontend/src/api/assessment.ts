import { apiClient } from "./client";
import type {
  AnswerState,
  AssessmentResult,
  AssessmentSummary,
  Attempt,
  AttemptQuestion,
  Quiz,
  QuizQuestion,
} from "@/types";

interface BackendQuiz {
  id: string;
  project_id: string;
  title: string;
  status: Quiz["status"];
  difficulty: string | null;
  question_count: number;
  created_at: string;
}

interface BackendQuestion {
  question_id: string;
  type: QuizQuestion["type"];
  prompt: string;
  options: { id: string; text: string }[];
  position: number;
  points: number;
  difficulty: string | null;
  concepts: { id: string; name: string }[];
  sources: { material_name: string; page_start: number | null; page_end: number | null }[];
}

interface BackendAnswer {
  submitted: string | null;
  is_correct: boolean | null;
  score: number | null;
  feedback: string | null;
  correct_option_id: string | null;
  evaluation: Record<string, unknown> | null;
}

interface BackendAttempt {
  id: string;
  quiz_id: string;
  status: Attempt["status"];
  score: number | null;
  max_score: number | null;
  started_at: string;
  completed_at: string | null;
}

interface BackendResult {
  assessment_id: string;
  quiz_attempt_id: string;
  quiz_id: string;
  total_questions: number;
  answered_count: number;
  correct_count: number;
  partial_count: number;
  incorrect_count: number;
  score: number;
  concept_results: BackendConceptResult[];
}

function toQuiz(q: BackendQuiz): Quiz {
  return {
    id: q.id,
    projectId: q.project_id,
    title: q.title,
    status: q.status,
    difficulty: q.difficulty,
    questionCount: q.question_count,
    createdAt: q.created_at,
  };
}

function toAnswer(a: BackendAnswer): AnswerState {
  return {
    submitted: a.submitted,
    isCorrect: a.is_correct,
    score: a.score,
    feedback: a.feedback,
    correctOptionId: a.correct_option_id,
    evaluation: a.evaluation,
  };
}

function toAttemptQuestion(q: BackendQuestion & { answer?: BackendAnswer }): AttemptQuestion {
  return {
    questionId: q.question_id,
    type: q.type,
    prompt: q.prompt,
    options: q.options ?? [],
    position: q.position,
    points: q.points ?? 1,
    difficulty: q.difficulty,
    concepts: q.concepts ?? [],
    sources: q.sources ?? [],
    answer: q.answer
      ? toAnswer(q.answer)
      : {
          submitted: null,
          isCorrect: null,
          score: null,
          feedback: null,
          correctOptionId: null,
          evaluation: null,
        },
  };
}

function toAttempt(a: BackendAttempt): Attempt {
  return {
    id: a.id,
    quizId: a.quiz_id,
    status: a.status,
    score: a.score,
    maxScore: a.max_score,
    startedAt: a.started_at,
    completedAt: a.completed_at,
  };
}

interface BackendConceptResult {
  concept_id: string;
  concept_name: string;
  questions_seen: number;
  correct_count: number;
  partial_count: number;
  incorrect_count: number;
  normalized_score: number;
  recent: string[];
}

function toQuizQuestion(q: BackendQuestion): QuizQuestion {
  return {
    questionId: q.question_id,
    type: q.type,
    prompt: q.prompt,
    options: q.options ?? [],
    position: q.position,
    points: q.points ?? 1,
    difficulty: q.difficulty,
    concepts: q.concepts ?? [],
    sources: q.sources ?? [],
  };
}

function toResult(
  r: Omit<BackendResult, "concept_results"> & { concept_results: BackendConceptResult[] },
): AssessmentResult {
  return {
    assessmentId: r.assessment_id,
    quizAttemptId: r.quiz_attempt_id,
    quizId: r.quiz_id,
    totalQuestions: r.total_questions,
    answeredCount: r.answered_count,
    correctCount: r.correct_count,
    partialCount: r.partial_count,
    incorrectCount: r.incorrect_count,
    score: r.score,
    conceptResults: (r.concept_results ?? []).map((c) => ({
      conceptId: c.concept_id,
      conceptName: c.concept_name,
      questionsSeen: c.questions_seen,
      correctCount: c.correct_count,
      partialCount: c.partial_count,
      incorrectCount: c.incorrect_count,
      normalizedScore: c.normalized_score,
      recent: c.recent ?? [],
    })),
  };
}

export interface CreateQuizInput {
  questionCount: number;
  difficulty?: string | null;
  questionTypes: ("MCQ" | "OPEN_ENDED")[];
  title?: string;
  clientRequestKey: string;
  focusConceptIds?: string[];
}

export const assessmentApi = {
  async quizzes(projectId: string): Promise<Quiz[]> {
    const res = await apiClient.get<BackendQuiz[]>(`/api/v1/projects/${projectId}/quizzes`);
    return res.data.map(toQuiz);
  },

  async createQuiz(
    projectId: string,
    input: CreateQuizInput,
  ): Promise<{ quiz: Quiz; questions: QuizQuestion[] }> {
    // Grounded generation fans out to one retrieval + model call per
    // (concept, type) group — measured ~16s live for 5 questions — so this
    // one route gets its own bounded timeout instead of the shared 15s
    // client default. Aborts would otherwise fake a failure AFTER the server
    // already persisted the quiz, and retries would duplicate it.
    // `client_request_key` is snake_case: the backend schema silently drops
    // unknown fields, so the camelCase spelling previously disabled
    // idempotent replays entirely.
    const res = await apiClient.post<{
      quiz: BackendQuiz;
      questions: BackendQuestion[];
    }>(
      `/api/v1/projects/${projectId}/quizzes`,
      {
        question_count: input.questionCount,
        difficulty: input.difficulty ?? null,
        focus_concepts: input.focusConceptIds ?? [],
        question_types: input.questionTypes,
        title: input.title ?? null,
        client_request_key: input.clientRequestKey,
      },
      { timeout: 120000 },
    );
    return { quiz: toQuiz(res.data.quiz), questions: res.data.questions.map(toQuizQuestion) };
  },

  async quiz(projectId: string, quizId: string) {
    const res = await apiClient.get<{
      quiz: BackendQuiz;
      questions: BackendQuestion[];
    }>(`/api/v1/projects/${projectId}/quizzes/${quizId}`);
    return { quiz: toQuiz(res.data.quiz), questions: res.data.questions.map(toQuizQuestion) };
  },

  async startAttempt(
    projectId: string,
    quizId: string,
  ): Promise<{ attempt: Attempt; questions: AttemptQuestion[] }> {
    const res = await apiClient.post<{
      attempt: BackendAttempt;
      questions: (BackendQuestion & { answer: BackendAnswer })[];
    }>(`/api/v1/projects/${projectId}/quizzes/${quizId}/attempts`);
    return {
      attempt: toAttempt(res.data.attempt),
      questions: res.data.questions.map(toAttemptQuestion),
    };
  },

  async attempt(projectId: string, attemptId: string) {
    const res = await apiClient.get<{
      attempt: BackendAttempt;
      questions: (BackendQuestion & { answer: BackendAnswer })[];
    }>(`/api/v1/projects/${projectId}/attempts/${attemptId}`);
    return {
      attempt: toAttempt(res.data.attempt),
      questions: res.data.questions.map(toAttemptQuestion),
    };
  },

  async answer(
    projectId: string,
    attemptId: string,
    questionId: string,
    answer: string,
  ): Promise<{
    isCorrect: boolean | null;
    score: number | null;
    feedback: string;
    correctOptionId: string | null;
    evaluation: Record<string, unknown> | null;
  }> {
    // Answering fans out to an AI evaluator for open-ended responses — the
    // same measured-slow model path as quiz generation — so this route gets
    // the same bounded timeout instead of the shared 15s client default.
    // Aborting early would fake a failure AFTER the server already persisted
    // the evaluation, leaving the attempt looking stuck in "request timeout".
    const res = await apiClient.post<{
      is_correct: boolean | null;
      score: number | null;
      feedback: string;
      correct_option_id: string | null;
      evaluation: Record<string, unknown> | null;
    }>(
      `/api/v1/projects/${projectId}/attempts/${attemptId}/answers`,
      {
        question_id: questionId,
        answer,
      },
      { timeout: 120000 },
    );
    return {
      isCorrect: res.data.is_correct,
      score: res.data.score,
      feedback: res.data.feedback,
      correctOptionId: res.data.correct_option_id,
      evaluation: res.data.evaluation,
    };
  },

  async complete(projectId: string, attemptId: string): Promise<AssessmentResult> {
    // Completion evaluates any pending open-ended answers server-side
    // (model calls) before finalizing — same bounded timeout as answering so
    // a slow evaluation surfaces honest progress instead of a fake timeout.
    const res = await apiClient.post<BackendResult>(
      `/api/v1/projects/${projectId}/attempts/${attemptId}/complete`,
      undefined,
      { timeout: 120000 },
    );
    return toResult(res.data);
  },

  async assessments(projectId: string): Promise<AssessmentSummary[]> {
    const res = await apiClient.get<AssessmentSummary[]>(
      `/api/v1/projects/${projectId}/assessments`,
    );
    return res.data;
  },

  async assessment(projectId: string, assessmentId: string): Promise<AssessmentResult> {
    const res = await apiClient.get<BackendResult>(
      `/api/v1/projects/${projectId}/assessments/${assessmentId}`,
    );
    return toResult(res.data);
  },
};
