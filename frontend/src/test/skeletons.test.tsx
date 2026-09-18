import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { adminApi } from "@/api/admin";
import { assessmentApi } from "@/api/assessment";
import { growthApi } from "@/api/growth";
import { masteryApi } from "@/api/mastery";
import { tutorApi } from "@/api/tutor";
import { toApiError } from "@/api/client";
import { AdminPage } from "@/app/pages/AdminPage";
import { GrowthSection } from "@/features/growth/components/GrowthSection";
import { MasterySection } from "@/features/mastery/components/MasterySection";
import { QuizSection } from "@/features/quizzes/components/QuizSection";
import { TutorSection } from "@/features/tutor/components/TutorSection";
import {
  SectionLoading,
  SkeletonCard,
  SkeletonChart,
  SkeletonConceptRows,
  SkeletonList,
  SkeletonQuizQuestion,
  SkeletonStat,
  SkeletonTable,
  SkeletonText,
  SkeletonTutorMessage,
  SlowHint,
} from "@/components/ui";
import { useSlowHint } from "@/hooks/useSlowHint";
import { useFirstVisible } from "@/hooks/useFirstVisible";
import { useAdminStore } from "@/stores/useAdminStore";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useMasteryStore } from "@/stores/useMasteryStore";
import { useTutorStore } from "@/stores/useTutorStore";

vi.mock("@/api/mastery", () => ({
  masteryApi: { list: vi.fn(), detail: vi.fn(), history: vi.fn() },
}));
vi.mock("@/api/growth", () => ({ growthApi: { get: vi.fn(), history: vi.fn() } }));
vi.mock("@/api/tutor", () => ({
  tutorApi: {
    conversations: vi.fn(),
    createConversation: vi.fn(),
    messages: vi.fn(),
    send: vi.fn(),
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
vi.mock("@/api/admin", () => ({
  adminApi: {
    overview: vi.fn(),
    users: vi.fn(),
    userJourney: vi.fn(),
    activity: vi.fn(),
    jobs: vi.fn(),
    health: vi.fn(),
    aiSummary: vi.fn(),
    evaluationSummary: vi.fn(),
    evaluationRuns: vi.fn(),
    runEvaluations: vi.fn(),
  },
}));

function resetAll() {
  useMasteryStore.getState().reset();
  useGrowthStore.getState().reset();
  useTutorStore.getState().reset();
  useAssessmentStore.getState().reset();
  useAdminStore.getState().reset();
  vi.clearAllMocks();
}

describe("skeleton primitives", () => {
  it("announce once via SectionLoading and hide shapes from screen readers", () => {
    render(
      <SectionLoading label="Loading things">
        <SkeletonStat />
        <SkeletonCard />
        <SkeletonList rows={2} />
        <SkeletonTable rows={2} cols={2} />
        <SkeletonChart />
        <SkeletonText lines={2} />
        <SkeletonConceptRows rows={2} />
        <SkeletonTutorMessage thinking />
        <SkeletonQuizQuestion options={2} />
      </SectionLoading>,
    );
    const regions = screen.getAllByRole("status");
    expect(regions).toHaveLength(1);
    expect(regions[0]).toHaveAttribute("aria-label", "Loading things");
    expect(regions[0]).toHaveAttribute("aria-busy", "true");
  });

  it("shows the slow hint only after the threshold", () => {
    vi.useFakeTimers();
    try {
      const { result, rerender } = renderHook(
        ({ active }: { active: boolean }) => useSlowHint(active, 4000),
        { initialProps: { active: true } },
      );
      expect(result.current).toBe(false);
      act(() => {
        vi.advanceTimersByTime(3999);
      });
      expect(result.current).toBe(false);
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(result.current).toBe(true);
      const { queryByText } = render(<SlowHint show={result.current}>Still loading…</SlowHint>);
      expect(queryByText("Still loading…")).toBeInTheDocument();
      rerender({ active: false });
      expect(result.current).toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("useFirstVisible", () => {
  const RealIO = globalThis.IntersectionObserver;

  function VisibilityProbe() {
    const [ref, visible] = useFirstVisible<HTMLDivElement>();
    return (
      <div ref={ref} data-testid="probe">
        {visible ? "visible" : "hidden"}
      </div>
    );
  }

  beforeEach(() => {
    // jsdom default: no IntersectionObserver at all.
    // @ts-expect-error remove for fallback test
    delete globalThis.IntersectionObserver;
  });

  it("is visible immediately where IntersectionObserver is unavailable", () => {
    const { result } = renderHook(() => useFirstVisible<HTMLDivElement>());
    expect(result.current[1]).toBe(true);
    globalThis.IntersectionObserver = RealIO;
  });

  it("gates on intersection where supported", () => {
    let notify: (entries: { isIntersecting: boolean }[]) => void = () => {};
    class FakeIO {
      constructor(cb: (entries: { isIntersecting: boolean }[]) => void) {
        notify = cb;
      }
      observe() {}
      disconnect() {}
    }
    // @ts-expect-error test double
    globalThis.IntersectionObserver = FakeIO;
    try {
      const { getByTestId } = render(<VisibilityProbe />);
      expect(getByTestId("probe")).toHaveTextContent("hidden");
      act(() => {
        notify([{ isIntersecting: false }]);
      });
      expect(getByTestId("probe")).toHaveTextContent("hidden");
      act(() => {
        notify([{ isIntersecting: true }]);
      });
      expect(getByTestId("probe")).toHaveTextContent("visible");
    } finally {
      globalThis.IntersectionObserver = RealIO;
    }
  });
});

describe("mastery skeleton lifecycle", () => {
  beforeEach(resetAll);

  const item = {
    conceptId: "c1",
    conceptName: "TCP",
    masteryScore: 0.69,
    confidence: 0.8,
    trend: "IMPROVING" as const,
    evidenceCount: 3,
    recentPerformance: ["C"],
    hasEvidence: true,
    updatedAt: "",
  };

  it("shows skeleton while loading, then real concepts", async () => {
    let release!: (v: unknown) => void;
    (masteryApi.list as Mock).mockReturnValueOnce(
      new Promise((res) => {
        release = res as (v: unknown) => void;
      }),
    );
    render(<MasterySection projectId="p" />);
    expect(screen.getByRole("status", { name: "Loading mastery" })).toBeInTheDocument();
    release({ items: [item], total: 1 });
    await waitFor(() => expect(screen.getByText("TCP")).toBeInTheDocument());
    expect(screen.queryByRole("status", { name: "Loading mastery" })).not.toBeInTheDocument();
  });

  it("shows empty state for 200 with zero concepts", async () => {
    (masteryApi.list as Mock).mockResolvedValue({ items: [], total: 0 });
    render(<MasterySection projectId="p" />);
    await waitFor(() => expect(screen.getByText("No mastery yet.")).toBeInTheDocument());
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("classifies timeout vs 500 distinctly and retry recovers", async () => {
    const timeoutErr = {
      isAxiosError: true,
      code: "ECONNABORTED",
      message: "timeout of 15000ms exceeded",
      response: undefined,
    };
    expect(toApiError(timeoutErr).code).toBe("REQUEST_TIMEOUT");
    (masteryApi.list as Mock).mockRejectedValueOnce(timeoutErr);
    (masteryApi.list as Mock).mockResolvedValueOnce({ items: [item], total: 1 });
    render(<MasterySection projectId="p" />);
    await waitFor(() => expect(screen.getByText("Could not load mastery")).toBeInTheDocument());
    expect(screen.queryByRole("status", { name: "Loading mastery" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("TCP")).toBeInTheDocument());
  });
});

describe("growth skeleton lifecycle", () => {
  beforeEach(resetAll);

  const growth = {
    projectId: "p",
    status: "IMPROVING" as const,
    hasEvidence: true,
    overallMastery: 0.71,
    averageConfidence: 0.6,
    conceptsImproving: 1,
    conceptsStable: 0,
    conceptsRequiringAttention: 0,
    assessedConcepts: 1,
    assessmentCount: 2,
    questionsAnswered: 5,
    updatedAt: "",
    concepts: [],
  };

  it("shows skeleton while loading, then real stats", async () => {
    let release!: (v: unknown) => void;
    (growthApi.get as Mock).mockReturnValueOnce(
      new Promise((res) => {
        release = res as (v: unknown) => void;
      }),
    );
    (growthApi.history as Mock).mockResolvedValue([]);
    render(<GrowthSection projectId="p" />);
    expect(screen.getByRole("status", { name: "Loading growth" })).toBeInTheDocument();
    release(growth);
    await waitFor(() => expect(screen.getByText("71%")).toBeInTheDocument());
    expect(screen.queryByRole("status", { name: "Loading growth" })).not.toBeInTheDocument();
  });
});

describe("tutor thinking state", () => {
  beforeEach(resetAll);

  it("shows thinking even with zero prior messages", async () => {
    (tutorApi.conversations as Mock).mockResolvedValue([
      { id: "c1", projectId: "p", title: "Chat", createdAt: "", updatedAt: "" },
    ]);
    (tutorApi.messages as Mock).mockResolvedValue([]);
    render(<TutorSection projectId="p" />);
    await waitFor(() => expect(tutorApi.messages).toHaveBeenCalled());
    useTutorStore.setState({ sendState: "sending" });
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "Tutor is thinking" })).toBeInTheDocument(),
    );
  });
});

describe("quiz generation skeleton", () => {
  beforeEach(resetAll);

  it("shows generation structure while busy, then clears on result", async () => {
    (assessmentApi.quizzes as Mock).mockResolvedValue([]);
    (assessmentApi.assessments as Mock).mockResolvedValue([]);
    render(<QuizSection projectId="p" />);
    await waitFor(() => expect(screen.getByText("No quizzes yet.")).toBeInTheDocument());
    useAssessmentStore.setState({ busyState: "working" });
    await waitFor(() =>
      expect(screen.getByRole("status", { name: "Generating quiz" })).toBeInTheDocument(),
    );
    useAssessmentStore.setState({ busyState: "idle" });
    await waitFor(() =>
      expect(screen.queryByRole("status", { name: "Generating quiz" })).not.toBeInTheDocument(),
    );
  });
});

describe("admin tabs load independently", () => {
  beforeEach(resetAll);

  it("fetches overview on mount but not users until selected", async () => {
    (adminApi.overview as Mock).mockResolvedValue({
      users: 1,
      admins: 1,
      spaces: 0,
      projects: 0,
      materials: 0,
      materialsReady: 0,
      assessments: 0,
      quizAttempts: 0,
      tutorConversations: 0,
      tutorMessages: 0,
      activeRecommendations: 0,
      events: 0,
      aiCalls: 0,
      evaluationRuns: 0,
      jobs: {},
    });
    (adminApi.health as Mock).mockResolvedValue({
      overall: "healthy",
      api: "healthy",
      database: "healthy",
      databaseConfigured: true,
      ai: {},
      storage: {},
      queue: {},
    });
    render(<AdminPage />);
    await waitFor(() => expect(adminApi.overview).toHaveBeenCalled());
    expect(adminApi.users).not.toHaveBeenCalled();
    expect(adminApi.activity).not.toHaveBeenCalled();
    (adminApi.users as Mock).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 25 });
    fireEvent.click(screen.getByRole("tab", { name: "Users" }));
    await waitFor(() => expect(adminApi.users).toHaveBeenCalled());
  });
});
