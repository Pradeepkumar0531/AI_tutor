import { MemoryRouter, Navigate, Route, Routes } from "react-router-dom";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { SpacesPage } from "@/app/pages/SpacesPage";
import { ProjectDetailPage } from "@/app/pages/ProjectDetailPage";
import {
  ProjectAnalyticsTab,
  ProjectGrowthTab,
  ProjectMaterialsTab,
  ProjectOverviewTab,
  ProjectQuizTab,
  ProjectTutorTab,
} from "@/app/pages/project/ProjectTabs";
import { ProjectsPage } from "@/app/pages/ProjectsPage";
import { useAnalyticsStore } from "@/stores/useAnalyticsStore";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useGrowthStore } from "@/stores/useGrowthStore";
import { useMasteryStore } from "@/stores/useMasteryStore";
import { useRecommendationsStore } from "@/stores/useRecommendationsStore";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";
import { useTutorStore } from "@/stores/useTutorStore";

// Only the HTTP boundary is mocked; mapping, stores, and pages run for real.
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
    list: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
    upload: vi.fn(),
    get: vi.fn(),
    chunks: vi.fn(),
    reprocess: vi.fn(),
    archive: vi.fn(),
  },
}));
vi.mock("@/api/knowledge", () => ({
  knowledgeApi: {
    status: vi.fn().mockResolvedValue({
      project_id: "project-a",
      status: "PENDING",
      totals: { chunks_total: 0, chunks_embedded: 0, concepts: 0, materials_ready: 0 },
    }),
    concepts: vi.fn().mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 }),
    concept: vi.fn(),
    search: vi.fn(),
    reprocess: vi.fn(),
  },
}));
vi.mock("@/api/assessment", () => ({
  assessmentApi: {
    quizzes: vi.fn().mockResolvedValue([]),
    createQuiz: vi.fn(),
    quiz: vi.fn(),
    startAttempt: vi.fn(),
    attempt: vi.fn(),
    answer: vi.fn(),
    complete: vi.fn(),
    assessments: vi.fn().mockResolvedValue([]),
    assessment: vi.fn(),
  },
}));
vi.mock("@/api/analytics", () => ({
  analyticsApi: {
    dashboard: vi.fn().mockResolvedValue({ hasLearningEvidence: false }),
    activity: vi.fn().mockResolvedValue([]),
    activityByDay: vi.fn().mockResolvedValue([]),
    masteryTrend: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock("@/api/mastery", () => ({
  masteryApi: {
    list: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    detail: vi.fn(),
    history: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock("@/api/growth", () => ({
  growthApi: {
    get: vi.fn().mockResolvedValue({
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
    }),
    history: vi.fn().mockResolvedValue([]),
  },
}));
vi.mock("@/api/recommendations", () => ({
  recommendationsApi: {
    list: vi.fn().mockResolvedValue([]),
    complete: vi.fn(),
    dismiss: vi.fn(),
  },
}));
vi.mock("@/api/tutor", () => ({
  tutorApi: {
    conversations: vi.fn().mockResolvedValue([]),
    createConversation: vi.fn().mockResolvedValue({
      id: "conv-a",
      projectId: "project-a",
      title: "Untitled conversation",
      createdAt: "",
      updatedAt: "",
    }),
    messages: vi.fn().mockResolvedValue([]),
    send: vi.fn(),
  },
}));

import { projectsApi } from "@/api/projects";
import { spacesApi } from "@/api/spaces";

const mockSpacesList = spacesApi.list as Mock;
const mockSpacesGet = spacesApi.get as Mock;
const mockSpacesCreate = spacesApi.create as Mock;
const mockSpacesArchive = spacesApi.archive as Mock;
const mockSpacesRestore = spacesApi.restore as Mock;
const mockProjectsList = projectsApi.list as Mock;
const mockProjectsGet = projectsApi.get as Mock;
const mockProjectsCreate = projectsApi.create as Mock;

const spaceA = {
  id: "space-a",
  name: "Mathematics",
  description: "Numbers",
  archivedAt: null,
  createdAt: "2026-01-01T00:00:00Z",
  updatedAt: "2026-01-02T00:00:00Z",
  projectCount: 2,
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
  useTutorStore.getState().reset();
  useAssessmentStore.getState().reset();
  useMasteryStore.getState().reset();
  useGrowthStore.getState().reset();
  useRecommendationsStore.getState().reset();
  useAnalyticsStore.getState().reset();
  vi.clearAllMocks();
}

describe("spaces store + SpacesPage", () => {
  beforeEach(resetStores);

  it("loads and renders the space list with counts", async () => {
    mockSpacesList.mockResolvedValue({
      items: [spaceA],
      total: 1,
      page: 1,
      page_size: 20,
    });
    render(
      <MemoryRouter>
        <SpacesPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Mathematics")).toBeInTheDocument());
    expect(screen.getByText("2 projects")).toBeInTheDocument();
    expect(mockSpacesList).toHaveBeenCalledWith({
      page: 1,
      pageSize: 20,
      search: "",
      includeArchived: false,
    });
  });

  it("shows the structural empty state when there are no spaces", async () => {
    mockSpacesList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    render(
      <MemoryRouter>
        <SpacesPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("No learning spaces yet.")).toBeInTheDocument());
    expect(
      screen.getByText("Create a space to organize your learning projects."),
    ).toBeInTheDocument();
  });

  it("shows an error state with retry on API failure", async () => {
    mockSpacesList.mockRejectedValue(new Error("boom"));
    render(
      <MemoryRouter>
        <SpacesPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Could not load spaces")).toBeInTheDocument());
    mockSpacesList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    fireEvent.click(screen.getByText("Try again"));
    await waitFor(() => expect(screen.getByText("No learning spaces yet.")).toBeInTheDocument());
  });

  it("creates a space through the dialog and shows it without refetch", async () => {
    mockSpacesList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockSpacesCreate.mockImplementation(async (input: { name: string }) => ({
      ...spaceA,
      name: input.name,
    }));
    render(
      <MemoryRouter>
        <SpacesPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("No learning spaces yet.")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "New Space" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Physics" } });
    fireEvent.click(screen.getByRole("button", { name: "Create space" }));

    await waitFor(() => expect(screen.getByText("Physics")).toBeInTheDocument());
    expect(mockSpacesCreate).toHaveBeenCalledWith({ name: "Physics", description: "" });
    expect(mockSpacesList).toHaveBeenCalledTimes(1); // no full refetch
  });

  it("archives a space by removing it from the active list", async () => {
    mockSpacesList.mockResolvedValue({
      items: [spaceA],
      total: 1,
      page: 1,
      page_size: 20,
    });
    await useSpacesStore.getState().fetch();
    expect(useSpacesStore.getState().items).toHaveLength(1);
    mockSpacesArchive.mockResolvedValue({ ...spaceA, archivedAt: "2026-02-01T00:00:00Z" });
    await useSpacesStore.getState().archive("space-a");
    expect(useSpacesStore.getState().items).toHaveLength(0);
    expect(useSpacesStore.getState().total).toBe(0);
  });

  it("shows archived spaces with a restore action when toggled", async () => {
    const archived = { ...spaceA, archivedAt: "2026-02-01T00:00:00Z" };
    mockSpacesList.mockResolvedValue({ items: [archived], total: 1, page: 1, page_size: 20 });
    mockSpacesRestore.mockResolvedValue(spaceA);
    render(
      <MemoryRouter>
        <SpacesPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Mathematics")).toBeInTheDocument());

    // Toggle archived visibility: refetches with the flag.
    fireEvent.click(screen.getByLabelText("Show archived"));
    await waitFor(() =>
      expect(mockSpacesList).toHaveBeenCalledWith(
        expect.objectContaining({ includeArchived: true }),
      ),
    );
    expect(screen.getByText("Archived")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(mockSpacesRestore).toHaveBeenCalledWith("space-a"));
  });
});

describe("projects store + ProjectsPage", () => {
  beforeEach(resetStores);

  it("filters projects by space through the API layer", async () => {
    mockSpacesList.mockResolvedValue({ items: [spaceA], total: 1, page: 1, page_size: 20 });
    mockProjectsList.mockResolvedValue({
      items: [projectA],
      total: 1,
      page: 1,
      page_size: 20,
    });
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Algebra")).toBeInTheDocument());

    const select = screen.getByLabelText("Filter by space") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "space-a" } });
    await waitFor(() =>
      expect(mockProjectsList).toHaveBeenCalledWith(
        expect.objectContaining({ spaceId: "space-a" }),
      ),
    );
  });

  it("creates a project and surfaces API errors", async () => {
    mockSpacesList.mockResolvedValue({ items: [spaceA], total: 1, page: 1, page_size: 20 });
    mockProjectsList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    mockProjectsCreate.mockRejectedValue(new Error("taken"));
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("No projects yet.")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "New Project" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Geometry" } });
    // Space select defaults to "" — pick the only space.
    fireEvent.change(screen.getByLabelText("Space"), { target: { value: "space-a" } });
    fireEvent.click(screen.getByRole("button", { name: "Create project" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  });
});

describe("ProjectDetailPage workspace", () => {
  beforeEach(resetStores);

  function renderDetail(path = "/projects/project-a") {
    return render(
      <MemoryRouter initialEntries={[path]}>
        <Routes>
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
        </Routes>
      </MemoryRouter>,
    );
  }

  it("defaults bare project URLs to the Overview tab only", async () => {
    mockProjectsGet.mockResolvedValue(projectA);
    mockSpacesGet.mockResolvedValue(spaceA);
    renderDetail();

    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument(),
    );
    expect(screen.getByText(/Solve quadratics/)).toBeInTheDocument();
    expect(screen.getByText("0 materials")).toBeInTheDocument();
    // Overview content renders…
    await waitFor(() => expect(screen.getByText("No recommendations yet.")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("No concepts yet.")).toBeInTheDocument());
    // …and no other tab's content is mounted.
    expect(screen.queryByText("No materials yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("Ask about your materials.")).not.toBeInTheDocument();
    expect(screen.queryByText("No quizzes yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No mastery yet.")).not.toBeInTheDocument();
    expect(screen.queryByText("No learning evidence yet.")).not.toBeInTheDocument();

    // And no fabricated analytics anywhere.
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/mastery score|streak|hours learned/i);
  });

  it("renders only the active tab for each tab route", async () => {
    mockProjectsGet.mockResolvedValue(projectA);
    mockSpacesGet.mockResolvedValue(spaceA);
    renderDetail("/projects/project-a/materials");

    await waitFor(() => expect(screen.getByText("No materials yet.")).toBeInTheDocument());
    expect(screen.queryByText("Ask about your materials.")).not.toBeInTheDocument();
    expect(screen.queryByText("No recommendations yet.")).not.toBeInTheDocument();
  });

  it("shows a non-disclosing 404 for unknown projects", async () => {
    mockProjectsGet.mockRejectedValue(new Error("Not found"));
    renderDetail();
    await waitFor(() => expect(screen.getByText("Project not found")).toBeInTheDocument());
  });

  it("breadcrumbs link back through the owning space", async () => {
    mockProjectsGet.mockResolvedValue(projectA);
    mockSpacesGet.mockResolvedValue(spaceA);
    renderDetail();
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument(),
    );
    const nav = screen.getByLabelText("Breadcrumb");
    expect(within(nav).getByText("Mathematics").getAttribute("href")).toBe("/spaces/space-a");
  });
});
