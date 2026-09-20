import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";

import { ProjectDetailPage } from "@/app/pages/ProjectDetailPage";
import { SpaceDetailPage } from "@/app/pages/SpaceDetailPage";
import { useAssessmentStore } from "@/stores/useAssessmentStore";
import { useProjectsStore } from "@/stores/useProjectsStore";
import { useSpacesStore } from "@/stores/useSpacesStore";

// Only the HTTP boundary is mocked; mapping, stores, and pages run for real.
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

const mockSpacesGet = spacesApi.get as Mock;
const mockProjectsGet = projectsApi.get as Mock;
const mockProjectsList = projectsApi.list as Mock;

const spaceA = { id: "space-a", name: "Mathematics", description: "Numbers" };
const spaceB = { id: "space-b", name: "Physics", description: "Motion" };
const projectA = {
  id: "project-a",
  spaceId: "space-a",
  name: "Algebra",
  description: "Equations",
  learningGoal: null,
  difficulty: null,
  materialCount: 0,
};
const projectB = {
  id: "project-b",
  spaceId: "space-b",
  name: "Calculus",
  description: "Limits",
  learningGoal: null,
  difficulty: null,
  materialCount: 0,
};

function reset() {
  useSpacesStore.getState().reset();
  useProjectsStore.getState().reset();
  useAssessmentStore.getState().reset();
  vi.clearAllMocks();
}

function ProjectHarness() {
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate("/projects/project-b/overview")}>go-b</button>
      <Routes>
        <Route path="/projects/:projectId" element={<ProjectDetailPage />}>
          <Route path="overview" element={<div>overview stub</div>} />
        </Route>
      </Routes>
    </>
  );
}

function SpaceHarness() {
  const navigate = useNavigate();
  return (
    <>
      <button onClick={() => navigate("/spaces/space-b")}>go-b</button>
      <Routes>
        <Route path="/spaces/:spaceId" element={<SpaceDetailPage />} />
      </Routes>
    </>
  );
}

describe("stale project navigation", () => {
  beforeEach(reset);

  it("never renders project A while project B loads", async () => {
    let resolveB!: (v: unknown) => void;
    mockProjectsGet.mockImplementation((id: string) =>
      id === "project-b" ? new Promise((r) => (resolveB = r)) : Promise.resolve(projectA),
    );
    mockSpacesGet.mockImplementation((id: string) =>
      Promise.resolve(id === "space-b" ? spaceB : spaceA),
    );
    render(
      <MemoryRouter initialEntries={["/projects/project-a/overview"]}>
        <ProjectHarness />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Algebra" })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "go-b" }));

    // While B is in flight: A must be gone, the loading state must show.
    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Algebra" })).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Loading project")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Calculus" })).not.toBeInTheDocument();

    resolveB(projectB);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Calculus" })).toBeInTheDocument(),
    );
  });
});

describe("stale space navigation", () => {
  beforeEach(reset);

  it("never renders space A (header or projects) while space B loads", async () => {
    let resolveB!: (v: unknown) => void;
    mockSpacesGet.mockImplementation((id: string) =>
      id === "space-b" ? new Promise((r) => (resolveB = r)) : Promise.resolve(spaceA),
    );
    mockProjectsList.mockResolvedValue({ items: [], total: 0, page: 1, page_size: 20 });
    render(
      <MemoryRouter initialEntries={["/spaces/space-a"]}>
        <SpaceHarness />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Mathematics" })).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "go-b" }));

    await waitFor(() =>
      expect(screen.queryByRole("heading", { name: "Mathematics" })).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Loading space")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Physics" })).not.toBeInTheDocument();

    resolveB(spaceB);
    await waitFor(() =>
      expect(screen.getByRole("heading", { name: "Physics" })).toBeInTheDocument(),
    );
    expect(screen.getByText("Motion")).toBeInTheDocument();
  });
});

describe("rapid-switch entity guards", () => {
  beforeEach(reset);

  it("late project responses cannot overwrite the latest route", async () => {
    let resolveA!: (v: unknown) => void;
    mockProjectsGet.mockImplementation((id: string) =>
      id === "project-a" ? new Promise((r) => (resolveA = r)) : Promise.resolve(projectB),
    );
    const store = useProjectsStore.getState();
    const pendingA = store.fetchOne("project-a");
    // Switching clears synchronously — no stale render window in the store.
    expect(useProjectsStore.getState().current).toBeNull();
    await store.fetchOne("project-b");
    expect(useProjectsStore.getState().current?.id).toBe("project-b");
    resolveA(projectA);
    await pendingA;
    expect(useProjectsStore.getState().current?.id).toBe("project-b");
  });

  it("late space responses cannot overwrite the latest route", async () => {
    let resolveA!: (v: unknown) => void;
    mockSpacesGet.mockImplementation((id: string) =>
      id === "space-a" ? new Promise((r) => (resolveA = r)) : Promise.resolve(spaceB),
    );
    const store = useSpacesStore.getState();
    const pendingA = store.fetchOne("space-a");
    expect(useSpacesStore.getState().current).toBeNull();
    await store.fetchOne("space-b");
    expect(useSpacesStore.getState().current?.id).toBe("space-b");
    resolveA(spaceA);
    await pendingA;
    expect(useSpacesStore.getState().current?.id).toBe("space-b");
  });

  it("reset invalidates in-flight entity fetches", async () => {
    let resolveA!: (v: unknown) => void;
    mockProjectsGet.mockImplementation(() => new Promise((r) => (resolveA = r)));
    const pending = useProjectsStore.getState().fetchOne("project-a");
    useProjectsStore.getState().reset();
    resolveA(projectA);
    await pending;
    expect(useProjectsStore.getState().current).toBeNull();
    expect(useProjectsStore.getState().status).toBe("idle");
  });
});
