import { MemoryRouter, Route, Routes } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { assessmentApi } from "@/api/assessment";
import { TopNav } from "@/components/layout/TopNav";
import { Card } from "@/components/ui/card";
import { SpaceDetailPage } from "@/app/pages/SpaceDetailPage";
import { QuizSection } from "@/features/quizzes/components/QuizSection";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useAuthStore } from "@/stores/useAuthStore";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";

// Only the HTTP boundary is mocked; mapping, stores, and components run for real.
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
vi.mock("@/api/spaces", () => ({
  spacesApi: { list: vi.fn(), get: vi.fn(), create: vi.fn(), update: vi.fn(), archive: vi.fn() },
}));
vi.mock("@/api/projects", () => ({
  projectsApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    archive: vi.fn(),
  },
}));

import { projectsApi } from "@/api/projects";
import { spacesApi } from "@/api/spaces";

const mockQuizzes = assessmentApi.quizzes as Mock;
const mockSummaries = assessmentApi.assessments as Mock;
const mockQuizDetail = assessmentApi.quiz as Mock;
const mockCreateQuiz = assessmentApi.createQuiz as Mock;
const mockStartAttempt = assessmentApi.startAttempt as Mock;

function reset() {
  useAssessmentStore.getState().reset();
  useSpacesStore.getState().reset();
  useProjectsStore.getState().reset();
  vi.clearAllMocks();
}

describe("quiz back navigation", () => {
  beforeEach(reset);

  it("leaves the result view with the list intact and no stuck error", async () => {
    const quiz = {
      id: "quiz-1",
      projectId: "proj-1",
      title: "Photosynthesis — Practice Quiz",
      status: "READY" as const,
      difficulty: null,
      questionCount: 2,
      createdAt: "",
    };
    mockQuizzes.mockResolvedValue([quiz]);
    mockSummaries.mockResolvedValue([]);
    mockQuizDetail.mockResolvedValue({ quiz, questions: [] });
    const store = useAssessmentStore.getState();
    await store.fetchQuizzes("proj-1");
    await store.selectQuiz("proj-1", "quiz-1");
    expect(useAssessmentStore.getState().activeQuiz?.quiz.id).toBe("quiz-1");

    // Simulate a completed attempt sitting on the result view.
    useAssessmentStore.setState({
      result: {
        assessmentId: "asm-1",
        quizAttemptId: "att-1",
        quizId: "quiz-1",
        totalQuestions: 2,
        answeredCount: 2,
        correctCount: 2,
        partialCount: 0,
        incorrectCount: 0,
        score: 100,
        conceptResults: [],
      },
    });
    useAssessmentStore.getState().backToList();

    const s = useAssessmentStore.getState();
    expect(s.result).toBeNull();
    expect(s.activeQuiz).toBeNull();
    expect(s.activeAttempt).toBeNull();
    expect(s.detailState).toBe("idle");
    expect(s.error).toBeNull();
    expect(s.busyState).toBe("idle");
    // The already-loaded list survives: no refetch, no loading flash.
    expect(s.quizzes).toHaveLength(1);
    expect(s.quizzesState).toBe("ready");
  });
});

describe("quiz titles", () => {
  beforeEach(reset);

  it("renders the real API-provided title in the quiz list", async () => {
    mockQuizzes.mockResolvedValue([
      {
        id: "quiz-9",
        projectId: "proj-1",
        title: "Mitochondria — Practice Quiz",
        status: "READY",
        difficulty: null,
        questionCount: 5,
        createdAt: "",
      },
    ]);
    mockSummaries.mockResolvedValue([]);
    render(
      <MemoryRouter>
        <QuizSection projectId="proj-1" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText("Mitochondria — Practice Quiz")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Untitled quiz")).not.toBeInTheDocument();
  });
});

describe("space header card", () => {
  beforeEach(reset);

  it("groups the space name and description inside a styled card", async () => {
    (spacesApi.get as Mock).mockResolvedValue({
      id: "space-a",
      name: "Mathematics",
      description: "Numbers and shapes",
    });
    (projectsApi.list as Mock).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    render(
      <MemoryRouter initialEntries={["/spaces/space-a"]}>
        <Routes>
          <Route path="/spaces/:spaceId" element={<SpaceDetailPage />} />
        </Routes>
      </MemoryRouter>,
    );
    const heading = await screen.findByRole("heading", { name: "Mathematics" });
    const card = heading.closest(".card-dark");
    expect(card).not.toBeNull();
    expect(card?.textContent).toContain("Numbers and shapes");
  });
});

describe("top navigation", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: { id: "u1", email: "learner@example.com", displayName: "Learner", role: "learner" },
      status: "authenticated",
    });
  });

  function renderNav(path = "/") {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <TopNav />
      </MemoryRouter>,
    );
  }

  it("marks Home active with a dark-blue background and readable text", () => {
    renderNav("/");
    const home = screen.getByRole("link", { name: "Home" });
    expect(home.classList.contains("bg-primary")).toBe(true);
    expect(home.classList.contains("text-primary-foreground")).toBe(true);
    for (const name of ["Spaces", "Analytics"]) {
      const link = screen.getByRole("link", { name });
      expect(link.classList.contains("bg-primary")).toBe(false);
    }
  });

  it("keeps the navigation bar visually outside the hero", () => {
    renderNav("/");
    const header = screen.getByText("AI Learning Companion").closest("header");
    expect(header).not.toBeNull();
    const nav = screen.getByRole("navigation", { name: "Primary" });
    expect(header!.contains(nav)).toBe(false);
  });

  it("pins the navigation bar to the viewport top on scroll", () => {
    renderNav("/");
    const nav = screen.getByRole("navigation", { name: "Primary" });
    // Sticky must be a direct child of the app column: a sticky element can
    // never escape its parent, so the bar cannot live inside the header.
    const bar = nav.closest("div.sticky");
    expect(bar).not.toBeNull();
    expect(bar!.classList.contains("top-0")).toBe(true);
  });

  it("orders the caption above the title with a deliberate gap", () => {
    renderNav("/");
    const caption = screen.getByText(/Learn.*Practice.*Master/);
    const title = screen.getByText("AI Learning Companion");
    expect(caption.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(title.className).toMatch(/text-4xl/);
  });
});

describe("card system", () => {
  it("gives every major card an intentional dark or light surface", () => {
    const { unmount: unmountDark } = render(<Card variant="dark">dark</Card>);
    expect(screen.getByText("dark").className).toContain("card-dark");
    unmountDark();
    const { unmount: unmountLight } = render(<Card variant="light">light</Card>);
    expect(screen.getByText("light").className).toContain("card-hero");
    unmountLight();
    render(<Card>plain</Card>);
    const plain = screen.getByText("plain").className;
    expect(plain).not.toContain("card-dark");
    expect(plain).not.toContain("card-hero");
  });
});

describe("loading animations", () => {
  beforeEach(reset);

  it("spins the Generate button while a quiz is being created", async () => {
    mockQuizzes.mockResolvedValue([]);
    mockSummaries.mockResolvedValue([]);
    let rejectCreate!: (e: unknown) => void;
    mockCreateQuiz.mockImplementation(() => new Promise((_, rej) => (rejectCreate = rej)));
    render(
      <MemoryRouter>
        <QuizSection projectId="proj-1" />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /generate quiz/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /generate quiz/i }));
    await waitFor(() => expect(screen.getByText("Generating…")).toBeInTheDocument());
    // Animated spinner next to the label (not static text alone).
    expect(
      screen
        .getByRole("button", { name: /generating/i })
        .querySelector(".animate-spin"),
    ).not.toBeNull();
    rejectCreate!(new Error("stop"));
    await waitFor(() =>
      expect(screen.getByText("Quiz generation failed")).toBeInTheDocument(),
    );
  });

  it("spins the Start attempt button while an attempt is starting", async () => {
    const quiz = {
      id: "quiz-1",
      projectId: "proj-1",
      title: "Energy — Practice Quiz",
      status: "READY" as const,
      difficulty: null,
      questionCount: 1,
      createdAt: "",
    };
    mockQuizzes.mockResolvedValue([quiz]);
    mockSummaries.mockResolvedValue([]);
    mockQuizDetail.mockResolvedValue({ quiz, questions: [] });
    let rejectStart!: (e: unknown) => void;
    mockStartAttempt.mockImplementation(() => new Promise((_, rej) => (rejectStart = rej)));
    render(
      <MemoryRouter>
        <QuizSection projectId="proj-1" />
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByText("Energy — Practice Quiz"));
    fireEvent.click(await screen.findByRole("button", { name: /start attempt/i }));
    await waitFor(() => expect(screen.getByText("Starting…")).toBeInTheDocument());
    expect(
      screen.getByRole("button", { name: /starting/i }).querySelector(".animate-spin"),
    ).not.toBeNull();
    rejectStart!(new Error("stop"));
    await waitFor(() =>
      expect(screen.getByText("Quiz generation failed")).toBeInTheDocument(),
    );
  });
});
