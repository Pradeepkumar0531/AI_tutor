import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import {
  createMemoryRouter,
  MemoryRouter,
  Navigate,
  Route,
  Routes,
  RouterProvider,
} from "react-router-dom";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { ProjectDetailPage } from "@/app/pages/ProjectDetailPage";
import {
  ProjectAnalyticsTab,
  ProjectGrowthTab,
  ProjectMaterialsTab,
  ProjectOverviewTab,
  ProjectQuizTab,
  ProjectTutorTab,
} from "@/app/pages/project/ProjectTabs";
import { analyticsApi } from "@/api/analytics";
import { assessmentApi } from "@/api/assessment";
import { growthApi } from "@/api/growth";
import { knowledgeApi } from "@/api/knowledge";
import { materialsApi } from "@/api/materials";
import { masteryApi } from "@/api/mastery";
import { projectsApi } from "@/api/projects";
import { recommendationsApi } from "@/api/recommendations";
import { spacesApi } from "@/api/spaces";
import { tutorApi } from "@/api/tutor";
import { useAnalyticsStore } from "@/stores/useAnalyticsStore";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useKnowledgeStore } from "@/stores/useKnowledgeStore";
import { useMasteryStore } from "@/stores/useMasteryStore";
import { useMaterialsStore } from "@/stores/useMaterialsStore";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useRecommendationsStore } from "@/stores/useRecommendationsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";
import { useTutorStore } from "@/stores/useTutorStore";

// Only the HTTP boundary is mocked; routing, stores, and sections run for real.
vi.mock("@/api/spaces", () => ({
  spacesApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
  },
}));
vi.mock("@/api/projects", () => ({
  projectsApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    archive: vi.fn(),
    restore: vi.fn(),
  },
}));
vi.mock("@/api/materials", () => ({
  materialsApi: {
    list: vi.fn(),
    upload: vi.fn(),
    get: vi.fn(),
    chunks: vi.fn(),
    images: vi.fn(),
    imageBlob: vi.fn(),
    pdfBlob: vi.fn(),
    reprocess: vi.fn(),
    archive: vi.fn(),
  },
}));
vi.mock("@/api/knowledge", () => ({
  knowledgeApi: {
    status: vi.fn(),
    concepts: vi.fn(),
    concept: vi.fn(),
    search: vi.fn(),
    reprocess: vi.fn(),
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
vi.mock("@/api/analytics", () => ({
  analyticsApi: {
    dashboard: vi.fn(),
    activity: vi.fn(),
    activityByDay: vi.fn(),
    masteryTrend: vi.fn(),
  },
}));
vi.mock("@/api/mastery", () => ({
  masteryApi: { list: vi.fn(), detail: vi.fn(), history: vi.fn() },
}));
vi.mock("@/api/growth", () => ({
  growthApi: { get: vi.fn(), history: vi.fn() },
}));
vi.mock("@/api/recommendations", () => ({
  recommendationsApi: { list: vi.fn(), complete: vi.fn(), dismiss: vi.fn() },
}));
vi.mock("@/api/tutor", () => ({
  tutorApi: {
    conversations: vi.fn(),
    createConversation: vi.fn(),
    messages: vi.fn(),
    send: vi.fn(),
  },
}));

const spaceA = {
  id: "space-a",
  name: "Mathematics",
  description: "Numbers",
  archivedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-02T00:00:00Z",
  projectCount: 1,
};

const projectA = {
  id: "project-a",
  spaceId: "space-a",
  name: "Algebra",
  description: "Equations",
  learningGoal: "Solve quadratics",
  targetOutcome: null,
  difficulty: null,
  archivedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-02T00:00:00Z",
  materialCount: 0,
};

function resetStores() {
  useSpacesStore.getState().reset();
  useProjectsStore.getState().reset();
  useMaterialsStore.getState().reset();
  useKnowledgeStore.getState().reset();
  useTutorStore.getState().reset();
  useAssessmentStore.getState().reset();
  useMasteryStore.getState().reset();
  useGrowthStore.getState().reset();
  useRecommendationsStore.getState().reset();
  useAnalyticsStore.getState().reset();
  vi.clearAllMocks();
}

function mockEmptyProject() {
  (projectsApi.get as Mock).mockResolvedValue(projectA);
  (spacesApi.get as Mock).mockResolvedValue(spaceA);
  (materialsApi.list as Mock).mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
  (knowledgeApi.status as Mock).mockResolvedValue({
    project_id: "project-a",
    status: "PENDING",
    totals: { chunks_total: 0, chunks_embedded: 0, concepts: 0, materials_ready: 0 },
  });
  (knowledgeApi.concepts as Mock).mockResolvedValue({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
  });
  (tutorApi.conversations as Mock).mockResolvedValue([]);
  (tutorApi.createConversation as Mock).mockResolvedValue({
    id: "conv-a",
    projectId: "project-a",
    title: "Untitled conversation",
    createdAt: "",
    updatedAt: "",
  });
  (tutorApi.messages as Mock).mockResolvedValue([]);
  (assessmentApi.quizzes as Mock).mockResolvedValue([]);
  (assessmentApi.assessments as Mock).mockResolvedValue([]);
  (masteryApi.list as Mock).mockResolvedValue({ items: [], total: 0 });
  (growthApi.get as Mock).mockResolvedValue({
    projectId: "project-a",
    status: "STABLE",
    hasEvidence: false,
    overallMastery: 0,
    averageConfidence: 0,
    conceptsImproving: 0,
    conceptsStable: 0,
    conceptsRequiringAttention: 0,
    assessedConcepts: 0,
    assessmentCount: 0,
    questionsAnswered: 0,
    updatedAt: null,
    concepts: [],
  });
  (growthApi.history as Mock).mockResolvedValue([]);
  (recommendationsApi.list as Mock).mockResolvedValue([]);
  (analyticsApi.dashboard as Mock).mockResolvedValue({ hasLearningEvidence: false });
  (analyticsApi.activity as Mock).mockResolvedValue([]);
  (analyticsApi.activityByDay as Mock).mockResolvedValue([]);
  (analyticsApi.masteryTrend as Mock).mockResolvedValue([]);
}

function projectRoutes() {
  return (
    <Route path="/projects/:projectId" element={<ProjectDetailPage />}>
      <Route index element={<Navigate to="overview" replace />} />
      <Route path="overview" element={<ProjectOverviewTab />} />
      <Route path="materials" element={<ProjectMaterialsTab />} />
      <Route path="tutor" element={<ProjectTutorTab />} />
      <Route path="quiz" element={<ProjectQuizTab />} />
      <Route path="growth" element={<ProjectGrowthTab />} />
      <Route path="analytics" element={<ProjectAnalyticsTab />} />
      <Route path="*" element={<Navigate to="overview" replace />} />
    </Route>
  );
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>{projectRoutes()}</Routes>
    </MemoryRouter>,
  );
}

describe("project tab navigation", () => {
  beforeEach(resetStores);
  beforeEach(mockEmptyProject);

  it("redirects a bare project URL to Overview", async () => {
    renderAt("/projects/project-a");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    const materialsTab = screen.getByRole("link", { name: "Materials" });
    expect(materialsTab.getAttribute("href")).toBe("/projects/project-a/materials");
    expect(
      (screen.getByRole("link", { name: "Overview" }) as HTMLAnchorElement).getAttribute(
        "aria-current",
      ),
    ).toBe("page");
  });

  it("renders only Overview content on the overview tab", async () => {
    renderAt("/projects/project-a/overview");
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("No concepts yet.")).toBeInTheDocument());
    expect(screen.queryByText("No materials yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Ask about your materials.")).not.toBeInTheDocument();
    expect(screen.queryByText("No quizzes yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No mastery yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No learning evidence yet.")).not.toBeInTheDocument();
  });

  it("renders only Materials on the materials tab", async () => {
    renderAt("/projects/project-a/materials");
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    expect(screen.queryByText("No recommendations yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Ask about your materials.")).not.toBeInTheDocument();
  });

  it("renders only Tutor on the tutor tab", async () => {
    renderAt("/projects/project-a/tutor");
    await waitFor(() => expect(screen.getByText("Ask about your materials.")).toBeInTheDocument());
    expect(screen.queryByText("No materials yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No quizzes yet.")).not.toBeInTheDocument();
  });

  it("renders only Quiz on the quiz tab", async () => {
    renderAt("/projects/project-a/quiz");
    await waitFor(() => expect(screen.getByText("No quizzes yet.")).toBeInTheDocument());
    expect(screen.queryByText("Ask about your materials.")).not.toBeInTheDocument();
    expect(screen.queryByText("No mastery yet.")).not.toBeInTheDocument();
  });

  it("renders only Growth on the growth tab", async () => {
    renderAt("/projects/project-a/growth");
    await waitFor(() => expect(screen.getByText("No mastery yet.")).toBeInTheDocument());
    await waitFor(() =>
      expect(
        screen.getByText("Growth will appear after you complete your first assessment."),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByText("No quizzes yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No learning evidence yet.")).not.toBeInTheDocument();
  });

  it("renders only Analytics on the analytics tab", async () => {
    renderAt("/projects/project-a/analytics");
    await waitFor(() => expect(screen.getByText("No learning evidence yet.")).toBeInTheDocument());
    expect(screen.queryByText("No mastery yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No materials yet.")).not.toBeInTheDocument();
  });

  it("redirects an invalid tab to Overview", async () => {
    renderAt("/projects/project-a/something-invalid");
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    expect(screen.queryByText("No materials yet.")).not.toBeInTheDocument();
  });

  it("does not fetch inactive tabs on Overview load", async () => {
    renderAt("/projects/project-a/overview");
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    expect(projectsApi.get).toHaveBeenCalledWith("project-a");
    expect(recommendationsApi.list).toHaveBeenCalled();
    expect(knowledgeApi.status).toHaveBeenCalled();
    expect(materialsApi.list).not.toHaveBeenCalled();
    expect(tutorApi.conversations).not.toHaveBeenCalled();
    expect(assessmentApi.quizzes).not.toHaveBeenCalled();
    expect(masteryApi.list).not.toHaveBeenCalled();
    expect(growthApi.get).not.toHaveBeenCalled();
    expect(analyticsApi.dashboard).not.toHaveBeenCalled();
  });

  it("keeps the project header visible across tabs with active state", async () => {
    renderAt("/projects/project-a/materials");
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument();
    const nav = screen.getByLabelText("Project");
    expect(within(nav).getByRole("link", { name: "Materials" }).getAttribute("aria-current")).toBe(
      "page",
    );
    expect(within(nav).getByRole("link", { name: "Overview" }).hasAttribute("aria-current")).toBe(
      false,
    );
  });

  it("shows section error states with retry inside tabs", async () => {
    (materialsApi.list as Mock).mockRejectedValueOnce(new Error("down"));
    (materialsApi.list as Mock).mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 1,
      page_size: 20,
    });
    renderAt("/projects/project-a/materials");
    await waitFor(() => expect(screen.getByText("Could not load materials")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
  });

  it("denies unknown projects without leaking data", async () => {
    (projectsApi.get as Mock).mockRejectedValue(new Error("Not found"));
    renderAt("/projects/project-a/overview");
    await waitFor(() => expect(screen.getByText("Project not found")).toBeInTheDocument());
  });

  it("shows the breadcrumb without a redundant back link, progress bar, or updated date", async () => {
    renderAt("/projects/project-a/overview");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument(),
    );
    // Breadcrumb remains the primary hierarchy navigation.
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mathematics" })).toHaveAttribute(
      "href",
      "/spaces/space-a",
    );
    // Redundant rows removed: back link, duplicated readiness progress, metadata date.
    expect(screen.queryByRole("link", { name: /back to/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/materials ready \(/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/updated/i)).not.toBeInTheDocument();
    // The summary cards themselves stay: ready, mastery, processing.
    expect(screen.getByText("Materials ready")).toBeInTheDocument();
    expect(screen.getByText("Average mastery")).toBeInTheDocument();
    expect(screen.getByText("Processing")).toBeInTheDocument();
  });

  it("gives header and summary cards the restrained dark-gradient treatment", async () => {
    const { container } = renderAt("/projects/project-a/overview");
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument(),
    );
    // card-dark (deep navy → muted blue) marks exactly the project header
    // card plus the three stat cards — not every card on the page.
    expect(container.querySelectorAll(".card-dark").length).toBe(4);
  });

  it("does not force scroll-to-top when switching tabs", async () => {
    // jsdom provides no scrollingElement: stub one so the legacy
    // `document.scrollingElement.scrollTop = 0` reset (had it still existed)
    // would trip this test, while the fixed page never touches it.
    let forcedTo: number | null = null;
    const stub = {};
    Object.defineProperty(stub, "scrollTop", {
      configurable: true,
      get: () => 500,
      set: (v: number) => {
        forcedTo = v;
      },
    });
    Object.defineProperty(document, "scrollingElement", { configurable: true, value: stub });
    const scrollTo = vi.fn();
    const prevScrollTo = window.scrollTo;
    window.scrollTo = scrollTo as typeof window.scrollTo;
    try {
      const router = createMemoryRouter(
        [
          {
            path: "/projects/:projectId",
            element: <ProjectDetailPage />,
            children: [
              { index: true, element: <Navigate to="overview" replace /> },
              { path: "overview", element: <ProjectOverviewTab /> },
              { path: "quiz", element: <ProjectQuizTab /> },
              { path: "tutor", element: <ProjectTutorTab /> },
            ],
          },
        ],
        { initialEntries: ["/projects/project-a/overview"] },
      );
      render(<RouterProvider router={router} />);
      await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("link", { name: "Quiz" }));
      await waitFor(() => expect(screen.getByText("No quizzes yet.")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("link", { name: "Tutor" }));
      await waitFor(() =>
        expect(screen.getByText("Ask about your materials.")).toBeInTheDocument(),
      );
      // Neither the legacy scrollTop reset nor window.scrollTo may run.
      expect(forcedTo).toBeNull();
      expect(scrollTo).not.toHaveBeenCalled();
    } finally {
      delete (document as unknown as Record<string, unknown>)["scrollingElement"];
      window.scrollTo = prevScrollTo;
    }
  });
});

describe("project tab history", () => {
  beforeEach(resetStores);
  beforeEach(mockEmptyProject);

  function renderRouter(initialPath: string) {
    const router = createMemoryRouter(
      [
        {
          path: "/projects/:projectId",
          element: <ProjectDetailPage />,
          children: [
            { index: true, element: <Navigate to="overview" replace /> },
            { path: "overview", element: <ProjectOverviewTab /> },
            { path: "materials", element: <ProjectMaterialsTab /> },
            { path: "tutor", element: <ProjectTutorTab /> },
            { path: "quiz", element: <ProjectQuizTab /> },
            { path: "growth", element: <ProjectGrowthTab /> },
            { path: "analytics", element: <ProjectAnalyticsTab /> },
            { path: "*", element: <Navigate to="overview" replace /> },
          ],
        },
      ],
      { initialEntries: [initialPath] },
    );
    render(<RouterProvider router={router} />);
    return router;
  }

  it("updates the URL on tab click and preserves tabs on refresh", async () => {
    const router = renderRouter("/projects/project-a/overview");
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("link", { name: "Materials" }));
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    expect(router.state.location.pathname).toBe("/projects/project-a/materials");
    expect(screen.queryByText("No recommendations yet.")).not.toBeInTheDocument();
  });

  it("supports browser Back and Forward between tabs", async () => {
    const router = renderRouter("/projects/project-a/overview");
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("link", { name: "Materials" }));
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("link", { name: "Tutor" }));
    await waitFor(() => expect(screen.getByText("Ask about your materials.")).toBeInTheDocument());
    await router.navigate(-1);
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    await router.navigate(-1);
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    await router.navigate(1);
    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
  });

  it("stops material polling when leaving the Materials tab", async () => {
    vi.useFakeTimers();
    try {
      const queued = {
        id: "m-1",
        projectId: "project-a",
        name: "Doc.pdf",
        type: "PDF",
        status: "QUEUED",
        originalFilename: "doc.pdf",
        mimeType: "application/pdf",
        fileSize: 10,
        processingError: null,
        retryCount: 0,
        pageCount: null,
        chunkCount: null,
        createdAt: "2026-01-01T00:00:00Z",
        updatedAt: "2026-01-01T00:00:00Z",
      };
      (materialsApi.list as Mock).mockResolvedValue({
        items: [queued],
        total: 1,
        page: 1,
        page_size: 20,
      });
      (materialsApi.get as Mock).mockResolvedValue({ ...queued, document: null });
      const router = renderRouter("/projects/project-a/materials");
      // Flush mount effects + mocked API microtasks (no waitFor under fake timers).
      await act(async () => {});
      expect(screen.getByText("Doc.pdf")).toBeInTheDocument();
      const callsAfterMount = (materialsApi.get as Mock).mock.calls.length;
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000);
      });
      expect((materialsApi.get as Mock).mock.calls.length).toBeGreaterThan(callsAfterMount);
      const callsBeforeLeave = (materialsApi.get as Mock).mock.calls.length;
      fireEvent.click(screen.getByRole("link", { name: "Tutor" }));
      await act(async () => {});
      expect(screen.getByText("Ask about your materials.")).toBeInTheDocument();
      expect(router.state.location.pathname).toBe("/projects/project-a/tutor");
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30000);
      });
      expect((materialsApi.get as Mock).mock.calls.length).toBe(callsBeforeLeave);
    } finally {
      vi.useRealTimers();
    }
  });
});
