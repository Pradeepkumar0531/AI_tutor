import { create } from "zustand";

import { toApiError } from "@/api/client";
import { assessmentApi } from "@/api/assessment";
import { useAnalyticsStore } from "@/stores/useAnalyticsStore";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useMasteryStore } from "@/stores/useMasteryStore";
import { useRecommendationsStore } from "@/stores/useRecommendationsStore";
import type {
  AssessmentResult,
  AssessmentSummary,
  Attempt,
  AttemptQuestion,
  Quiz,
  QuizQuestion,
} from "@/types";
import type { LoadStatus } from "./useSpacesStore";

export interface CreateQuizForm {
  questionCount: number;
  difficulty: string | null;
  mcq: boolean;
  openEnded: boolean;
}

interface AssessmentState {
  /** Project owning every slice below (same contract as the tutor store:
   * switching projects clears stale slices synchronously; late responses
   * from a previous project are dropped). */
  projectId: string | null;
  quizzes: Quiz[];
  quizzesState: LoadStatus;
  summaries: AssessmentSummary[];
  summariesState: LoadStatus;
  activeQuiz: { quiz: Quiz; questions: QuizQuestion[] } | null;
  activeAttempt: { attempt: Attempt; questions: AttemptQuestion[] } | null;
  detailState: LoadStatus;
  busyState: "idle" | "working" | "error";
  result: AssessmentResult | null;
  error: string | null;
  fetchQuizzes: (projectId: string) => Promise<void>;
  createQuiz: (projectId: string, form: CreateQuizForm) => Promise<void>;
  selectQuiz: (projectId: string, quizId: string) => Promise<void>;
  startAttempt: (projectId: string, quizId: string) => Promise<void>;
  answerQuestion: (
    projectId: string,
    attemptId: string,
    questionId: string,
    answer: string,
  ) => Promise<void>;
  completeAttempt: (projectId: string, attemptId: string) => Promise<void>;
  practiceConcept: (projectId: string, conceptId: string) => Promise<void>;
  openAssessment: (projectId: string, assessmentId: string) => Promise<void>;
  backToList: () => void;
  /** Dismiss a surfaced operation error (generation failures stay visible
   * until acknowledged; the next operation replaces them). */
  clearError: () => void;
  reset: () => void;
}

const initial = {
  projectId: null as string | null,
  quizzes: [] as Quiz[],
  quizzesState: "idle" as LoadStatus,
  summaries: [] as AssessmentSummary[],
  summariesState: "idle" as LoadStatus,
  activeQuiz: null as { quiz: Quiz; questions: QuizQuestion[] } | null,
  activeAttempt: null as { attempt: Attempt; questions: AttemptQuestion[] } | null,
  detailState: "idle" as LoadStatus,
  busyState: "idle" as "idle" | "working" | "error",
  result: null as AssessmentResult | null,
  error: null as string | null,
};

function newRequestKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export const useAssessmentStore = create<AssessmentState>((set, get) => ({
  ...initial,

  fetchQuizzes: async (projectId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ quizzesState: "loading", summariesState: "loading", error: null });
    try {
      const [quizzes, summaries] = await Promise.all([
        assessmentApi.quizzes(projectId),
        assessmentApi.assessments(projectId),
      ]);
      if (get().projectId !== projectId) return;
      set({ quizzes, quizzesState: "ready", summaries, summariesState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({
        quizzesState: "error",
        summariesState: "error",
        error: toApiError(e).message,
      });
    }
  },

  createQuiz: async (projectId, form) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    const types: ("MCQ" | "OPEN_ENDED")[] = [];
    if (form.mcq) types.push("MCQ");
    if (form.openEnded) types.push("OPEN_ENDED");
    if (types.length === 0) {
      set({ error: "Select at least one question type." });
      return;
    }
    set({ busyState: "working", error: null });
    try {
      const created = await assessmentApi.createQuiz(projectId, {
        questionCount: Math.min(Math.max(Math.round(form.questionCount) || 5, 1), 20),
        difficulty: form.difficulty,
        questionTypes: types,
        clientRequestKey: newRequestKey(),
      });
      if (get().projectId !== projectId) return;
      set((s) => ({
        quizzes: [created.quiz, ...s.quizzes],
        activeQuiz: created,
        activeAttempt: null,
        result: null,
        busyState: "idle",
      }));
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ busyState: "error", error: toApiError(e).message });
    }
  },

  selectQuiz: async (projectId, quizId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ detailState: "loading", error: null, result: null, activeAttempt: null });
    try {
      const detail = await assessmentApi.quiz(projectId, quizId);
      if (get().projectId !== projectId) return;
      set({ activeQuiz: detail, detailState: "ready" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ detailState: "error", error: toApiError(e).message });
    }
  },

  startAttempt: async (projectId, quizId) => {
    if (get().projectId !== projectId) return;
    set({ busyState: "working", error: null, result: null });
    try {
      const detail = await assessmentApi.startAttempt(projectId, quizId);
      if (get().projectId !== projectId) return;
      set({ activeAttempt: detail, busyState: "idle" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ busyState: "error", error: toApiError(e).message });
    }
  },

  answerQuestion: async (projectId, attemptId, questionId, answer) => {
    if (get().projectId !== projectId) return;
    const current = get().activeAttempt;
    if (!current || get().busyState === "working") return;
    set({ busyState: "working", error: null });
    try {
      await assessmentApi.answer(projectId, attemptId, questionId, answer);
      // Server is the source of truth: re-read the attempt so submitted
      // answers, feedback, and correct-option reveals apply exactly once.
      const refreshed = await assessmentApi.attempt(projectId, attemptId);
      if (get().projectId === projectId && get().activeAttempt?.attempt.id === attemptId) {
        set({ activeAttempt: refreshed, busyState: "idle" });
      }
    } catch (e) {
      if (get().projectId === projectId && get().activeAttempt?.attempt.id === attemptId) {
        set({ busyState: "error", error: toApiError(e).message });
      }
    }
  },

  completeAttempt: async (projectId, attemptId) => {
    if (get().projectId !== projectId) return;
    set({ busyState: "working", error: null });
    try {
      const result = await assessmentApi.complete(projectId, attemptId);
      const summaries = await assessmentApi.assessments(projectId);
      if (get().projectId !== projectId) return;
      set({ result, summaries, busyState: "idle", activeAttempt: null });
      // Completion drives synchronous mastery/growth/recommendation updates
      // server-side: refresh the sibling slices so estimates appear without
      // a reload. Fire-and-forget; each fetch owns its errors.
      void useMasteryStore
        .getState()
        .fetchList(projectId)
        .catch(() => {});
      void useGrowthStore
        .getState()
        .fetchGrowth(projectId)
        .catch(() => {});
      void useRecommendationsStore
        .getState()
        .fetchList(projectId)
        .catch(() => {});
      void useAnalyticsStore
        .getState()
        .fetchDashboard(projectId)
        .catch(() => {});
    } catch (e) {
      set({ busyState: "error", error: toApiError(e).message });
    }
  },

  openAssessment: async (projectId, assessmentId) => {
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ busyState: "working", error: null });
    try {
      const result = await assessmentApi.assessment(projectId, assessmentId);
      if (get().projectId !== projectId) return;
      set({ result, activeAttempt: null, activeQuiz: null, busyState: "idle" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ busyState: "error", error: toApiError(e).message });
    }
  },

  practiceConcept: async (projectId, conceptId) => {
    // Recommendation-driven practice: a focused quiz via the existing
    // adaptive engine (bank reuse, grounded generation, idempotency),
    // then straight into the attempt.
    if (get().projectId !== projectId) set({ ...initial, projectId });
    set({ busyState: "working", error: null, result: null });
    try {
      const created = await assessmentApi.createQuiz(projectId, {
        questionCount: 5,
        difficulty: null,
        questionTypes: ["MCQ", "OPEN_ENDED"],
        clientRequestKey: newRequestKey(),
        focusConceptIds: [conceptId],
      });
      if (get().projectId !== projectId) return;
      set((s) => ({
        quizzes: [created.quiz, ...s.quizzes],
        activeQuiz: created,
        busyState: "idle",
      }));
      const detail = await assessmentApi.startAttempt(projectId, created.quiz.id);
      if (get().projectId !== projectId) return;
      set({ activeAttempt: detail, busyState: "idle" });
    } catch (e) {
      if (get().projectId !== projectId) return;
      set({ busyState: "error", error: toApiError(e).message });
    }
  },

  backToList: () =>
    set({ activeQuiz: null, activeAttempt: null, result: null, detailState: "idle" }),

  clearError: () =>
    set((s) => ({
      error: null,
      busyState: s.busyState === "error" ? ("idle" as const) : s.busyState,
    })),

  reset: () => set(initial),
}));
