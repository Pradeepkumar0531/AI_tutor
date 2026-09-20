import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { analyticsApi } from "@/api/analytics";
import { assessmentApi } from "@/api/assessment";
import { QuizSection } from "@/features/quizzes/components/QuizSection";
import { useAnalyticsStore } from "@/stores/useAnalyticsStore";
import { useAssessmentStore } from "@/stores/useAssessmentStore";

// Only the HTTP boundary is mocked; mapping, store, and components run for real.
vi.mock("@/api/analytics", () => ({
  analyticsApi: {
    dashboard: vi.fn(),
    activity: vi.fn(),
    activityByDay: vi.fn(),
    masteryTrend: vi.fn(),
  },
}));
vi.mock("@/api/assessment", () => ({
  assessmentApi: {
    quizzes: vi.fn(),
    createQuiz: vi.fn(),
    quiz: vi.fn(),
    startAttempt: vi.fn(),
    attempt: vi.fn(),
    answer: vi.fn(),
    complete: vi.fn(),
    assessments: vi.fn(),
    assessment: vi.fn(),
  },
}));

const mockQuizzes = assessmentApi.quizzes as Mock;
const mockCreate = assessmentApi.createQuiz as Mock;
const mockStart = assessmentApi.startAttempt as Mock;
const mockAttempt = assessmentApi.attempt as Mock;
const mockAnswer = assessmentApi.answer as Mock;
const mockComplete = assessmentApi.complete as Mock;
const mockSummaries = assessmentApi.assessments as Mock;
const mockAssessment = assessmentApi.assessment as Mock;

function reset() {
  useAssessmentStore.getState().reset();
  useAnalyticsStore.getState().reset();
  vi.clearAllMocks();
}

const quiz = {
  id: "quiz-1",
  projectId: "proj-1",
  title: "Untitled quiz",
  status: "READY" as const,
  difficulty: null,
  questionCount: 2,
  createdAt: "",
};

const mcq = {
  questionId: "q-mcq",
  type: "MCQ" as const,
  prompt: "What does the material state about Photosynthesis?",
  options: [
    { id: "A", text: "It converts sunlight." },
    { id: "B", text: "It does not cover this." },
  ],
  position: 0,
  points: 1,
  difficulty: "MEDIUM" as const,
  concepts: [{ id: "c-photo", name: "Photosynthesis" }],
  sources: [{ material_name: "Doc", page_start: 1, page_end: 1 }],
};

const opened = {
  questionId: "q-open",
  type: "OPEN_ENDED" as const,
  prompt: "Explain Photosynthesis in your own words.",
  options: [],
  position: 1,
  points: 1,
  difficulty: "MEDIUM" as const,
  concepts: [{ id: "c-photo", name: "Photosynthesis" }],
  sources: [{ material_name: "Doc", page_start: 1, page_end: 1 }],
};

const blank = {
  submitted: null,
  isCorrect: null,
  score: null,
  feedback: null,
  correctOptionId: null,
  evaluation: null,
};

const attempt = {
  id: "att-1",
  quizId: "quiz-1",
  status: "IN_PROGRESS" as const,
  score: null,
  maxScore: 2,
  startedAt: "",
  completedAt: null,
};

function listed() {
  mockQuizzes.mockResolvedValue([quiz]);
  mockSummaries.mockResolvedValue([]);
}

describe("assessment store", () => {
  beforeEach(reset);

  it("loads quizzes and summaries", async () => {
    listed();
    await useAssessmentStore.getState().fetchQuizzes("proj-1");
    const s = useAssessmentStore.getState();
    expect(s.quizzes).toHaveLength(1);
    expect(s.quizzesState).toBe("ready");
  });

  it("creates a quiz with a client idempotency key", async () => {
    listed();
    mockCreate.mockResolvedValue({ quiz, questions: [mcq, opened] });
    await useAssessmentStore.getState().fetchQuizzes("proj-1");
    await useAssessmentStore
      .getState()
      .createQuiz("proj-1", { questionCount: 5, difficulty: null, mcq: true, openEnded: true });
    expect(mockCreate).toHaveBeenCalledWith(
      "proj-1",
      expect.objectContaining({
        questionCount: 5,
        questionTypes: ["MCQ", "OPEN_ENDED"],
        clientRequestKey: expect.any(String),
      }),
    );
    expect(useAssessmentStore.getState().activeQuiz?.quiz.id).toBe("quiz-1");
  });

  it("refuses creation without question types", async () => {
    listed();
    await useAssessmentStore.getState().fetchQuizzes("proj-1");
    await useAssessmentStore
      .getState()
      .createQuiz("proj-1", { questionCount: 5, difficulty: null, mcq: false, openEnded: false });
    expect(mockCreate).not.toHaveBeenCalled();
    expect(useAssessmentStore.getState().error).toMatch(/question type/i);
  });

  it("answers then reloads the attempt from the server", async () => {
    listed();
    mockStart.mockResolvedValue({
      attempt,
      questions: [
        { ...mcq, answer: blank },
        { ...opened, answer: blank },
      ],
    });
    mockAnswer.mockResolvedValue({
      isCorrect: true,
      score: 1,
      feedback: "Correct.",
      correctOptionId: "A",
      evaluation: null,
    });
    mockAttempt.mockResolvedValue({
      attempt,
      questions: [
        {
          ...mcq,
          answer: {
            submitted: "A",
            isCorrect: true,
            score: 1,
            feedback: "Correct.",
            correctOptionId: "A",
            evaluation: null,
          },
        },
        { ...opened, answer: blank },
      ],
    });
    const store = useAssessmentStore.getState();
    await store.fetchQuizzes("proj-1");
    await useAssessmentStore.getState().startAttempt("proj-1", "quiz-1");
    await useAssessmentStore.getState().answerQuestion("proj-1", "att-1", "q-mcq", "A");
    expect(mockAnswer).toHaveBeenCalledWith("proj-1", "att-1", "q-mcq", "A");
    expect(mockAttempt).toHaveBeenCalledWith("proj-1", "att-1");
    const answered = useAssessmentStore
      .getState()
      .activeAttempt?.questions.find((q) => q.questionId === "q-mcq");
    expect(answered?.answer.isCorrect).toBe(true);
    expect(answered?.answer.correctOptionId).toBe("A");
  });

  it("completes and refreshes result history", async () => {
    listed();
    const result = {
      assessmentId: "as-1",
      quizAttemptId: "att-1",
      quizId: "quiz-1",
      totalQuestions: 1,
      answeredCount: 1,
      correctCount: 1,
      partialCount: 0,
      incorrectCount: 0,
      score: 100,
      conceptResults: [
        {
          conceptId: "c-photo",
          conceptName: "Photosynthesis",
          questionsSeen: 1,
          correctCount: 1,
          partialCount: 0,
          incorrectCount: 0,
          normalizedScore: 1,
          recent: ["C"],
        },
      ],
    };
    mockComplete.mockResolvedValue(result);
    mockSummaries.mockResolvedValue([
      {
        id: "as-1",
        quizAttemptId: "att-1",
        quizId: "quiz-1",
        status: "COMPLETED",
        score: 100,
        completedAt: "",
      },
    ]);
    await useAssessmentStore.getState().fetchQuizzes("proj-1");
    await useAssessmentStore.getState().completeAttempt("proj-1", "att-1");
    const s = useAssessmentStore.getState();
    expect(s.result?.score).toBe(100);
    expect(s.activeAttempt).toBeNull();
    expect(s.summaries).toHaveLength(1);
    // Completion refreshes sibling slices (mastery/growth/recs/analytics).
    await waitFor(() => expect(analyticsApi.dashboard).toHaveBeenCalledWith("proj-1"));
  });

  it("records creation errors without crashing", async () => {
    listed();
    mockCreate.mockRejectedValue(new Error("no evidence"));
    await useAssessmentStore.getState().fetchQuizzes("proj-1");
    await useAssessmentStore
      .getState()
      .createQuiz("proj-1", { questionCount: 5, difficulty: null, mcq: true, openEnded: false });
    const s = useAssessmentStore.getState();
    expect(s.busyState).toBe("error");
    expect(s.error).toContain("no evidence");
  });
});

describe("QuizSection", () => {
  beforeEach(reset);

  function renderSection() {
    return render(<QuizSection projectId="proj-1" />);
  }

  it("creates a quiz and shows learner-safe questions", async () => {
    listed();
    mockCreate.mockResolvedValue({ quiz, questions: [mcq, opened] });
    mockStart.mockResolvedValue({
      attempt,
      questions: [
        { ...mcq, answer: blank },
        { ...opened, answer: blank },
      ],
    });
    renderSection();
    await waitFor(() => expect(screen.getByText("Generate quiz")).toBeEnabled());
    fireEvent.click(screen.getByText("Generate quiz"));
    await waitFor(() => expect(screen.getByText("Start attempt")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Start attempt"));
    await waitFor(() =>
      expect(
        screen.getByText(/What does the material state about Photosynthesis/),
      ).toBeInTheDocument(),
    );
    // Learner-safe: options visible, correct answers nowhere.
    expect(screen.getByText("It converts sunlight.")).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/correct_option_id|reference_answer/);
  });

  it("surfaces a generation failure and retry discovers the persisted quiz", async () => {
    // Regression: generation failures used to be silent (spinner, then
    // nothing). Worse, a timed-out request had already persisted the quiz —
    // the retry must re-read the list (finding the ghost) rather than
    // blindly regenerating a duplicate.
    listed();
    mockCreate.mockRejectedValueOnce(new Error("Could not reach the server."));
    renderSection();
    await waitFor(() => expect(screen.getByText("Generate quiz")).toBeEnabled());
    fireEvent.click(screen.getByText("Generate quiz"));
    await waitFor(() => expect(screen.getByText("Quiz generation failed")).toBeInTheDocument());
    expect(screen.getByText(/Could not reach the server/)).toBeInTheDocument();
    // The timed-out quiz actually persisted: the list now returns it.
    mockQuizzes.mockResolvedValue([{ ...quiz, title: "Untitled quiz (recovered)" }]);
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("Untitled quiz (recovered)")).toBeInTheDocument());
    expect(screen.queryByText("Quiz generation failed")).not.toBeInTheDocument();
    expect(mockCreate).toHaveBeenCalledTimes(1);
  });

  it("answers drafts locally and submits everything with one Submit Quiz", async () => {
    listed();
    mockCreate.mockResolvedValue({ quiz, questions: [mcq, opened] });
    mockStart.mockResolvedValue({
      attempt,
      questions: [
        { ...mcq, answer: blank },
        { ...opened, answer: blank },
      ],
    });
    mockAnswer.mockResolvedValue({
      isCorrect: false,
      score: 0,
      feedback: "Not quite.",
      correctOptionId: "A",
      evaluation: null,
    });
    // Every answer re-reads the attempt from the server; the final read
    // backs the result view's per-question lines.
    mockAttempt.mockResolvedValue({
      attempt,
      questions: [
        {
          ...mcq,
          answer: {
            submitted: "B",
            isCorrect: false,
            score: 0,
            feedback: "Not quite.",
            correctOptionId: "A",
            evaluation: null,
          },
        },
        {
          ...opened,
          answer: {
            submitted: "Mitosis overview.",
            isCorrect: true,
            score: 1,
            feedback: "Correct.",
            correctOptionId: null,
            evaluation: null,
          },
        },
      ],
    });
    mockComplete.mockResolvedValue({
      assessmentId: "as-1",
      quizAttemptId: "att-1",
      quizId: "quiz-1",
      totalQuestions: 2,
      answeredCount: 2,
      correctCount: 1,
      partialCount: 0,
      incorrectCount: 1,
      score: 50,
      conceptResults: [],
    });
    mockSummaries.mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(screen.getByText("Generate quiz")).toBeEnabled());
    fireEvent.click(screen.getByText("Generate quiz"));
    await waitFor(() => expect(screen.getByText("Start attempt")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Start attempt"));
    await waitFor(() => expect(screen.getByText(/Answered 0 of 2/)).toBeInTheDocument());
    // No per-question submit buttons: one final action only.
    expect(screen.queryByRole("button", { name: "Submit answer" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("It does not cover this."));
    fireEvent.change(screen.getByLabelText("Answer for question 2"), {
      target: { value: "Mitosis overview." },
    });
    fireEvent.click(screen.getByRole("button", { name: "Submit Quiz" }));
    // Both drafts persist through the existing per-question endpoint, then
    // the attempt completes exactly once.
    await waitFor(() => expect(mockAnswer).toHaveBeenCalledTimes(2));
    expect(mockAnswer).toHaveBeenNthCalledWith(1, "proj-1", "att-1", "q-mcq", "B");
    expect(mockAnswer).toHaveBeenNthCalledWith(2, "proj-1", "att-1", "q-open", "Mitosis overview.");
    expect(mockComplete).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText("Assessment result")).toBeInTheDocument());
    expect(screen.getByText("50%", { exact: true })).toBeInTheDocument();
    expect(screen.getByText("1 of 2 correct")).toBeInTheDocument();
  });

  it("completes an attempt and shows concept performance", async () => {
    listed();
    mockCreate.mockResolvedValue({ quiz, questions: [mcq] });
    mockStart.mockResolvedValue({ attempt, questions: [{ ...mcq, answer: blank }] });
    mockAnswer.mockResolvedValue({
      isCorrect: true,
      score: 1,
      feedback: "Correct.",
      correctOptionId: "A",
      evaluation: null,
    });
    mockAttempt.mockResolvedValue({
      attempt,
      questions: [
        {
          ...mcq,
          answer: {
            submitted: "A",
            isCorrect: true,
            score: 1,
            feedback: "Correct.",
            correctOptionId: "A",
            evaluation: null,
          },
        },
      ],
    });
    mockComplete.mockResolvedValue({
      assessmentId: "as-1",
      quizAttemptId: "att-1",
      quizId: "quiz-1",
      totalQuestions: 1,
      answeredCount: 1,
      correctCount: 1,
      partialCount: 0,
      incorrectCount: 0,
      score: 100,
      conceptResults: [
        {
          conceptId: "c-photo",
          conceptName: "Photosynthesis",
          questionsSeen: 1,
          correctCount: 1,
          partialCount: 0,
          incorrectCount: 0,
          normalizedScore: 1,
          recent: ["C"],
        },
      ],
    });
    mockSummaries.mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(screen.getByText("Generate quiz")).toBeEnabled());
    fireEvent.click(screen.getByText("Generate quiz"));
    await waitFor(() => expect(screen.getByText("Start attempt")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Start attempt"));
    await waitFor(() =>
      expect(
        screen.getByText(/What does the material state about Photosynthesis/),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByText("It converts sunlight."));
    fireEvent.click(screen.getByRole("button", { name: "Submit Quiz" }));
    await waitFor(() => expect(screen.getByText("100%")).toBeInTheDocument());
    expect(screen.getByText("Photosynthesis")).toBeInTheDocument();
    expect(document.body.textContent).toContain("1c/0p/0i of 1");
    // Concise per-question line plus an expandable review.
    expect(screen.getByText(/Q1 — Correct\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Review answers" }));
    await waitFor(() => expect(screen.getByText(/you chose A/)).toBeInTheDocument());
  });

  it("opens a past result from history", async () => {
    mockQuizzes.mockResolvedValue([]);
    mockSummaries.mockResolvedValue([
      {
        id: "as-9",
        quizAttemptId: "att-9",
        quizId: "quiz-9",
        status: "COMPLETED",
        score: 50,
        completedAt: "",
      },
    ]);
    mockCreate.mockResolvedValue({ quiz, questions: [] });
    mockAssessment.mockResolvedValue({
      assessmentId: "as-9",
      quizAttemptId: "att-9",
      quizId: "quiz-9",
      totalQuestions: 2,
      answeredCount: 2,
      correctCount: 1,
      partialCount: 0,
      incorrectCount: 1,
      score: 50,
      conceptResults: [],
    });
    renderSection();
    await waitFor(() => expect(screen.getByText("Past results")).toBeInTheDocument());
    fireEvent.click(screen.getByText(/50%/));
    await waitFor(() => expect(screen.getByText("Assessment result")).toBeInTheDocument());
    expect(within(document.body).getByText("50%", { exact: true })).toBeInTheDocument();
  });

  it("shows an honest empty state with no quizzes", async () => {
    mockQuizzes.mockResolvedValue([]);
    mockSummaries.mockResolvedValue([]);
    renderSection();
    await waitFor(() => expect(screen.getByText("No quizzes yet.")).toBeInTheDocument());
  });
});
